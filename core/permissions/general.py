from __future__ import annotations
from rest_framework.permissions import BasePermission, SAFE_METHODS


class AllowReadOnly(BasePermission):
    """
    Custom permission that allows read-only access (safe methods only).
    Safe methods include: GET, HEAD, OPTIONS.
    """

    def has_permission(self, request, view) -> bool:
        return request.method in SAFE_METHODS


class IsProfileOwnerOrReadOnly(BasePermission):
    """
    Permission that allows profile owners full access,
    but restricts others to read-only actions.
    Assumes the object has a `user` attribute.
    """

    def has_object_permission(self, request, view, obj) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return getattr(obj, "user", None) == request.user


class IsStaffOrReadOnly(BasePermission):
    """
    Permission that allows staff users full access,
    but restricts non-staff users to read-only actions.
    """

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)


class IsActiveUser(BasePermission):
    """
    Permission that only allows active users to access the API.
    Useful for disabling accounts without deleting them.
    """

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.is_active)
