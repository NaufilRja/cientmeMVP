from rest_framework import serializers 
from users.serializers import SimpleUserSerializer, UserSerializer
from .models import Reel, Comment, Share, Audio, Tag
from moviepy.editor import VideoFileClip
from core.constants import MAX_VIDEO_SIZE_MB, MAX_DURATION_SEC
from django.core.exceptions import ValidationError


import os
import tempfile
from django.core.files import File
from PIL import Image 

from django.contrib.auth import get_user_model
User = get_user_model()



# Ensure compatibility with latest Pillow
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS



# ----------------------- 
# Comment Serializer 
# -----------------------
# serializers.py
class CommentSerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer(read_only=True)
    likes_count = serializers.SerializerMethodField()
    replies_count = serializers.SerializerMethodField()
    replies = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    parent = serializers.SerializerMethodField()
    is_deleted = serializers.BooleanField(read_only=True)


    class Meta:
        model = Comment
        fields = [
            "id", "user", "comment", "parent",
            "likes_count", "replies_count", "replies",
            "is_liked",  "is_deleted",
            "created_at", "updated_at"
        ]
        read_only_fields = [
            "user", "likes_count", "replies_count",
            "replies", "is_liked", "is_deleted"
        ]

    def validate(self, attrs):
        if self.instance and self.instance.is_deleted:
            raise serializers.ValidationError("Deleted comments cannot be updated.")
        return attrs


    def get_likes_count(self, obj):
        return obj.likes.count()

    def get_replies_count(self, obj):
        return obj.replies.count()

    def get_is_liked(self, obj):
        user = self.context.get("request").user
        return user in obj.likes.all() if user.is_authenticated else False

    def get_replies(self, obj):
        # Show only first 2-3 replies for top-level comment
        qs = obj.replies.select_related("user").all()[:3]
        return [
            {
                "id": reply.id,
                "user": SimpleUserSerializer(reply.user, context=self.context).data,
                "comment": reply.comment,
                "likes_count": reply.likes.count(),
                "replies_count": reply.replies.count(),
                "is_liked": self.get_is_liked(reply),
                "created_at": reply.created_at,
                "updated_at": reply.updated_at
            }
            for reply in qs
        ]

    def get_parent(self, obj):
        if obj.parent:
            return {
                "id": obj.parent.id,
                "username": obj.parent.user.username,
                "comment": obj.parent.comment[:30],  # preview only
            }
        return None


# -----------------------
# Tag Serializer
# -----------------------
class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug']



# -----------------------
# Reel Serializer
# -----------------------
class ReelSerializer(serializers.ModelSerializer):
    """
    Serializer for Reel model.
    Adds computed fields for likes, saves, shares, comments, and user interactions.
    """

    user = SimpleUserSerializer(read_only=True)
    likes_count = serializers.SerializerMethodField()
    saves_count = serializers.SerializerMethodField()
    shares_count = serializers.SerializerMethodField()
    comments_count = serializers.SerializerMethodField()
    reply_comments_count = serializers.SerializerMethodField()
    comments = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    
    tags = TagSerializer(many=True, read_only=True)  # for read
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(), many=True, write_only=True, source='tags'
    )  # for write/update


    class Meta:
        model = Reel
        fields = [
            "id",
            "title",
            'description', 
            'tags', 
            'tag_ids',
            "user",
            "video",
            "video_size_mb",
            "video_duration",
            "thumbnail",
            "audio",
            "likes_count",
            "saves_count",
            "shares_count",
            "is_liked",
            "is_saved",
            "comments_count",
            "reply_comments_count",
            "comments",
            "views",
            'reach',
            "is_banned",
            "created_at",
        ]
        read_only_fields = [
            "user",
            "video_size_mb",
            "video_duration",
            "thumbnail",
            "likes_count",
            "saves_count",
            "shares_count",
            "is_liked",
            "is_saved",
            "comments_count",
            "reply_comments_count",
            "comments",
            "views",
            'reach',
            "is_banned",
        ]

    # -----------------------
    # Custom getters
    # -----------------------
    def get_likes_count(self, obj):
        return obj.likes.count()

    def get_saves_count(self, obj):
        return obj.saves.count()

    def get_shares_count(self, obj):
        return obj.shares

    def get_is_liked(self, obj):
        user = self.context.get("request").user
        return user.is_authenticated and obj.likes.filter(id=user.id).exists()

    def get_is_saved(self, obj):
        user = self.context.get("request").user
        return user.is_authenticated and obj.saves.filter(id=user.id).exists()

    def get_comments_count(self, obj):
        return obj.comments.filter(parent__isnull=True).count()

    def get_reply_comments_count(self, obj):
        return obj.comments.exclude(parent__isnull=True).count()

    def get_comments(self, obj):
        comments = obj.comments.filter(parent__isnull=True).select_related(
            "user"
        ).prefetch_related("replies", "likes")
        return CommentSerializer(comments, many=True, context=self.context).data
    
    
    def validate_video(self, value):
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as    tmp_file:
            for chunk in value.chunks():
                tmp_file.write(chunk)
            tmp_path = tmp_file.name

        try:
            clip = VideoFileClip(tmp_path)
        except Exception as e:
            raise serializers.ValidationError(f"Cannot read video file: {str(e)}")

        # Trim and compress
        trimmed_path = tmp_path + "_processed.mp4"

        # Resize to 720p max height if needed
        clip_resized = clip.resize(height=720) if clip.h > 720 else clip

        # Cut duration to MAX_DURATION_SEC
        clip_final = clip_resized.subclip(0, min(clip.duration, MAX_DURATION_SEC))

        # Write processed video
        clip_final.write_videofile(
            trimmed_path,
            codec="libx264",
            audio_codec="aac",
            preset="fast",
            bitrate="5000k",  # compress to reduce size
            threads=2,
            logger=None
        )

        # Close clips
        clip.close()
        clip_final.close()

        # Replace original file in the serializer
        value.file.close()
        value.file = open(trimmed_path, "rb")
        value.file = File(value.file)

        # Check final size
        if value.file.size > MAX_VIDEO_SIZE_MB * 1024 * 1024:
            raise serializers.ValidationError(
                f"File too large. Max {MAX_VIDEO_SIZE_MB} MB allowed."
        )

        # Save duration and size in a temporary attribute for later use
        value._processed_duration = min(clip.duration, MAX_DURATION_SEC)
        value._processed_size_mb = round(os.path.getsize(trimmed_path) /    (1024 * 1024), 2)

        return value
    
    
    def create(self, validated_data):
        video_file = validated_data.get('video')
        reel = super().create(validated_data)

        if video_file:
            # Update duration and size using the temporary attributes
            reel.video_duration = getattr(video_file, "_processed_duration", 0)
            reel.video_size_mb = getattr(video_file, "_processed_size_mb", 0)
            reel.save(update_fields=['video_duration', 'video_size_mb'])

        return reel

    
    
# -----------------------
# Reel Update Serializer
# -----------------------
class ReelUpdateSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True, read_only=True)  # for reading tags
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(), 
        many=True, 
        write_only=True, 
        source="tags",
        required=False 
    )  

    class Meta:
        model = Reel
        fields = ["title", "description", "thumbnail", "tags", "tag_ids"] # only safe fields
        read_only_fields = ["video", "reach", "views", "likes", "shares", "is_banned"]    


# -----------------------
# Reel Share Serializer
# -----------------------
class ShareSerializer(serializers.ModelSerializer):
    sharer = UserSerializer(read_only=True)

    class Meta:
        model = Share
        fields = [
            "id", "reel", "sharer", "points_earned", "badge_earned",
            "target_reach", "created_at"
        ]
        read_only_fields = [
            "sharer", "points_earned", "badge_earned",
            "target_reach", "created_at"
        ]

     
     
# -----------------------
# Reel Report Serializer
# -----------------------   
class ReelReportSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=[r[0] for r in Reel.REPORT_REASONS])        
    
    
 
# -----------------------
# Audio Serializer
# -----------------------     
class AudioSerializer(serializers.ModelSerializer):
    created_by = SimpleUserSerializer(read_only=True)
    reels_count = serializers.IntegerField(source="reels.count", read_only=True)

    class Meta:
        model = Audio
        fields = ["id", "title", "file", "duration", "is_from_reel", "reels_count", "created_by", "created_at"]
    


# -----------------------
# Reel Report Serializer
# -----------------------      
class ReelReportSerializer(serializers.Serializer):
    REASONS = [
        ("spam", "Spam"),
        ("inappropriate", "Inappropriate content"),
        ("sexual", "Sexual content"),
        ("harassment", "Harassment or bullying"),
        ("hate_speech", "Hate speech"),
        ("other", "Other"),
    ]
    
    reason = serializers.ChoiceField(choices=REASONS)
    # Optional: for "Other" reason, allow extra text
    other_text = serializers.CharField(required=False, allow_blank=True, max_length=255)    