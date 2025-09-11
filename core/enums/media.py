from __future__ import annotations
from enum import Enum




class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"




class AudioSource(str, Enum):
    UPLOAD = "upload" # user uploaded file
    EXTERNAL = "external" # remote URL
    GENERATED = "generated" # programmatic/AI generated




# Django model `choices` helpers (tuple of tuples)
MEDIA_TYPE_CHOICES = tuple((m.value, m.name.title()) for m in MediaType)
AUDIO_SOURCE_CHOICES = tuple((a.value, a.name.title()) for a in AudioSource)