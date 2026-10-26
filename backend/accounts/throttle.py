"""Slow down password guessing on /api/auth/login/.

Failed sign-ins in the last WINDOW are counted three ways:
  same email from the same computer (IP)  -> block after PER_EMAIL_IP  (a person mistyping, or a guesser)
  same computer, any email                -> block after PER_IP        (one computer trying many accounts)
  same email, any computer                -> block after PER_EMAIL     (many computers attacking one account)
The per-IP and per-email limits are higher than the first one, so an office whose staff share one internet
address, or a lawyer whose account someone else is attacking from far away, is not locked out by others.
A correct password from the same computer clears that computer's count for that email.
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

WINDOW = timedelta(minutes=getattr(settings, "LOGIN_LOCK_MINUTES", 15))
PER_EMAIL_IP = getattr(settings, "LOGIN_MAX_FAILS", 5)
PER_IP = 20
PER_EMAIL = 50


def client_ip(request) -> str:
    # Behind a reverse proxy (DJANGO_SECURE=1), the proxy puts the real address first in X-Forwarded-For.
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "") if getattr(settings, "SECURE_PROXY_SSL_HEADER", None) else ""
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR", "")) or "unknown"


def blocked(email: str, ip: str) -> int:
    """Minutes until sign-in is allowed again (0 = allowed now)."""
    import math
    from .models import LoginAttempt
    now = timezone.now()
    recent = LoginAttempt.objects.filter(at__gte=now - WINDOW)
    wait = 0.0
    for qs, limit in ((recent.filter(email=email, ip=ip), PER_EMAIL_IP),
                      (recent.filter(ip=ip), PER_IP),
                      (recent.filter(email=email), PER_EMAIL)):
        n = qs.count()
        if n >= limit:
            # Allowed again once the count falls below the limit, i.e. when the (n - limit + 1)-th oldest attempt expires.
            key = qs.order_by("at")[n - limit]
            wait = max(wait, ((key.at + WINDOW) - now).total_seconds())
    return math.ceil(wait / 60) if wait > 0 else 0


def failed(email: str, ip: str) -> None:
    from .models import LoginAttempt
    LoginAttempt.objects.create(email=email, ip=ip)


def succeeded(email: str, ip: str) -> None:
    from .models import LoginAttempt
    LoginAttempt.objects.filter(email=email, ip=ip).delete()
    LoginAttempt.objects.filter(at__lt=timezone.now() - timedelta(days=1)).delete()   # keep the table small
