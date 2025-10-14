from rest_framework import serializers
from django.conf import settings
from django.utils import timezone
from users.serializers import SimpleUserSerializer
from reels.models import Reel
from django.db.models import Q
from core.utils.user_online import is_user_online
from rest_framework import views, permissions
from rest_framework.response import Response



from .models import (
    Game, WinningNumber, GameSubmission, GameHistory, WinnerHistory, GameReward, RewardMessage, RewardChat, GameComplaint 

)


# -----------------------
# Helper function to split comma-separated lists
# -----------------------
def split_comma_field(value):
    """
    If value is a single-item list containing commas, split into a list of strings.
    """
    if isinstance(value, list) and len(value) == 1 and ',' in value[0]:
        return [v.strip() for v in value[0].split(',')]
    return value


# -----------------------
# Simple Reel Serializer 
# -----------------------
class SimpleReelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reel
        fields = ["id", "title", "thumbnail"]  # only fields you need


# -----------------------
# Public Game Serializer 
# -----------------------
class PublicGameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Game
        fields = [
            'public_id',
            'title',
            'description',
            'image',
            'link',
            'reward_type'
        ]  # only safe/public fields


# -----------------------
# Game Serializer (Active Games Only)
# -----------------------
class GameSerializer(serializers.ModelSerializer):
    """
    Serializer for active games that users can participate in.

    Only shows info relevant for ongoing games:
    - Remaining time
    - Participation count
    - Basic game info (title, description, guesses)
    """
    remaining_time = serializers.SerializerMethodField()
    participant_count = serializers.IntegerField(read_only=True)
    is_active = serializers.SerializerMethodField()
    
    # Optional reward_type
    reward_type = serializers.ChoiceField(
        choices=Game.REWARD_TYPE_CHOICES,
        required=False,
        allow_null=True
    )

    # Images and links
    image = serializers.ImageField(required=False, allow_null=True)
    link = serializers.URLField(required=False, allow_null=True)
    first_prize_image = serializers.ImageField(required=True)
    second_prize_image = serializers.ImageField(required=False, allow_null=True)
    third_prize_image = serializers.ImageField(required=False, allow_null=True)

    reel_id = serializers.IntegerField(source='reel.id', read_only=True)
    reel_title = serializers.CharField(source='reel.title', read_only=True)
    reel_username = serializers.CharField(source='reel.user.username', read_only=True)
    
    
    winner_titles = serializers.ListField(
        child=serializers.CharField(max_length=255),
        required=False,
        allow_empty=True
    )
    winner_descriptions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True
    )
    winner_links = serializers.ListField(
        child=serializers.URLField(),
        required=False,
        allow_empty=True
    )
    

    class Meta:
        model = Game
        fields = [
            'id', 'creator', 'title', 'description', 'image', 'link',
            'reward_type', 'number_of_winners',
            'guess_min', 'guess_max', 'reel', 'reel_id', 'reel_title',
            'reel_username',
            'is_active', 'participant_count',
            'duration', 'end_time', 'remaining_time',
            'first_prize_image', 'first_prize_link',
            'second_prize_image', 'second_prize_link',
            'third_prize_image', 'third_prize_link',
            'winner_titles',
            'winner_descriptions',
            'winner_links',
        ]
        
        read_only_fields = [
            'id', 'creator', 'created_at', 'updated_at',
            'end_time', 'remaining_time', 'participant_count',
            'reel_id', 'reel_title', 'is_active'
        ]
        
    
    # --------------------------
    # Winner fields validation (Updated)
    # --------------------------
    def validate_winner_titles(self, value):
        return split_comma_field(value)

    def validate_winner_descriptions(self, value):
        return split_comma_field(value)

    def validate_winner_links(self, value):
        return split_comma_field(value)

    
    # --------------------------
    # Validation
    # --------------------------
    def validate_reel(self, value):
        request_user = self.context['request'].user

        # Only reel owner can attach a game
        if value.user != request_user:
            raise serializers.ValidationError(
                "You can only create a game for your own reel."
            )

        # Ensure one game per reel (on create)
        if self.instance is None and Game.objects.filter(reel=value).exists():
            raise serializers.ValidationError(
                "A game already exists for this reel."
            )

        return value
    

    # --------------------------
    # Custom Methods
    # --------------------------
    def get_remaining_time(self, obj):
        """
        Returns remaining time until game ends.
        """
        if obj.end_time:
            delta = obj.end_time - timezone.now()
            seconds = max(int(delta.total_seconds()), 0)
            readable = str(delta).split('.')[0] if seconds > 0 else "Ended"
            return {"seconds": seconds, "readable": readable}
        return {"seconds": 0, "readable": "Ended"}

    def get_is_active(self, obj):
        """
        Returns dynamic active status (True if game is ongoing).
        """
        return obj.is_active_dynamic  # custom property in model


    # --------------------------
    # Output representation
    # --------------------------
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['winner_titles'] = split_comma_field(data.get('winner_titles', []))
        data['winner_descriptions'] = split_comma_field(data.get('winner_descriptions', []))
        data['winner_links'] = split_comma_field(data.get('winner_links', []))
        return data


# -----------------------
# Winning Number Serializer
# -----------------------
class WinningNumberSerializer(serializers.ModelSerializer):
    winner = SimpleUserSerializer(read_only=True)

    class Meta:
        model = WinningNumber
        fields = [
            'id', 'number', 'reward_description', 'reward_image', 'reward_link',
            'reward_type', 'prize_position', 'winner', 'is_claimed',
        ]
        read_only_fields = ['winner', 'is_claimed']

    def get_winner_username(self, obj):
        return obj.winner.username if obj.winner else None

    def get_winner_avatar(self, obj):
        if obj.winner and getattr(obj.winner, "avatar", None):
            return obj.winner.avatar.url if obj.winner.avatar else None
        return None


# -----------------------
# Game Submission Serializer
# -----------------------
class GameSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GameSubmission
        fields = [
            'id', 'game', 'user', 'guessed_number',
            'submitted_at', 'is_winner', 'prize_position'
        ]
        read_only_fields = ['user', 'submitted_at', 'is_winner', 'prize_position']

    def validate_guessed_number(self, value):
        if not isinstance(value, int):
            raise serializers.ValidationError("Guessed number must be an integer.")

        # Get game instance
        game = self.initial_data.get('game') or getattr(self.instance, 'game', None)
        if not game:
            raise serializers.ValidationError("Game not provided.")

        if isinstance(game, (int, str)):
            try:
                game = Game.objects.get(pk=game)
            except Game.DoesNotExist:
                raise serializers.ValidationError("Invalid game ID.")

        # Check if game is active
        if not game.is_active or (game.end_time and game.end_time <= timezone.now()):
            raise serializers.ValidationError("This game is closed. You cannot submit guesses.")

        # Check number range
        if value < game.guess_min or value > game.guess_max:
            raise serializers.ValidationError(
                f"Number must be between {game.guess_min} and {game.guess_max}."
            )
        return value

    def validate(self, attrs):
        """
        Full object validation: prevent duplicate submissions
        and check if user follows the creator (optional rule)
        """
        user = self.context['request'].user
        game = attrs.get('game')
        
        # 1 Prevent creator participation
        if user == game.creator:
            raise serializers.ValidationError(
                {"non_field_errors": ["Creators cannot participate in their own game."]}
            )

        # 2 Prevent duplicate submission
        if GameSubmission.objects.filter(game=game, user=user).exists():
            raise serializers.ValidationError(
                {"non_field_errors": ["You have already submitted."]}
            )

        # 3 followers-only participation
        if hasattr(game.creator, 'profile'):
            if user not in game.creator.profile.followers.all():
                raise serializers.ValidationError(
                    {"non_field_errors": ["You must follow the creator to participate in this game."]}
                )

        return attrs


    def create(self, validated_data):
        # Create submission
        submission = GameSubmission.objects.create(
            game=validated_data['game'],
            guessed_number=validated_data['guessed_number'],
            user=validated_data.get('user'),  # user must be passed from perform_create
            submitted_at=validated_data.get('submitted_at', timezone.now())
        )

        # Check if guessed number is a winning number and unclaimed
        guessed_number = validated_data['guessed_number']
        game = validated_data['game']

        winning_number_obj = game.winning_numbers.filter(
            number=guessed_number,
            winner__isnull=True  # Correct field to check availability
        ).first()

        if winning_number_obj:
            submission.mark_winner(position=winning_number_obj.prize_position)

        return submission


    def to_representation(self, instance):
        return {
            "id": instance.id,
            "guessed_number": instance.guessed_number,
            "is_winner": instance.is_winner,
            "prize_position": instance.prize_position
        }



# -----------------------
# Late Guees Serializer
# -----------------------
class LateGuessSerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer(read_only=True)

    class Meta:
        model = GameSubmission
        fields = ["id", "user", "guessed_number", "submitted_at"]


   
   
# -----------------------------
# Public Winner History Serializer
# ------------------------------
class PublicWinnerSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username")
    avatar = serializers.ImageField(source="user.avatar", allow_null=True)

    class Meta:
        model = WinnerHistory
        fields = ["id", "username", "avatar", "prize_position", "number"]
   
  
  

# -----------------------------
# Public Game History Serializer
# ------------------------------
class PublicGameHistorySerializer(serializers.ModelSerializer):
    winner = SimpleUserSerializer(read_only=True)
    game_title = serializers.CharField(source='game.title', read_only=True)
    reward_description = serializers.SerializerMethodField()

    
    class Meta:
        model = GameHistory
        fields = [
            'public_id',
            'game_title',
            'winner',
            'reward_description',
        ]

    def get_reward_description(self, obj):
        # obj is GameHistory instance
        first_winner = obj.winners.first()  # 'winners' is the related_name in WinnerHistory
        if first_winner:
            return first_winner.reward_description or ""
        return ""
    
      
   

# ----------------------------------------------------
# Game History Serializer (Completed / Past Games)
# ----------------------------------------------------
class GameHistorySerializer(serializers.ModelSerializer):
    """
    Serializer for closed/completed games.

    Includes full details:
    - Winning numbers
    - All winners
    - Late correct guesses
    - Encrypted winning numbers
    """
    decrypted_winning_numbers = serializers.SerializerMethodField()
    late_correct_guesses = serializers.SerializerMethodField()
    all_winners = PublicWinnerSerializer(source="winners", many=True, read_only=True)
    creator = SimpleUserSerializer(read_only=True)   # nested user info
    reel = SimpleReelSerializer(read_only=True)      # nested reel info (if you have a ree


    class Meta:
        model = GameHistory
        fields = [
            "id",
            "public_id",
            "game",
            "creator",
            "reel",
            "title",
            "description",
            "reward_type",
            "number_of_winners",
            "guess_min",
            "guess_max",
            "created_at",
            "completed_at",
            "updated_at",
            "decrypted_winning_numbers",
            "late_correct_guesses",
            "all_winners",
        ]
        read_only_fields = fields
    # --------------------------
    # Decrypt winning numbers
    # --------------------------
    def get_decrypted_winning_numbers(self, obj):
        """
        Convert the stored string (e.g., "1,2,3") into a list of dicts:
        [{"number":1}, {"number":2}, ...]
        """
        if obj.decrypted_winning_numbers:
            try:
                numbers = [int(n) for n in obj.decrypted_winning_numbers.split(",") if n]
                return [{"number": n} for n in numbers]
            except Exception:
                return []
        return []



    # --------------------------
    # Late correct guesses
    # --------------------------
    def get_late_correct_guesses(self, obj):
        """
        Return submissions that guessed correctly but weren't winners.
        """
        game = obj.game
        if not game.winners_selected:
            return []

        winning_numbers = list(game.winning_numbers.values_list("number", flat=True))
        winning_user_ids = list(game.winning_numbers.values_list("winner_id", flat=True))

        late_submissions = game.submissions.filter(
            guessed_number__in=winning_numbers
        ).exclude(user_id__in=winning_user_ids)

        return LateGuessSerializer(
            late_submissions.order_by("submitted_at"),
            many=True,
            context=self.context
        ).data


    
# ------------------
# simple Serializer
# ------------------
class SimpleGameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Game
        fields = ["id", "title", "description"]  # keep it light



# ----------------------------------
# Public Winner History Serializers
# ----------------------------------

class PublicWinnerSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username")
    
    class Meta:
        model = WinnerHistory
        fields = ["id", "username", "prize_position", "reward_type"]

   
    
# -----------------------
# Winner History Serializer
# -----------------------
class WinnerHistorySerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer(read_only=True)
    game = SimpleGameSerializer(source="game_history.game", read_only=True)
    can_message = serializers.ReadOnlyField()
    forfeited = serializers.ReadOnlyField()
    reward_received = serializers.ReadOnlyField()
    received_at = serializers.ReadOnlyField()
    

    minimal_fields = ["user", "prize_position", "number"]
    
    winner_status = serializers.SerializerMethodField()
    creator_status = serializers.SerializerMethodField()

    class Meta:
        model = WinnerHistory
        fields = [
            "id",
            "game",
            "user",
            "number",
            "can_message",
            "prize_position",
            "reward_type",
            "reward_description",
            "reward_image",
            "reward_link",
            "claimed_at",
            "claim_deadline",
            "reward_received",
            "received_at",
            "reward_delivery_deadline",
            "forfeited",
            "winner_status",
            "creator_status",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        """
        Dynamic field visibility based on user role:
        - Creator → full info
        - Winner (self) → full info of self
        - Other authenticated → minimal info
        - Unauthenticated → "login required" message
        """
        request = self.context.get("request")
        user = getattr(request, "user", None)
        data = super().to_representation(instance)

        if not user or not user.is_authenticated:
            return {"detail": "You must be logged in to view winner history."}

        is_creator = instance.game_history.game.creator == user
        is_self_winner = instance.user == user

        if is_creator or is_self_winner:
            return data  # full info
        else:
            # minimal info for other authenticated users
            return {k: v for k, v in data.items() if k in self.minimal_fields}
        
        
    def get_winner_status(self, obj):
        if obj.reward_received:
            return "Received / Completed"
        elif obj.reward_delivered:
            return "Waiting for confirmation"
        elif obj.is_claimed:
            return "Claimed"
        return "Pending"

    def get_creator_status(self, obj):
        if obj.reward_received:
            return "Completed / Received"
        elif obj.reward_delivered:
            return "Delivered / Sent"
        elif obj.is_claimed:
            return "Winner has claimed"
        return "Pending"    



# -----------------------
# Game Reward Serializer
# -----------------------
class GameRewardSerializer(serializers.ModelSerializer):
    game_title = serializers.CharField(source='game.title', read_only=True)
    
    # Ensure reward_title is always mandatory
    reward_title = serializers.CharField(required=True)

    class Meta:
        model = GameReward
        fields = [
            'id',
            'game',
            'game_title',  # read-only
            'position',
            'reward_type',
            'reward_title',  # mandatory
            'reward_description',
            'reward_link',
            'is_claimed',
            'claimed_at',
        ]
        read_only_fields = ['is_claimed', 'claimed_at']  # Only modifiable internally



# ---------------------------
# Claimed Winner Serializer
# ---------------------------
class ClaimedWinnerSerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer(read_only=True)  # use your existing serializer
    game_title = serializers.CharField(source="game.title", read_only=True)
    reward_info = serializers.SerializerMethodField()
    is_messaged = serializers.SerializerMethodField()

    class Meta:
        model = WinnerHistory
        fields = [
            "id",
            "user",             # full user info via SimpleUserSerializer
            "game_title",
            "reward_info",
            "claimed_at",
            "is_messaged",
        ]

    def get_reward_info(self, obj):
        info = f"Prize: {obj.reward_description or 'N/A'}, Position: {obj.prize_position}"
        return info

    def get_is_messaged(self, obj):
        return RewardChat.objects.filter(
            creator=obj.game_history.creator, winner=obj.user
        ).exists()





# ---------------------------
# Reward Message Serializer 
# ---------------------------
class RewardMessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.SerializerMethodField()
    reward_chat_id = serializers.IntegerField(source='reward_chat.id', read_only=True)
    winner_history_id = serializers.IntegerField(source='winner_history.id', read_only=True)

    class Meta:
        model = RewardMessage
        fields = [
            "id",
            "message",
            "sender",
            "sender_username",
            "image",
            "created_at",
            "is_system_message",
            "reward_chat_id",
            "winner_history_id",
        ]
        read_only_fields = [
            "id", "created_at", "sender", "sender_username",
            "is_system_message", "reward_chat_id", "winner_history_id"
        ]

    def get_sender_username(self, obj):
        if obj.is_system_message:
            return obj.winner_history.user.username if obj.winner_history else "System"
        return obj.sender.username if obj.sender else "Unknown"

    def validate(self, attrs):
        request_user = self.context['request'].user
        data = self.context['request'].data
        game_history_id = data.get('game_history')

        if not game_history_id:
            raise serializers.ValidationError({"game_history": "GameHistory must be provided."})

        # Fetch the game history
        try:
            game_history = GameHistory.objects.get(id=game_history_id)
        except GameHistory.DoesNotExist:
            raise serializers.ValidationError({"game_history": "GameHistory not found."})

        # Determine WinnerHistory
        if request_user == game_history.creator:
            # Creator sending → either use winner_id or auto-pick latest claimed
            winner_id = data.get('winner_id')
            if winner_id:
                wh = WinnerHistory.objects.filter(game_history=game_history, user_id=winner_id).first()
                if not wh:
                    raise serializers.ValidationError({"winner_history": "WinnerHistory not found for this winner and game!"})
            else:
                # Auto-fetch latest claimed winner who hasn't received reward
                wh = WinnerHistory.objects.filter(
                    game_history=game_history,
                    is_claimed=True,
                    reward_received=False
                ).order_by('-claimed_at').first()

                if not wh:
                    raise serializers.ValidationError({"winner_history": "No claimed winner available for messaging."})
        else:
            # Winner sending → their own WinnerHistory
            wh = WinnerHistory.objects.filter(game_history=game_history, user=request_user).first()
            if not wh:
                raise serializers.ValidationError({"winner_history": "WinnerHistory not found for this user and game!"})

        wh.refresh_from_db()
        now = timezone.now()

        # Messaging permission checks
        if not wh.is_claimed:
            raise serializers.ValidationError({"non_field_errors": ["Messaging not allowed until reward is claimed."]})
        if wh.reward_delivery_deadline and now > wh.reward_delivery_deadline:
            raise serializers.ValidationError({"non_field_errors": ["Messaging period expired."]})
        if wh.reward_received:
            raise serializers.ValidationError({"non_field_errors": ["Cannot send messages after reward confirmed."]})

        # Get or create chat
        chat, _ = RewardChat.objects.get_or_create(
            creator=game_history.creator,
            winner=wh.user,
            defaults={'is_active': True}
        )

        if not chat.is_active:
            raise serializers.ValidationError({"non_field_errors": ["Messaging is no longer allowed."]})

        attrs['winner_history'] = wh
        attrs['reward_chat'] = chat
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data['sender'] = request.user

        instance = super().create(validated_data)

        # Deliver message & update chat status
        receiver = instance.reward_chat.winner if instance.sender == instance.reward_chat.creator else instance.reward_chat.creator
        if is_user_online(receiver):
            instance.is_delivered = True
            instance.save(update_fields=["is_delivered"])

        instance.reward_chat.last_message_status = "double" if instance.is_delivered else "single"
        instance.reward_chat.save(update_fields=["last_message_status"])

        return instance

   
# ---------------------------
# Chat List Serializer (Fixed)
# ---------------------------
class ChatListSerializer(serializers.ModelSerializer):
    other_user = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    last_message_time = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    last_message_status = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = RewardChat
        fields = [
            "id",
            "other_user",
            "last_message",
            "last_message_time",
            "unread_count",
            "last_message_status",
            "is_active",
        ]

    def get_other_user(self, obj):
        request_user = self.context["request"].user
        other = obj.winner if obj.creator == request_user else obj.creator
        profile = getattr(other, "profile", None)
        return {
            "id": other.id,
            "username": other.username,
            "avatar": profile.avatar.url if profile and profile.avatar else None,
            "is_online": is_user_online(other) if profile else False,
        }

    def get_last_message(self, obj):
        last_msg = obj.messages.order_by("-created_at").first()
        if not last_msg:
            return "No messages yet"  # 👈 Show this only if no messages exist
        if last_msg.message:
            return last_msg.message[:50]  # Limit to first 50 chars
        elif last_msg.image:
            return "📷 Image"
        else:
            return "No messages yet"

    def get_last_message_time(self, obj):
        last_msg = obj.messages.all().order_by("-created_at").first()
        return last_msg.created_at if last_msg else None

    def get_unread_count(self, obj):
        request_user = self.context["request"].user
        return obj.messages.exclude(sender=request_user).filter(is_read=False).count()

    def get_last_message_status(self, obj):
        request_user = self.context["request"].user
        last_msg = obj.messages.order_by("-created_at").first()

        if not last_msg or last_msg.sender != request_user:
            return None

        receiver = obj.winner if request_user == obj.creator else obj.creator

        # Single / double / seen
        if last_msg.is_read:
            return "seen"
        elif last_msg.is_delivered:  # <-- use delivered flag
            return "double"
        else:
            return "single"


    def get_is_active(self, obj):
        return obj.is_active



# -----------------------
# Game Complaint Serializer
# -----------------------
class GameComplaintSerializer(serializers.ModelSerializer):
    """
    Serializer for Complaint model.
    
    Rules:
    - Any winner can create a complaint about their reward.
    - Winners can only edit the description while complaint status is still 'open'.
    - Only staff/admin users can change the complaint status (open → resolved/rejected).
    """

    class Meta:
        model = GameComplaint
        fields = [
            "id",
            "winner_history",
            "user",
            "description",
            "status",
            "created_at",
            "updated_at",
        ]
        # Auto-managed fields should not be edited directly
        read_only_fields = ["id", "user", "created_at", "updated_at"]

    def update(self, instance, validated_data):
        """
        Custom update logic:
        - Staff can update complaint status.
        - Normal users cannot update status.
        - Normal users can update complaint description only if complaint is still open.
        """
        user = self.context["request"].user

        # Prevent normal users from updating status
        if "status" in validated_data:
            if not user.is_staff:
                raise serializers.ValidationError(
                    "Only staff can change the complaint status."
                )

        # Prevent users from editing description after complaint is closed
        if "description" in validated_data:
            if instance.status != "open":
                raise serializers.ValidationError(
                    "You cannot edit a complaint once it is resolved or rejected."
                )

        return super().update(instance, validated_data)
