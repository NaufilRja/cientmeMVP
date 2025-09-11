"""
core/constants.py
-----------------
Centralized constants used across the project.
Keeps magic numbers, strings, and configuration in one place for reusability.
"""

# -------------------
# User-related
# -------------------
USERNAME_MAX_LENGTH = 30
BIO_MAX_LENGTH = 280
EMAIL_MAX_LENGTH = 254
PASSWORD_MIN_LENGTH = 8

# -------------------
# Media-related
# -------------------
MAX_IMAGE_SIZE_MB = 5       # Maximum image upload size in MB
MAX_VIDEO_SIZE_MB = 50      # Maximum video upload size in MB
ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "gif", "webp"]
ALLOWED_VIDEO_EXTENSIONS = ["mp4", "mov", "avi", "mkv"]

# -------------------
# Pagination
# -------------------
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# -------------------
# Cache & Throttling
# -------------------
CACHE_TIMEOUT_SHORT = 60 * 5       # 5 minutes
CACHE_TIMEOUT_MEDIUM = 60 * 60     # 1 hour
CACHE_TIMEOUT_LONG = 60 * 60 * 24  # 24 hours

# -------------------
# General Choices
# -------------------
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
STATUS_CHOICES = [
    (STATUS_ACTIVE, "Active"),
    (STATUS_INACTIVE, "Inactive"),
]

VISIBILITY_PUBLIC = "public"
VISIBILITY_PRIVATE = "private"
VISIBILITY_FRIENDS = "followers"
VISIBILITY_CHOICES = [
    (VISIBILITY_PUBLIC, "Public"),
    (VISIBILITY_PRIVATE, "Private"),
    (VISIBILITY_FRIENDS, "Followers Only"),
]



# Weights for engagement reach logic
LIKE_WEIGHT, COMMENT_WEIGHT, REPLY_COMMENT_WEIGHT, SHARE_WEIGHT, SAVE_WEIGHT, VIEW_WEIGHT, WATCH_WEIGHT, = 1.5, 3, 4, 6, 5, 0.2, 2