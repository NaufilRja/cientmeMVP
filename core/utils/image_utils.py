# core/utils/image_utils.py

from PIL import Image
from io import BytesIO
from django.core.files.base import ContentFile

def compress_image(image_field, max_size=(600, 600), quality=75):
    """
    Compress and resize an image before saving to storage.

    Args:
        image_field: ImageFieldFile instance from a model
        max_size: (width, height) tuple; maximum dimension
        quality: JPEG compression quality (0-100)

    Returns:
        ContentFile: Compressed image to replace the original
    """
    if not image_field:
        return None

    img = Image.open(image_field)
    img = img.convert("RGB")  # Ensure consistent format
    img.thumbnail(max_size, Image.ANTIALIAS)

    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=quality)
    return ContentFile(buffer.getvalue(), name=image_field.name)
