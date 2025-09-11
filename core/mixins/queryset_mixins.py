from __future__ import annotations
from typing import Optional
from django.db import models
from django.db.models import Q


class ActiveQuerySet(models.QuerySet):
    """
    Common queryset for models having an `is_active` field.
    Provides reusable filters and search helpers.
    """

    def active(self) -> "ActiveQuerySet":
        """Return only active records (is_active=True)."""
        return self.filter(is_active=True)

    def inactive(self) -> "ActiveQuerySet":
        """Return only inactive records (is_active=False)."""
        return self.filter(is_active=False)

    def search(self, query: Optional[str], *fields: str) -> "ActiveQuerySet":
        """
        Case-insensitive contains search across the given `fields`.

        Example:
            MyModel.objects.search("hello", "title", "description")
        """
        if not query:
            return self

        conditions = Q()
        for f in fields:
            conditions |= Q(**{f"{f}__icontains": query})
        return self.filter(conditions)


class OwnerQuerySet(models.QuerySet):
    """
    QuerySet for filtering objects by their `owner` relationship.
    Assumes a ForeignKey or OneToOne field named `owner`.
    """

    def for_user(self, user) -> "OwnerQuerySet":
        """
        Filter queryset for objects owned by a specific user.
        Returns an empty queryset if the user is None or anonymous.
        """
        if user is None or getattr(user, "is_anonymous", False):
            return self.none()
        return self.filter(owner=user)


class ManagerFromQuerySet(models.Manager.from_queryset(ActiveQuerySet)):
    """
    Default manager based on ActiveQuerySet.
    Exposes `.active()`, `.inactive()`, and `.search()` at manager level.

    Example:
        MyModel.objects.active().search("foo", "title")
    """

    def get_queryset(self):  # type: ignore[override]
        # Extend here if you want global prefetch/select_related defaults
        return super().get_queryset()
