from rest_framework import serializers
from django.contrib.auth import get_user_model
from reels.models import Reel

User = get_user_model()


# -----------------------
# User Search Serializer
# -----------------------
class UserSearchSerializer(serializers.ModelSerializer):
    last_id = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'name', 'avatar_url', 'last_id']

    def get_last_id(self, obj):
        return obj.id

    def get_avatar_url(self, obj):
        request = self.context.get('request')
        if hasattr(obj, 'profile') and obj.profile.avatar:
            return request.build_absolute_uri(obj.profile.avatar.url)
        return None


# -----------------------
# Reel Search Serializer
# -----------------------
class ReelSearchSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    last_id = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = Reel
        fields = ['id', 'title', 'user', 'thumbnail_url', 'last_id']

    def get_user(self, obj):
        request = self.context.get('request')
        avatar_url = None
        if hasattr(obj.user, 'profile') and obj.user.profile.avatar:
            avatar_url = request.build_absolute_uri(obj.user.profile.avatar.url)
        return {
            "id": obj.user.id,
            "username": obj.user.username,
            "avatar": avatar_url
        }

    def get_last_id(self, obj):
        return obj.id

    def get_thumbnail_url(self, obj):
        request = self.context.get('request')
        if obj.thumbnail:
            return request.build_absolute_uri(obj.thumbnail.url)
        return None
