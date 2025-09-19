from rest_framework import serializers
from .services.game_fairness import GameFairness
from django.utils import timezone

from .models import ( Game, WinningNumber, GameSubmission, GameHistory, WinnerHistory)


class GameSerializer(serializers.ModelSerializer):
    remaining_time = serializers.SerializerMethodField()
    winning_numbers = serializers.SerializerMethodField()
    participant_count = serializers.IntegerField(read_only=True)  # Only one field, simplified

    class Meta:
        model = Game
        fields = [
            'id', 'creator', 'title', 'description', 'image', 'link', 'reward_type',
            'number_of_winners', "guess_min", "guess_max", 'reel', 'is_active',
            'participant_count', 'winning_numbers', 'duration', 'end_time', 
            'remaining_time', 'created_at', 'updated_at', 'salt', 'hash_value', 
            'winning_numbers_encrypted',
        ]
        read_only_fields = [
            'id', 'creator', 'created_at', 'updated_at', 'end_time', 'remaining_time',
            'salt', 'hash_value', 'winning_numbers_encrypted',
            'participant_count',
        ]

    def validate(self, attrs):
        if not any([attrs.get('description'), attrs.get('image'), attrs.get('link')]):
            raise serializers.ValidationError("At least one of 'description', 'image', or 'link' must be provided.")
        guess_min = attrs.get('guess_min')
        guess_max = attrs.get('guess_max')
        if guess_min <= 0:
            raise serializers.ValidationError("'guess_min' must be > 0.")
        if guess_max <= guess_min:
            raise serializers.ValidationError("'guess_max' must be > 'guess_min'.")
        if attrs.get('number_of_winners', 0) < 1:
            raise serializers.ValidationError("'number_of_winners' must be at least 1.")
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['creator'] = request.user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if instance.submissions.exists():
            restricted_fields = ['title', 'description', 'image', 'reward_type', 'link', 'number_of_winners', 'guess_min', 'guess_max']
            for field in restricted_fields:
                if field in validated_data:
                    raise serializers.ValidationError(f"Cannot update '{field}' because participants have submitted guesses.")
        return super().update(instance, validated_data)

    def get_winning_numbers(self, obj):
        if obj.winning_numbers_encrypted and obj.end_time and timezone.now() >= obj.end_time:
            try:
                decrypted = GameFairness.decrypt_numbers(obj.winning_numbers_encrypted)
                return list(map(int, decrypted.split('-')))
            except Exception:
                return []  # Safe fallback if encryption is invalid
        return []

    def get_remaining_time(self, obj):
        if obj.end_time and timezone.now() < obj.end_time:
            delta = obj.end_time - timezone.now()
            return {"seconds": int(delta.total_seconds()), "readable": str(delta).split('.')[0]}
        return {"seconds": 0, "readable": "Ended"}


# -----------------------
# Winning Number Serializer
# -----------------------
class WinningNumberSerializer(serializers.ModelSerializer):
    """
    Serializer for WinningNumber model.
    Shows number, reward info, and winner if claimed.
    """
    winner_username = serializers.SerializerMethodField()

    class Meta:
        model = WinningNumber
        fields = [
            'id', 'number', 'reward_description', 'reward_image', 'reward_link',
            'reward_type', 'prize_position', 'winner', 'winner_username', 'is_claimed'
        ]
        read_only_fields = ['winner', 'winner_username', 'is_claimed']

    def get_winner_username(self, obj):
        return obj.winner.username if obj.winner else None


class GameSubmissionSerializer(serializers.ModelSerializer):
    """
    Serializer for GameSubmission.
    Ensures user guesses only once and marks winners.
    """
    class Meta:
        model = GameSubmission
        fields = [
            'id', 'game', 'user', 'guessed_number',
            'submitted_at', 'is_winner', 'prize_position'
        ]
        read_only_fields = ['user', 'submitted_at', 'is_winner', 'prize_position']

    def validate_guessed_number(self, value):
        """Ensure the guess is within the game's min/max range."""
        game = self.initial_data.get('game') or getattr(self.instance, 'game', None)

        if not game:
            raise serializers.ValidationError("Game not provided.")

        # Convert ID to Game object safely
        if isinstance(game, (int, str)):
            try:
                game = Game.objects.get(pk=game)
            except Game.DoesNotExist:
                raise serializers.ValidationError("Invalid game ID.")

        if value < game.guess_min or value > game.guess_max:
            raise serializers.ValidationError(
                f"Number must be between {game.guess_min} and {game.guess_max}."
            )
        return value

    def create(self, validated_data):
        """Assign user, check uniqueness, and mark winner if applicable."""
        user = self.context['request'].user
        game = validated_data['game']
        guessed_number = validated_data['guessed_number']

        # Only one submission per user/game
        if GameSubmission.objects.filter(user=user, game=game).exists():
            raise serializers.ValidationError("You have already submitted a guess for this game.")

        submission = GameSubmission.objects.create(user=user, **validated_data)

        # Check winning numbers
        winning_number_obj = game.winning_numbers.filter(
            number=guessed_number, is_claimed=False
        ).first()
        if winning_number_obj:
            submission.mark_winner(position=winning_number_obj.prize_position)

        return submission


# -----------------------
# Game History Serializer
# -----------------------
class GameHistorySerializer(serializers.ModelSerializer):
    """
    Serializer for immutable game history.
    """
    class Meta:
        model = GameHistory
        fields = '__all__'
        read_only_fields = '__all__'


# -----------------------
# Winner History Serializer
# -----------------------
class WinnerHistorySerializer(serializers.ModelSerializer):
    user_username = serializers.SerializerMethodField()
    game_title = serializers.CharField(source="game_history.title", read_only=True)

    class Meta:
        model = WinnerHistory
        fields = [
            'id',
            'game_history',
            'game_title',
            'user',
            'user_username',
            'number',
            'prize_position',
            'reward_type',
            'reward_description',
            'reward_image',
            'reward_link',
            'claimed_at'
        ]
        read_only_fields = fields  # all immutable

    def get_user_username(self, obj):
        return obj.user.username if obj.user else None
