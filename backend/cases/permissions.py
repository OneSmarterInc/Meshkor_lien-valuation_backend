from rest_framework.permissions import BasePermission

from accounts.models import is_staff_role


class IsStaffRole(BasePermission):
    message = "Only MeshKor staff can do this."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and is_staff_role(request.user))
