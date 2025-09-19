from rest_framework import viewsets, permissions
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from rest_framework import serializers
from django.utils import timezone
from django.conf import settings
from .services.game_fairness import GameFairness
from .services.game_logic import generate_winning_numbers


from .models import (
    Game, 
    GameSubmission,
    WinningNumber,
    GameHistory,
    WinnerHistory
)

from .serializers import (
    GameSerializer, 
    GameSubmissionSerializer,
    WinningNumberSerializer,
    GameHistorySerializer,
    WinnerHistorySerializer
)




class GameViewSet(viewsets.ModelViewSet):
    serializer_class = GameSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = Game.objects.filter(is_active=True).order_by('-created_at')
        reel_id = self.request.query_params.get('reel_id')
        if reel_id:
            queryset = queryset.filter(reel_id=reel_id)
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        game_instance = serializer.save(creator=user)

        if not game_instance.end_time:
            game_instance.end_time = timezone.now() + game_instance.duration

        try:
            winning_numbers, salt, hash_value = generate_winning_numbers(
                game_instance.guess_min,
                game_instance.guess_max,
                game_instance.number_of_winners
            )
        except ValueError as e:
            raise serializers.ValidationError(str(e))

        encrypted_numbers = GameFairness.encrypt_numbers(
            "-".join(map(str, winning_numbers)),
            settings.FERNET_SECRET_KEY
        )

        game_instance.salt = salt
        game_instance.hash_value = hash_value
        game_instance.winning_numbers_encrypted = encrypted_numbers
        game_instance.save(update_fields=['end_time', 'salt', 'hash_value', 'winning_numbers_encrypted'])

    def perform_update(self, serializer):
        user = self.request.user
        instance = serializer.instance

        if not (user.is_staff or user == instance.creator):
            raise PermissionDenied("You cannot update this game.")

        if instance.submissions.exists():
            restricted_fields = ['title', 'description', 'image', 'reward_type', 'link',
                                 'guess_min', 'guess_max', 'number_of_winners']
            for field in restricted_fields:
                if field in serializer.validated_data:
                    raise serializers.ValidationError(
                        f"Cannot update '{field}' because participants have already submitted guesses."
                    )

        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user

        if not (user.is_staff or user == instance.creator):
            raise PermissionDenied("You cannot delete this game.")

        if instance.submissions.exists():
            raise serializers.ValidationError(
                "Cannot delete this game because participants have already submitted guesses."
            )

        instance.is_active = False
        instance.save(update_fields=['is_active'])

        
        
class GameSubmissionViewSet(viewsets.ModelViewSet):
    serializer_class = GameSubmissionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return GameSubmission.objects.all().order_by('submitted_at')
        return GameSubmission.objects.filter(user=user).order_by('submitted_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, submitted_at=timezone.now())

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def mark_winners(self, request, pk=None):
        """
        Admin/staff can mark winners manually.
        """
        submission = self.get_object()
        game = submission.game

        submissions = game.submissions.order_by('submitted_at')
        winners_count = game.number_of_winners

        position = 1
        for submission in submissions:
            if position > winners_count:
                break
            submission.mark_winner(position)
            position += 1

        return Response({'status': f'{winners_count} winners marked.'})




# -----------------------
# Game Number ViewSet
# -----------------------
class WinningNumberViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only API for winning numbers.
    - Users can see all winning numbers for a game
    - Shows reward info and winner if claimed
    """
    queryset = WinningNumber.objects.all().order_by('prize_position')
    serializer_class = WinningNumberSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        """
        Optionally filter by `game_id` query param
        """
        queryset = super().get_queryset()
        game_id = self.request.query_params.get('game_id')
        if game_id:
            queryset = queryset.filter(game_id=game_id)
        return queryset




# -----------------------
# Game History ViewSet
# -----------------------
class GameHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only viewset for completed games history.
    - Users can see past games created by any creator.
    - Immutable: no creation, update, or deletion allowed.
    """
    queryset = GameHistory.objects.all().order_by('-completed_at')
    serializer_class = GameHistorySerializer
    permission_classes = [permissions.AllowAny]


# -----------------------
# Winner History ViewSet
# -----------------------
class WinnerHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only viewset for winners of games.
    - Users can see who won and prize details.
    - Immutable: no creation, update, or deletion allowed.
    """
    queryset = WinnerHistory.objects.all().order_by('-claimed_at')
    serializer_class = WinnerHistorySerializer
    permission_classes = [permissions.AllowAny]
