"""Portal users. Django's own User keeps email and password; Profile adds the
portal role and the law firm. A firm user sees only its firm's cases."""
from django.conf import settings
from django.db import models


class Firm(models.Model):
    name = models.CharField(max_length=200, unique=True)
    contact_email = models.EmailField(blank=True, help_text="Where 'report ready' mail goes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Profile(models.Model):
    class Role(models.TextChoices):
        FIRM = "firm", "Law firm user"
        REVIEWER = "reviewer", "MeshKor reviewer"
        ADMIN = "admin", "MeshKor admin"

    STAFF_ROLES = (Role.REVIEWER, Role.ADMIN)

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.FIRM)
    firm = models.ForeignKey(Firm, null=True, blank=True, on_delete=models.PROTECT, related_name="users")

    def __str__(self):
        return f"{self.user.email} ({self.role})"

    @property
    def is_staff_role(self) -> bool:
        return self.role in self.STAFF_ROLES

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.role == self.Role.FIRM and self.firm_id is None:
            raise ValidationError({"firm": "A firm user must belong to a firm."})


def role_of(user) -> str | None:
    p = getattr(user, "profile", None)
    return p.role if p else None


def is_staff_role(user) -> bool:
    p = getattr(user, "profile", None)
    return bool(p and p.is_staff_role)


def firm_of(user):
    p = getattr(user, "profile", None)
    return p.firm if p else None


class LoginAttempt(models.Model):
    """One failed sign-in. Used to slow down password guessing (accounts/throttle.py).
    Kept 1 day, then deleted by the next sign-in."""
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    email = models.CharField(max_length=254, db_index=True)    # as typed, lower-case
    ip = models.CharField(max_length=45, db_index=True)        # IPv4 or IPv6

    class Meta:
        ordering = ["-at"]
