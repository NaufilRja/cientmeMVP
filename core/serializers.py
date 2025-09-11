from rest_framework import serializers
from django.contrib.auth import get_user_model
from reels.models import Reel

User = get_user_model()



# -----------------------
# User Search Serializer
# -----------------------
class UserSearchSerializer(serializers.ModelSerializer):
    """Serializer to return minimal info for user search results."""
    last_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'name', 'avatar', 'last_id']

    def get_last_id(self, obj):
        """Return the ID for cursor pagination."""
        return obj.id



# -----------------------
# Reel Search Serializer
# -----------------------
class ReelSearchSerializer(serializers.ModelSerializer):
    """Serializer to return minimal info for reel search results."""
    user = serializers.SerializerMethodField()
    last_id = serializers.SerializerMethodField()

    class Meta:
        model = Reel
        fields = ['id', 'title', 'user', 'thumbnail', 'last_id']

    def get_user(self, obj):
        """Return minimal user info for the reel's owner."""
        return {
            "id": obj.user.id,
            "username": obj.user.username,
            "avatar": getattr(obj.user.profile, "avatar", None)  # safer access via profile
        }

    def get_last_id(self, obj):
        """Return the ID for cursor pagination."""
        return obj.id