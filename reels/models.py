from django.db import models
from django.utils.text import slugify
from django.conf import settings
from core.models.base import BaseModel
from core.utils.upload_paths import reel_upload_to, reel_thumbnail_upload_to
from core.mixins.queryset_mixins import ActiveQuerySet, ManagerFromQuerySet
from core.utils.validators import validate_image_file_size, validate_video_file_size
from moviepy.video.io.VideoFileClip import VideoFileClip
import os
from PIL import Image
import numpy as np


User = settings.AUTH_USER_MODEL


# -----------------------
# Tag Model
# -----------------------
class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name




# -----------------------
# Reel Queryset Model
# -----------------------
class ReelQuerySet(models.QuerySet):
    def published(self):
        """Return only published reels"""
        return self.filter(is_published=True)
    
    def trending(self):
        """Example: return reels with views > 1000"""
        return self.filter(views__gt=1000)



# -----------------------
# Reel Model
# -----------------------
class Reel(BaseModel):
    """
    Model representing a short TikTok/Instagram-style reel video.

    Features:
    - Tracks likes, saves, shares, reports, and views.
    - Supports banning/unbanning reels by admins/moderators.
    - Auto compresses video and generates a thumbnail on save.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reels",
        help_text="Owner of the reel"
    )

    title = models.CharField(max_length=200)

    video = models.FileField(
        upload_to=reel_upload_to,
        validators=[validate_video_file_size],
        help_text="Video file up to 15 seconds and 20 MB"
    )

  
    thumbnail = models.ImageField(
        upload_to=reel_thumbnail_upload_to,
        blank=True,
        null=True,
        validators=[validate_image_file_size],
        help_text="Auto-generated thumbnail from video"
    )
    
    audio = models.ForeignKey(
        "reels.Audio",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reels"
    )
    
    
    
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Optional description of the reel"
    )

    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="reels",
        help_text="Optional hashtags for this reel"
    )
    

    likes = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="liked_reels"
    )

    saves = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="saved_reels",
        help_text="Users who saved this reel"
    )

    shares = models.PositiveIntegerField(
        default=0,
        help_text="Increment when reel is shared"
    )

    views = models.PositiveIntegerField(
        default=0,
        help_text="Auto-increment on each view"
    )

    reach = models.PositiveIntegerField(default=0)
    reports = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="reported_reels",
        help_text="Users who reported this reel"
    )

    REPORT_REASONS = [
        ("spam", "Spam or misleading"),
        ("inappropriate", "Inappropriate content"),
        ("other", "Other"),
    ]

    last_report_reason = models.CharField(
        max_length=50,
        choices=REPORT_REASONS,
        blank=True,
        null=True,
        help_text="Stores the last reported reason"
    )

    is_banned = models.BooleanField(
        default=False,
        help_text="Hide this reel if it violates policies"
    )

    objects = ReelQuerySet.as_manager()

    def __str__(self):
        return f"{self.title} by {self.user.username}"

    # -----------------------
    # Moderation helpers
    # -----------------------
    def ban(self):
        """Mark reel as banned."""
        self.is_banned = True
        self.save(update_fields=["is_banned"])

    def unban(self):
        """Unmark reel as banned."""
        self.is_banned = False
        self.save(update_fields=["is_banned"])

    # -----------------------
    # Video/thumbnail utils
    # -----------------------
    def save(self, *args, **kwargs):
        """
        Compress video and generate thumbnail only when video is first uploaded
        or updated. Skip during simple field updates (like shares, likes, etc.).
        """
        update_fields = kwargs.get("update_fields", None)

        super().save(*args, **kwargs)

            # Run compression only if video was added/changed
        if not self.pk or (update_fields and "video" in update_fields):
            if self.video and hasattr(self.video, "path") and os.path.exists(self.video.path):
                self._compress_video()
                # regenerate thumbnail if missing
                if not self.thumbnail:
                    self._generate_thumbnail()
                    

    def _compress_video(self):
        """Compress video file using moviepy, safe version."""
        input_path = self.video.path if self.video else None
        if not input_path or not os.path.exists(input_path):
            return  # skip if missing file

        output_path = f"{os.path.splitext(input_path)[0]}_compressed.mp4"

        try:
            clip = VideoFileClip(input_path)
            clip.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                preset="ultrafast",
                threads=2,  # safer for dev
                logger=None  # suppress noisy ffmpeg logs
            )
            clip.close()

            # Update model field
            self.video.name = os.path.relpath(output_path, settings.MEDIA_ROOT)
            super().save(update_fields=["video"])  # save updated video field only
        except Exception as e:
            # Don’t crash the app if ffmpeg fails
            print(f"Video compression failed: {e}")

    def _generate_thumbnail(self):
        """Generate thumbnail from first frame of video."""
        clip = VideoFileClip(self.video.path)
        frame = clip.get_frame(0)

        im = Image.fromarray(np.uint8(frame))
        thumbnail_path = self.video.path.replace(".mp4", ".jpg")
        im.save(thumbnail_path)

        self.thumbnail.name = os.path.relpath(thumbnail_path, settings.MEDIA_ROOT)
        self.save(update_fields=["thumbnail"])
        
        
# -----------------------
# Comment Model
# -----------------------
class Comment(BaseModel):
    """
    Comments for a reel. Supports replies via `parent`.
    """
    
    reel = models.ForeignKey(
        Reel,
        on_delete=models.CASCADE,
        related_name="comments"
    )
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    
    comment = models.TextField(max_length=500)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="replies",
        on_delete=models.CASCADE
    )
    
    likes = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        blank=True, 
        related_name="liked_comments"
        )
    
  

    def __str__(self):
        return f"Comment by {self.user.username} on {self.reel.title}"
    
    
# -----------------------
# share Model
# -----------------------
class Share(BaseModel):
    """
    Tracks reel sharing and points earned by sharer.
    """
    reel = models.ForeignKey(Reel, on_delete=models.CASCADE, related_name="shares_logs")
    sharer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shared_reels")
    
    target_reach = models.PositiveIntegerField(default=10000)
    points_earned = models.PositiveIntegerField(default=0)
    badge_earned = models.BooleanField(default=False)

    # Engagement scoped to this share
    views = models.PositiveIntegerField(default=0)
    likes = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="liked_shares", blank=True)
    saves = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="saved_shares", blank=True)
    comments = models.ManyToManyField("reels.Comment", related_name="share_comments", blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sharer.username} shared {self.reel.title}"



        
# -----------------------
# Audio Model
# -----------------------
class Audio(models.Model):
    """
    Audio model for reusable sounds in reels.
    - Can come from uploaded file or extracted from another reel.
    - Linked to multiple reels.
    """
    title = models.CharField(max_length=255, blank=True, null=True)
    file = models.FileField(upload_to="reel_audio/", blank=True, null=True)
    duration = models.FloatField(null=True, blank=True, help_text="Duration in seconds")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="audios")
    created_at = models.DateTimeField(auto_now_add=True)
    is_from_reel = models.BooleanField(default=False)

    def __str__(self):
        return self.title or f"Audio {self.id}"

    @property
    def reels_count(self):
        """How many reels are using this audio."""
        return self.reels.count()
    
