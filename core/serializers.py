from rest_framework import serializers
from django.contrib.auth import get_user_model
from reels.models import Reel
from games.models import GameHistory, WinnerHistory, RewardMessage
from users.serializers import SimpleUserSerializer

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



# --------------------------------
# Game History Search Serializer
# --------------------------------
class GameHistorySearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = GameHistory
        fields = ['id', 'title', 'description', 'reward_type', 'created_at', 'number_of_winners']



# --------------------------------
# Winner History Search Serializer
# --------------------------------
class WinnerHistorySearchSerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer(read_only=True)

    class Meta:
        model = WinnerHistory
        fields = ['id', 'user', 'prize_position']



