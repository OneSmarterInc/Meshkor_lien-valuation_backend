from rest_framework import serializers

from .models import Firm


class FirmSerializer(serializers.ModelSerializer):
    class Meta:
        model = Firm
        fields = ("id", "name")


def user_payload(user) -> dict:
    """The `user` object of the API contract."""
    p = getattr(user, "profile", None)
    name = (user.get_full_name() or "").strip() or user.email or user.username
    return {
        "id": user.id,
        "name": name,
        "email": user.email,
        "role": p.role if p else "firm",
        "firm": FirmSerializer(p.firm).data if p and p.firm_id else None,
        "must_change_password": bool(p and p.must_change_password),
    }


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)
