from __future__ import annotations
from django.db import models
from django.utils import timezone




class TimeStampedModel(models.Model):
    """Abstract base with created/updated timestamps.
    Use this when you only need timestamps, without activation flags.
    """
    created_at = models.DateTimeField(auto_now_add=True, help_text="Object creation time.")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last modification time.")


    class Meta:
        abstract = True
        ordering = ("-created_at",)




class BaseModel(TimeStampedModel):
    """Abstract base for most models.
    Adds an `is_active` flag for soft delete and simple lifecycle helpers.
    Keep *User* models separate from this if you rely on Django's native `is_active` semantics.
    """
    
    is_active = models.BooleanField(default=True, help_text="Soft-delete flag. Inactive == hidden.")


    class Meta(TimeStampedModel.Meta):
        abstract = True


    def deactivate(self, *, save: bool = True) -> None:
        """Soft delete: mark inactive and optionally persist."""
        self.is_active = False
        if save:
            self.save(update_fields=["is_active", "updated_at"]) # auto-updates updated_at


    def activate(self, *, save: bool = True) -> None:
        """Restore a soft-deleted instance."""
        self.is_active = True
        if save:
            self.save(update_fields=["is_active", "updated_at"]) # auto-updates updated_at


    def touch(self) -> None:
        """Manually bump `updated_at` without other changes."""
        self.updated_at = timezone.now()
        self.save(update_fields=["updated_at"]) # triggers signals  