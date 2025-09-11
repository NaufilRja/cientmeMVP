from __future__ import annotations
import os
import secrets
import string
from typing import Iterable
from django.utils.text import slugify as dj_slugify




def rand_token(n: int = 32) -> str:
    """Cryptographically secure random token (URL-safe)."""
    return secrets.token_urlsafe(n)




def safe_slug(value: str, *, allow_unicode: bool = False) -> str:
    """Slugify with fallback to random suffix to avoid empty slugs."""
    base = dj_slugify(value or "", allow_unicode=allow_unicode)
    return base or f"item-{secrets.token_hex(4)}"




def ensure_unique_slug(instance, slug_field: str = "slug", source_field: str = "name") -> None:
    """Populate a unique slug on `instance` based on `source_field`.
    Must be called before saving. Requires the model to have a manager and `slug` field.
    """
    base = safe_slug(getattr(instance, source_field, ""))
    Model = instance.__class__
    slug = base
    i = 2
    while Model.objects.filter(**{slug_field: slug}).exclude(       pk=instance.pk).exists():
        slug = f"{base}-{i}"
        i += 1
        setattr(instance, slug_field, slug)




def random_filename(original_name: str, *, prefix: str | None = None) -> str:
    """Create a randomized filename preserving extension."""
    _, ext = os.path.splitext(original_name)
    core = secrets.token_hex(8)
    return f"{(prefix + '-') if prefix else ''}{core}{ext.lower()}"


