from rest_framework import serializers
from django.conf import settings
from django.utils import timezone
from .models import (
    Game, WinningNumber, GameSubmission, GameHistory, WinnerHistory, RewardMessage, GameComplaint

)


# -----------------------
# Game Serializer
# -----------------------
class GameSerializer(serializers.ModelSerializer):
    remaining_time = serializers.SerializerMethodField()
    winning_numbers = serializers.SerializerMethodField()
    participant_count = serializers.IntegerField(read_only=True)
    is_finished = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    late_correct_guesses = serializers.SerializerMethodField()
    all_winners = serializers.SerializerMethodField()
    
    # -----------------------
    # Optional reward_type
    # -----------------------
    reward_type = serializers.ChoiceField(
        choices=Game.REWARD_TYPE_CHOICES,
        required=False,    # optional
        allow_null=True    # allow null
    )
    
    # Make image optional
    image = serializers.ImageField(required=False, allow_null=True)
    link = serializers.URLField(required=False, allow_null=True)
    first_prize_image = serializers.ImageField(required=True)
    second_prize_image = serializers.ImageField(required=False, allow_null=True)
    third_prize_image = serializers.ImageField(required=False, allow_null=True)

    reel_id = serializers.IntegerField(source='reel.id', read_only=True)
    reel_title = serializers.CharField(source='reel.title', read_only=True)

    

    class Meta:
        model = Game
        fields = [
            'id', 'creator', 'title', 'description', 'image', 'link',
            'reward_type', 'number_of_winners',
            'guess_min', 'guess_max', 'reel', 'reel_id', 'reel_title','is_active', 'participant_count',
            'winning_numbers', 'duration', 'end_time', 'remaining_time', 'created_at', 
            'updated_at', 'salt', 'hash_value', 'winning_numbers_encrypted', 'is_finished',
            'auto_close', 'auto_select_winner', 'winners_selected',
            'first_prize_image', 'first_prize_link',
            'second_prize_image', 'second_prize_link',
            'third_prize_image', 'third_prize_link',
            "late_correct_guesses",'all_winners',  
        ]
        read_only_fields = [
            'id', 'creator', 'created_at', 'updated_at', 'end_time', 'remaining_time',
            'salt', 'hash_value', 'winning_numbers_encrypted', 'participant_count',
            'is_finished', "auto_close", "auto_select_winner", 'winners_selected', 'is_active',
            'reel_id', 'reel_title', "late_correct_guesses",'all_winners',  
        ]

    # -----------------------
    # Custom validation
    # -----------------------
    def validate(self, attrs):
        # Only enforce required fields on create
        if not self.instance:  # create
            if not attrs.get('title'):
                raise serializers.ValidationError("Game title is required.")
            if not attrs.get('description'):
                raise serializers.ValidationError("Game description is required.")
            if not attrs.get('first_prize_image'):
                raise serializers.ValidationError("First prize image is required.")

        guess_min = attrs.get('guess_min')
        guess_max = attrs.get('guess_max')
        if guess_min is not None and guess_min <= 0:
            raise serializers.ValidationError("'guess_min' must be > 0.")
        if guess_min is not None and guess_max is not None and guess_max <= guess_min:
            raise serializers.ValidationError("'guess_max' must be > 'guess_min'.")

        number_of_winners = attrs.get('number_of_winners')
        if number_of_winners is not None and number_of_winners < 1:
            raise serializers.ValidationError("'number_of_winners' must be at least 1.")

        return attrs


    # ---------------------------------------
    # validation for reel and game one to one
    # ---------------------------------------
    def validate_reel(self, value):
        if value and Game.objects.filter(reel=value).exists():
            raise serializers.ValidationError("This reel is already attached to another game.")
        return value

    # -----------------------
    # Optional link validation
    # -----------------------
    def validate_link(self, value):
        if value and not (value.startswith("http://") or value.startswith("https://")):
            raise serializers.ValidationError("Link must start with http:// or https://")
        return value

    # -----------------------
    # Create Game Method
    # -----------------------
    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['creator'] = request.user
        return super().create(validated_data)


    # --------------------
    # Update Game Method
    # --------------------
    def update(self, instance, validated_data):
        if instance.submissions.exists():
            restricted_fields = [
                'title', 'description', 'image', 'reward_type', 'link',
                'number_of_winners', 'guess_min', 'guess_max'
            ]
            for field in restricted_fields:
                if field in validated_data:
                    raise serializers.ValidationError(
                        f"Cannot update '{field}' because participants have submitted guesses."
                    )
        return super().update(instance, validated_data)

    # -----------------------
    # Custom Methods
    # -----------------------
    def get_winning_numbers(self, obj):
        """
        Returns the actual winning numbers, regardless of whether winners are selected.
        """
        if obj.winning_numbers_encrypted:
            try:
                # decrypt the numbers
                from cryptography.fernet import Fernet
                key = settings.GAME_ENCRYPTION_KEY  # your secret key
                f = Fernet(key)
                decrypted = f.decrypt(obj.winning_numbers_encrypted.encode()).decode()
                # assume stored as comma-separated string: "1,2,3"
                numbers = [int(n) for n in decrypted.split(',')]
                return [{"number": n} for n in numbers]
            except Exception as e:
                return []  # fail silently if decrypt fails
        return []

    
    # -------------------------------
    # Get Late Correct Guess Methods
    # ------------------------------
    def get_late_correct_guesses(self, obj):
        """
        Return submissions where users guessed correctly
        but didn't win (guessed later than the actual winners).
        """
        if not obj.winners_selected:
            return []

        # pull the official winning numbers directly from WinningNumber table
        winning_numbers = list(obj.winning_numbers.values_list("number", flat=True))

        # collect IDs of actual winners
        winning_user_ids = list(obj.winning_numbers.values_list("winner_id", flat=True))

        # find submissions that guessed correctly but were not winners
        late_submissions = obj.submissions.filter(
            guessed_number__in=winning_numbers
        ).exclude(user_id__in=winning_user_ids)

        return LateGuessSerializer(
            late_submissions.order_by("submitted_at"),  # optional: sort by submission time
            many=True,
            context=self.context
        ).data


    # -----------------------
    # Get All Winners Methods
    # -----------------------
    def get_all_winners(self, obj):
        """
        Returns all winners grouped by prize position
        """
        winners_qs = obj.winning_numbers.filter(winner__isnull=False)
        return [
            {
                "id": wn.winner.id,
                "username": wn.winner.username,
                "avatar": wn.winner.avatar.url if wn.winner.avatar else None,
                "winning_number": wn.number,
                "prize_position": wn.prize_position,
            }
            for wn in winners_qs
        ]



    # --------------------------
    # Get Remaining Time Methods
    # --------------------------
    def get_remaining_time(self, obj):
        if obj.end_time:
            delta = obj.end_time - timezone.now()
            seconds = max(int(delta.total_seconds()), 0)
            readable = str(delta).split('.')[0] if seconds > 0 else "Ended"
            return {"seconds": seconds, "readable": readable}
        return {"seconds": 0, "readable": "Ended"}


     # --------------------------
    # Get Is Finished Methods
    # --------------------------
    def get_is_finished(self, obj):
        if obj.end_time:
            return timezone.now() >= obj.end_time
        return False 
    
     
    # --------------------------
    # Get Is Active Methods
    # --------------------------
    def get_is_active(self, obj):
        return obj.is_active_dynamic




# -----------------------
# Winning Number Serializer
# -----------------------
class WinningNumberSerializer(serializers.ModelSerializer):
    winner_username = serializers.SerializerMethodField()
    winner_avatar = serializers.SerializerMethodField()

    class Meta:
        model = WinningNumber
        fields = [
            'id', 'number', 'reward_description', 'reward_image', 'reward_link',
            'reward_type', 'prize_position', 'winner',
            'winner_username', 'winner_avatar', 'is_claimed',
        ]
        read_only_fields = ['winner', 'winner_username', 'winner_avatar', 'is_claimed']

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
    username = serializers.CharField(source="user.username", read_only=True)
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = GameSubmission
        fields = ["id", "username", "avatar", "guessed_number", "submitted_at"]

    def get_avatar(self, obj):
        return obj.user.avatar.url if obj.user and getattr(obj.user, "avatar", None) else None



# -----------------------
# Game History Serializer
# -----------------------
class GameHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = GameHistory
        fields = [
            'id',
            'updated_at',
            'is_active',
            'title',
            'description',
            'reward_type',
            'number_of_winners',
            'guess_min',
            'guess_max',
            'created_at',
            'completed_at',
            'decrypted_winning_numbers',
            'game',
            'creator',
            'reel',
        ]
        read_only_fields = fields  # all fields are read-only
        
        
# -----------------------
# Winner History Serializer
# -----------------------
class WinnerHistorySerializer(serializers.ModelSerializer):
    user_username = serializers.SerializerMethodField()
    game_title = serializers.CharField(source="game_history.title", read_only=True)
    can_message = serializers.ReadOnlyField()
    forfeited = serializers.ReadOnlyField()  

    class Meta:
        model = WinnerHistory
        fields = [
            'id',
            'game_history',
            'game_title',
            'user',
            'user_username',
            'number',
            'can_message',
            'prize_position',
            'reward_type',
            'reward_description',
            'reward_image',
            'reward_link',
            'claimed_at',
            'claim_deadline',
            'reward_delivery_deadline',
            'forfeited',
        ]
        read_only_fields = [
            'id',
            'game_history',
            'game_title',
            'user',
            'user_username',
            'prize_position',
            'claimed_at',
            'claim_deadline',
            'reward_delivery_deadline',
            'forfeited',
        ]

    def get_user_username(self, obj):
        return obj.user.username if obj.user else None
    
    def get_can_message(self, obj):
        return obj.can_message 


# -----------------------
# RewardMessage Serializer
# -----------------------
class RewardMessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source='sender.username', read_only=True)

    class Meta:
        model = RewardMessage
        fields = [
            "id",
            "winner_history",
            "sender",
            "sender_username",
            "message",
            "image",
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "sender", "sender_username"]

    def validate(self, attrs):
        wh = attrs.get("winner_history")
        if wh:
            now = timezone.now()
            allowed_until = wh.reward_delivery_deadline or wh.claim_deadline
            if not allowed_until or now > allowed_until:
                raise serializers.ValidationError("Messaging period has expired.")
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["sender"] = request.user
        return super().create(validated_data)




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
