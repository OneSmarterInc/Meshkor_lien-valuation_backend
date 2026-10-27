from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView  # noqa: F401  (used in urls)

from cases.audit import log
from . import mfa, throttle
from .serializers import LoginSerializer, user_payload


def issue_tokens(request, user) -> dict:
    """The end of a full sign-in: clear the failed-attempt count, write the audit line, return the tokens."""
    from django.contrib.auth.models import update_last_login
    throttle.succeeded(user.email.lower(), throttle.client_ip(request))
    update_last_login(None, user)                     # "Last sign-in" on the Users page
    refresh = RefreshToken.for_user(user)
    log(user, "Signed in")
    return {"access": str(refresh.access_token), "refresh": str(refresh), "user": user_payload(user)}


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        email = s.validated_data["email"].strip().lower()
        ip = throttle.client_ip(request)
        wait = throttle.blocked(email, ip)
        if wait:
            log(None, "Sign-in blocked", f"{email} from {ip}: too many wrong passwords")
            return Response({"detail": f"Too many sign-in attempts. Try again in {wait} minute{'s' if wait != 1 else ''}."},
                            status=status.HTTP_429_TOO_MANY_REQUESTS, headers={"Retry-After": str(wait * 60)})
        user = authenticate(request, email=s.validated_data["email"], password=s.validated_data["password"])
        if user is None:
            throttle.failed(email, ip)
            return Response({"detail": "Wrong email or password."}, status=status.HTTP_401_UNAUTHORIZED)
        if not hasattr(user, "profile"):
            return Response({"detail": "This account has no portal role. Ask MeshKor."}, status=status.HTTP_403_FORBIDDEN)
        f = user.profile.firm
        if user.profile.role == "firm" and (f is None or not f.active):
            log(user, "Sign-in refused", "the firm is turned off")
            return Response({"detail": "Your firm's portal account is turned off. Ask MeshKor."}, status=status.HTTP_403_FORBIDDEN)
        if mfa.required():
            # Right password. The sign-in ends only after the Google Authenticator code (accounts/mfa.py),
            # so the failed-attempt count is not cleared yet.
            tf = getattr(user, "two_factor", None)
            stage = "verify" if (tf is not None and tf.confirmed) else "setup"
            return Response({"mfa": stage, "mfa_token": mfa.challenge(user, stage)})
        return Response(issue_tokens(request, user))


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(user_payload(request.user))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get("refresh")
        if token:
            try:
                RefreshToken(token).blacklist()
            except TokenError:
                pass
        log(request.user, "Signed out")
        return Response(status=status.HTTP_204_NO_CONTENT)
