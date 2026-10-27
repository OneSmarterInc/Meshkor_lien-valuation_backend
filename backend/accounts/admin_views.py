"""Admin pages (MeshKor admin only): law firms, users, payer names.

Roles (decided October 27, 2026):
  firm      a law firm user: uploads bills, sees only its own firm's released reports
  reviewer  MeshKor staff: reviews, approves and sends reports
  admin     everything a reviewer does, plus these pages

Every change is written to the audit log. A password is never shown again after it is made:
the admin gets a one-time temporary password, and the user must change it at the next sign-in.
"""
from __future__ import annotations

import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from cases.audit import log
from cases.permissions import IsAdminRole
from .models import Firm, Profile
from .serializers import user_payload

User = get_user_model()
OPEN = ("uploaded", "processing", "needs_review", "returned", "no_price_file", "error")


def temp_password() -> str:
    return secrets.token_urlsafe(9)          # 12 characters, shown once to the admin


def end_sessions(user) -> None:
    """Sign the user out everywhere: every refresh token is blacklisted (the access token ends within 30 minutes)."""
    try:
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
        for t in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=t)
    except Exception:  # noqa: BLE001 — the blacklist app may be off in a test setup
        pass


# ----------------------------------------------------------------------------- firms

def firm_row(f: Firm) -> dict:
    return {"id": f.id, "name": f.name, "contact_email": f.contact_email, "active": f.active, "created_at": f.created_at,
            "users": getattr(f, "n_users", None), "cases": getattr(f, "n_cases", None), "open_cases": getattr(f, "n_open", None)}


class FirmIn(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    active = serializers.BooleanField(required=False)

    def validate_name(self, v):
        v = " ".join(v.split())
        if not v:
            raise serializers.ValidationError("Give the firm's name.")
        qs = Firm.objects.filter(name__iexact=v)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A firm with this name exists already.")
        return v


def _firms():
    return Firm.objects.annotate(n_users=Count("users", distinct=True), n_cases=Count("cases", distinct=True),
                                 n_open=Count("cases", filter=Q(cases__status__in=OPEN), distinct=True)).order_by("name")


class AdminFirms(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        return Response([firm_row(f) for f in _firms()])

    def post(self, request):
        s = FirmIn(data=request.data)
        s.is_valid(raise_exception=True)
        if "name" not in s.validated_data:
            return Response({"name": ["Give the firm's name."]}, status=400)
        f = Firm.objects.create(name=s.validated_data["name"], contact_email=s.validated_data.get("contact_email", ""))
        log(request.user, "Firm added", f.name)
        return Response(firm_row(_firms().get(pk=f.pk)), status=status.HTTP_201_CREATED)


class AdminFirm(APIView):
    permission_classes = [IsAdminRole]

    def patch(self, request, pk):
        f = get_object_or_404(Firm, pk=pk)
        s = FirmIn(f, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        changes = []
        for k, v in s.validated_data.items():
            if getattr(f, k) != v:
                changes.append(f"{k}: {getattr(f, k)!r} → {v!r}")
                setattr(f, k, v)
        if changes:
            f.save()
            if s.validated_data.get("active") is False:
                for p in f.users.select_related("user"):
                    end_sessions(p.user)
            log(request.user, "Firm changed", f"{f.name}: " + "; ".join(changes))
        return Response(firm_row(_firms().get(pk=f.pk)))


# ----------------------------------------------------------------------------- users

def user_row(u) -> dict:
    p = getattr(u, "profile", None)
    return {**user_payload(u), "first_name": u.first_name, "last_name": u.last_name, "active": u.is_active,
            "last_login": u.last_login, "date_joined": u.date_joined}


class UserIn(serializers.Serializer):
    email = serializers.EmailField(required=False)
    name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=[r.value for r in Profile.Role], required=False)
    firm_id = serializers.IntegerField(required=False, allow_null=True)
    active = serializers.BooleanField(required=False)


def _check_role_firm(role, firm_id):
    if role == Profile.Role.FIRM:
        if not firm_id:
            return None, {"firm_id": ["A law firm user must belong to a firm."]}
        firm = Firm.objects.filter(pk=firm_id).first()
        if firm is None:
            return None, {"firm_id": ["No such firm."]}
        return firm, None
    return None, None                       # MeshKor staff belong to no firm


def _active_admins_without(user) -> int:
    return Profile.objects.filter(role=Profile.Role.ADMIN, user__is_active=True).exclude(user=user).count()


class AdminUsers(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        qs = User.objects.select_related("profile", "profile__firm").filter(profile__isnull=False).order_by("email")
        role = request.query_params.get("role")
        if role:
            qs = qs.filter(profile__role=role)
        firm = request.query_params.get("firm")
        if firm:
            if not firm.isdigit():
                return Response({"detail": "firm must be a number."}, status=400)
            qs = qs.filter(profile__firm_id=int(firm))
        return Response([user_row(u) for u in qs])

    def post(self, request):
        s = UserIn(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if not d.get("email"):
            return Response({"email": ["Give the user's email."]}, status=400)
        email = d["email"].strip().lower()
        if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exists():
            return Response({"email": ["A user with this email exists already."]}, status=400)
        role = d.get("role") or Profile.Role.FIRM
        firm, err = _check_role_firm(role, d.get("firm_id"))
        if err:
            return Response(err, status=400)
        pw = temp_password()
        first, _, last = (d.get("name") or "").strip().partition(" ")
        with transaction.atomic():
            u = User.objects.create_user(username=email, email=email, password=pw, first_name=first[:150], last_name=last[:150])
            Profile.objects.create(user=u, role=role, firm=firm, must_change_password=True)
        log(request.user, "User added", f"{email} · {role}" + (f" · {firm.name}" if firm else ""))
        return Response({**user_row(u), "temporary_password": pw}, status=status.HTTP_201_CREATED)


class AdminUser(APIView):
    permission_classes = [IsAdminRole]

    def patch(self, request, pk):
        u = get_object_or_404(User.objects.select_related("profile"), pk=pk, profile__isnull=False)
        p = u.profile
        s = UserIn(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        role = d.get("role", p.role)
        firm_id = d["firm_id"] if "firm_id" in d else p.firm_id
        active = d.get("active", u.is_active)
        if u.pk == request.user.pk and (role != p.role or not active):
            return Response({"detail": "You cannot change your own role or turn off your own account."}, status=400)
        if p.role == Profile.Role.ADMIN and (role != Profile.Role.ADMIN or not active) and _active_admins_without(u) == 0:
            return Response({"detail": "The portal needs at least one active admin."}, status=400)
        firm, err = _check_role_firm(role, firm_id)
        if err:
            return Response(err, status=400)
        changes = []
        if "email" in d:
            email = d["email"].strip().lower()
            if email != u.email.lower():
                if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exclude(pk=u.pk).exists():
                    return Response({"email": ["A user with this email exists already."]}, status=400)
                changes.append(f"email {u.email} → {email}")
                u.email = u.username = email
        if "name" in d:
            first, _, last = d["name"].strip().partition(" ")
            if (first, last) != (u.first_name, u.last_name):
                changes.append(f"name → {d['name'].strip()!r}")
                u.first_name, u.last_name = first[:150], last[:150]
        if role != p.role:
            changes.append(f"role {p.role} → {role}")
        if (firm.pk if firm else None) != p.firm_id:
            changes.append(f"firm → {firm.name if firm else 'none'}")
        if active != u.is_active:
            changes.append("turned on" if active else "turned off")
        with transaction.atomic():
            u.is_active = active
            u.save()
            p.role, p.firm = role, firm
            p.save()
        if changes and (not active or "role" in " ".join(changes) or "firm" in " ".join(changes)):
            end_sessions(u)                  # new rights apply at the next sign-in
        if changes:
            log(request.user, "User changed", f"{u.email}: " + "; ".join(changes))
        return Response(user_row(u))


class AdminUserResetPassword(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        u = get_object_or_404(User.objects.select_related("profile"), pk=pk, profile__isnull=False)
        pw = temp_password()
        u.set_password(pw)
        u.save()
        u.profile.must_change_password = True
        u.profile.save(update_fields=["must_change_password"])
        end_sessions(u)
        log(request.user, "Password reset", u.email)
        return Response({"temporary_password": pw})


# ----------------------------------------------------------------------------- own password (every user)

class ChangePassword(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        cur = request.data.get("current_password") or ""
        new = request.data.get("new_password") or ""
        u = request.user
        if not u.check_password(cur):
            return Response({"current_password": ["This is not your current password."]}, status=400)
        if new == cur:
            return Response({"new_password": ["Choose a password you have not used here."]}, status=400)
        try:
            validate_password(new, u)
        except ValidationError as e:
            return Response({"new_password": list(e.messages)}, status=400)
        u.set_password(new)
        u.save()
        p = getattr(u, "profile", None)
        if p and p.must_change_password:
            p.must_change_password = False
            p.save(update_fields=["must_change_password"])
        log(u, "Password changed", u.email)
        return Response(user_payload(u))
