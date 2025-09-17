from __future__ import annotations
import re
from typing import Iterable
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from core.constants import MAX_IMAGE_SIZE_MB, MAX_VIDEO_SIZE_MB






def validate_image_file_size(file):
    if file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise ValidationError(f"File too large. Max {MAX_IMAGE_SIZE_MB} MB allowed.")

# def validate_video_file_size(file):
#     if file.size > MAX_VIDEO_SIZE_MB * 1024 * 1024:
#         raise ValidationError(f"File too large. Max {MAX_VIDEO_SIZE_MB} MB allowed.")


def validate_video_file_size(file):
    # Intentionally left empty — validation is handled in serializer
    pass


def validate_allowed_extensions(filename: str, allowed: Iterable[str]) -> None:
    """Ensure filename has an allowed extension (case-insensitive)."""
    if "." not in filename:
        raise ValidationError("File has no extension.")
    ext = filename.rsplit(".", 1)[1].lower()
    if ext not in {e.lower().lstrip(".") for e in allowed}:
        raise ValidationError(f"Unsupported file type: .{ext}")




_username_re = re.compile(r"^[a-zA-Z0-9_\.\-]{3,30}$")




def validate_username(value: str) -> None:
    """Basic username validator: 3–30 chars, alnum with _.- allowed."""
    if not _username_re.match(value):
        raise ValidationError("Username must be 3–30 chars and contain only letters, numbers, _ . -")




_url_validator = URLValidator(schemes=["http", "https"]) # strict to web URLs only



def validate_http_url(value: str) -> None:
    """Validate that a string is an HTTP/HTTPS URL."""
    _url_validator(value)  # Raises ValidationError if invalid
