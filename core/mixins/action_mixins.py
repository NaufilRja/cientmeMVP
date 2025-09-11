from __future__ import annotations
from typing import Any, Dict
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated




class ActionResponseMixin:
    """Small helpers to standardize API responses inside viewsets."""

    def success(self, data: Dict[str, Any] | None = None, status_code: int = status.HTTP_200_OK) -> Response:
        return Response({"ok": True, **(data or {})}, status=status_code)


    def fail(self, message: str, *, status_code: int = status.      HTTP_400_BAD_REQUEST, **extra) -> Response:
        payload = {"ok": False, "detail": message}
        payload.update(extra)
        return Response(payload, status=status_code)



class OwnerActionsMixin(ActionResponseMixin):
    """ViewSet mixin offering common owner-centric actions.
    Assumes the queryset model has a boolean `is_active` and an `owner` field.
    """


    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=["post"], url_path="deactivate")
    
    def deactivate(self, request, pk=None): # noqa: D401
        """Soft-deactivate an object (sets `is_active=False`)."""
        obj = self.get_object()
        if getattr(obj, "owner_id", None) != request.user.id and not request.user.is_staff:
            return self.fail("Not allowed.", status_code=status.HTTP_403_FORBIDDEN)
        if hasattr(obj, "deactivate"):
            obj.deactivate()
        else:
            obj.is_active = False
            obj.save(update_fields=["is_active"])
        return self.success({"id": obj.pk, "is_active": obj.is_active})


    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        obj = self.get_object()
        if getattr(obj, "owner_id", None) != request.user.id and not request.user.is_staff:
            return self.fail("Not allowed.", status_code=status.HTTP_403_FORBIDDEN)
        if hasattr(obj, "activate"):
            obj.activate()
        else:
            obj.is_active = True
            obj.save(update_fields=["is_active"])
        return self.success({"id": obj.pk, "is_active": obj.is_active})