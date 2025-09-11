from rest_framework import serializers 
from users.serializers import SimpleUserSerializer, UserSerializer
from .models import Reel, Comment, Share, Audio
from moviepy.video.io.VideoFileClip import VideoFileClip
from rest_framework.exceptions import ValidationError

import os
from django.contrib.auth import get_user_model
User = get_user_model()




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

    class Meta:
        model = Reel
        fields = [
            "id",
            "title",
            "user",
            "video",
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
    
    
    def _validate_video_duration(self):
        """Check that video duration does not exceed 15 seconds."""
        video_path = self.video.path

        clip = None
        try:
            clip = VideoFileClip(video_path)
        except Exception as e:
            raise ValidationError({"video": f"Cannot read video file: {str(e)}"})

        if clip.duration > 15:
            clip.close()
            # Optionally delete the file
            if os.path.exists(video_path):
                os.remove(video_path)
            raise ValidationError({"video": "Video cannot exceed 15 seconds."})

        clip.close()
    
    
# -----------------------
# Reel Share Serializer
# -----------------------
class ShareSerializer(serializers.ModelSerializer):
    sharer = UserSerializer(read_only=True)
    
    class Meta:
        model = Share
        fields = ["id", "reel", "sharer", "points_earned", "badge_earned", "target_reach", "created_at"]
        read_only_fields = ["sharer", "points_earned", "badge_earned", "target_reach", "created_at"]
        
        
     
     
# -----------------------
# Reel Report Serializer
# -----------------------   
class ReelReportSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=[r[0] for r in Reel.REPORT_REASONS])        
    
    
 
# -----------------------
# Audio Serializer
# -----------------------     
class AudioSerializer(serializers.ModelSerializer):
    reels_count = serializers.IntegerField(source="reels.count", read_only=True)

    class Meta:
        model = Audio
        fields = ["id", "title", "file", "duration", "is_from_reel", "reels_count", "created_by", "created_at"]
    