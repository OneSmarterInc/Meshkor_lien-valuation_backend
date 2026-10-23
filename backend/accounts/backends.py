"""Sign in with e-mail + password (the frontend sends `email`)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        email = (kwargs.get("email") or username or "").strip()
        if not email or password is None:
            return None
        User = get_user_model()
        user = User.objects.filter(email__iexact=email).order_by("id").first() \
            or User.objects.filter(username__iexact=email).first()
        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
