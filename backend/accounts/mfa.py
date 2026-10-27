"""Two-step sign-in with Google Authenticator (or any TOTP app: Microsoft Authenticator, Authy, 1Password).

For every role (firm, reviewer, admin) when MESHKOR_MFA_REQUIRED=1 (the default):

  1. POST /api/auth/login/ {email, password}
       right password, 2FA already set up  -> {"mfa": "verify", "mfa_token"}   (no sign-in yet)
       right password, 2FA not set up yet  -> {"mfa": "setup",  "mfa_token"}
  2a. setup:  POST /api/auth/mfa/setup/   {mfa_token}        -> {secret, otpauth_uri, qr_svg}
              POST /api/auth/mfa/confirm/ {mfa_token, code}  -> signed in + 10 recovery codes (shown once)
  2b. verify: POST /api/auth/mfa/verify/  {mfa_token, code}  -> signed in   (code = 6 digits, or a recovery code)

The mfa_token is signed by the server, lasts 10 minutes, and stops working when the password changes.
The 6-digit code changes every 30 seconds; a code works only once; 30 seconds of clock difference are allowed.
Wrong codes count in the same sign-in limit as wrong passwords (accounts/throttle.py), and a right password
alone no longer clears that count: only a full sign-in does.
The secret is stored encrypted (MESHKOR_FILE_KEY), recovery codes as keyed hashes. Everything runs on this
server: the QR code is drawn here, and nothing is sent to Google or anyone else.
A user who lost the phone signs in with a recovery code, or an admin resets their 2FA (Admin > Users).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

from django.conf import settings
from django.core import signing
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from cases.audit import log
from . import throttle
from .models import TwoFactor

ISSUER = "MeshKor Lien Valuation"
TOKEN_AGE = 600            # seconds an mfa_token is valid (time to install the app and scan)
STEP = 30
RECOVERY_N = 10
_ALPHA = "abcdefghjkmnpqrstuvwxyz23456789"     # no 0/o, 1/l/i


def required() -> bool:
    return bool(getattr(settings, "MESHKOR_MFA_REQUIRED", True))


# ----------------------------------------------------------------------------- storage

def _fernet():
    from cryptography.fernet import Fernet
    key = getattr(settings, "MESHKOR_FILE_KEY", "") or ""
    if not key:     # a developer PC without MESHKOR_FILE_KEY: a key made from the secret key
        key = base64.urlsafe_b64encode(hashlib.sha256(("mfa:" + settings.SECRET_KEY).encode()).digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def secret_of(tf: TwoFactor) -> str:
    return _fernet().decrypt(tf.secret_enc.encode()).decode()


def _hash(code: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), ("recovery:" + code).encode(), hashlib.sha256).hexdigest()


def _norm(code: str) -> str:
    return "".join(ch for ch in (code or "").lower() if ch.isalnum())


def new_recovery_codes(tf: TwoFactor) -> list[str]:
    codes = ["".join(secrets.choice(_ALPHA) for _ in range(4)) + "-" + "".join(secrets.choice(_ALPHA) for _ in range(4))
             for _ in range(RECOVERY_N)]
    tf.recovery_hashes = [_hash(_norm(c)) for c in codes]
    tf.save(update_fields=["recovery_hashes"])
    return codes


def check_code(tf: TwoFactor, code: str, allow_recovery: bool = True) -> str | None:
    """'totp' or 'recovery' when the code is right (and uses it up), else None."""
    import pyotp
    c = _norm(code)
    if c.isdigit() and len(c) == 6:
        totp = pyotp.TOTP(secret_of(tf))
        now = int(time.time()) // STEP
        for step in (now - 1, now, now + 1):
            if step > tf.last_step and hmac.compare_digest(totp.at(step * STEP), c):
                tf.last_step = step
                tf.save(update_fields=["last_step"])
                return "totp"
        return None
    if allow_recovery and len(c) == 8:
        h = _hash(c)
        for i, stored in enumerate(tf.recovery_hashes or []):
            if hmac.compare_digest(stored, h):
                tf.recovery_hashes = tf.recovery_hashes[:i] + tf.recovery_hashes[i + 1:]
                tf.save(update_fields=["recovery_hashes"])
                return "recovery"
    return None


# ----------------------------------------------------------------------------- the step between password and code

def _pw_tag(user) -> str:
    return hashlib.sha256((user.password or "").encode()).hexdigest()[:12]


def challenge(user, stage: str) -> str:
    return signing.dumps({"u": user.pk, "s": stage, "p": _pw_tag(user)}, salt="meshkor.mfa")


def _from_token(request, stage: str):
    from django.contrib.auth import get_user_model
    try:
        d = signing.loads(str(request.data.get("mfa_token") or ""), salt="meshkor.mfa", max_age=TOKEN_AGE)
    except signing.BadSignature:
        return None, Response({"detail": "The sign-in step has expired. Sign in again."}, status=status.HTTP_401_UNAUTHORIZED)
    user = get_user_model().objects.filter(pk=d.get("u"), is_active=True).select_related("profile").first()
    if user is None or d.get("s") != stage or d.get("p") != _pw_tag(user):
        return None, Response({"detail": "The sign-in step has expired. Sign in again."}, status=status.HTTP_401_UNAUTHORIZED)
    return user, None


def _blocked(request, user):
    ip = throttle.client_ip(request)
    wait = throttle.blocked(user.email.lower(), ip)
    if wait:
        log(user, "Sign-in blocked", f"{user.email} from {ip}: too many wrong codes")
        return Response({"detail": f"Too many sign-in attempts. Try again in {wait} minute{'s' if wait != 1 else ''}."},
                        status=status.HTTP_429_TOO_MANY_REQUESTS, headers={"Retry-After": str(wait * 60)})
    return None


def _wrong(request, user, what="code"):
    throttle.failed(user.email.lower(), throttle.client_ip(request))
    return Response({"code": [f"This {what} is not right. Use the newest 6-digit code in the app."]}, status=400)


def _signed_in(request, user, extra=None):
    from .views import issue_tokens
    return Response({**issue_tokens(request, user), **(extra or {})})


# ----------------------------------------------------------------------------- views: sign-in

class MfaSetup(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        import pyotp
        import segno
        user, err = _from_token(request, "setup")
        if err:
            return err
        tf = TwoFactor.objects.filter(user=user).first()
        if tf and tf.confirmed:
            return Response({"detail": "Two-step sign-in is already set up. Sign in again."}, status=400)
        if tf is None:
            tf = TwoFactor.objects.create(user=user, secret_enc=_fernet().encrypt(pyotp.random_base32().encode()).decode())
        secret = secret_of(tf)
        uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=ISSUER)
        qr = segno.make(uri, error="m")
        return Response({"secret": secret, "secret_grouped": " ".join(secret[i:i + 4] for i in range(0, len(secret), 4)),
                         "otpauth_uri": uri, "qr_svg": qr.svg_data_uri(scale=5, border=2, dark="#17232b"),
                         "issuer": ISSUER, "account": user.email})


class MfaConfirm(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        user, err = _from_token(request, "setup")
        if err:
            return err
        blocked = _blocked(request, user)
        if blocked:
            return blocked
        tf = TwoFactor.objects.filter(user=user, confirmed_at__isnull=True).first()
        if tf is None:
            return Response({"detail": "Start the set-up again."}, status=400)
        if check_code(tf, request.data.get("code"), allow_recovery=False) is None:
            return _wrong(request, user)
        tf.confirmed_at = timezone.now()
        tf.save(update_fields=["confirmed_at"])
        codes = new_recovery_codes(tf)
        log(user, "Two-step sign-in set up", user.email)
        return _signed_in(request, user, {"recovery_codes": codes})


class MfaVerify(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        user, err = _from_token(request, "verify")
        if err:
            return err
        blocked = _blocked(request, user)
        if blocked:
            return blocked
        tf = TwoFactor.objects.filter(user=user, confirmed_at__isnull=False).first()
        if tf is None:
            return Response({"detail": "The sign-in step has expired. Sign in again."}, status=status.HTTP_401_UNAUTHORIZED)
        how = check_code(tf, request.data.get("code"))
        if how is None:
            return _wrong(request, user)
        extra = {}
        if how == "recovery":
            left = len(tf.recovery_hashes)
            log(user, "Signed in with a recovery code", f"{left} left")
            extra["recovery_codes_left"] = left
        return _signed_in(request, user, extra)


# ----------------------------------------------------------------------------- views: own account

class MfaStatus(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tf = TwoFactor.objects.filter(user=request.user, confirmed_at__isnull=False).first()
        return Response({"required": required(), "enabled": bool(tf), "confirmed_at": tf.confirmed_at if tf else None,
                         "recovery_codes_left": len(tf.recovery_hashes) if tf else 0})


class MfaNewRecoveryCodes(APIView):
    """New recovery codes; the old ones stop working. Needs a current 6-digit code."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tf = TwoFactor.objects.filter(user=request.user, confirmed_at__isnull=False).first()
        if tf is None:
            return Response({"detail": "Two-step sign-in is not set up for this account."}, status=400)
        blocked = _blocked(request, request.user)
        if blocked:
            return blocked
        if check_code(tf, request.data.get("code"), allow_recovery=False) is None:
            return _wrong(request, request.user)
        codes = new_recovery_codes(tf)
        log(request.user, "New recovery codes made", request.user.email)
        return Response({"recovery_codes": codes})
