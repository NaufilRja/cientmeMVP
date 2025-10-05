from rest_framework import(viewsets, permissions, serializers, 
status, exceptions
)

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from django.utils import timezone
from django.conf import settings
from django.http import Http404
from django.db.models import Q


from .services.game_fairness import GameFairness
from .services.game_logic import generate_winning_numbers

from .models import (
    Game, GameSubmission, WinningNumber,
    GameHistory, WinnerHistory, RewardMessage, GameComplaint
)

from .serializers import (
    GameSerializer, GameSubmissionSerializer,
    WinningNumberSerializer, GameHistorySerializer,
    WinnerHistorySerializer, RewardMessageSerializer, GameComplaintSerializer, PublicGameHistorySerializer,
    PublicWinnerSerializer
)


# -----------------------
# Game ViewSet
# -----------------------
class GameViewSet(viewsets.ModelViewSet):
    serializer_class = GameSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        """
        Return the queryset for active games.
        Filters:
        - Only active games (`is_active=True`) that haven't ended (`end_time > now`).
        - Optionally filter by `reel_id`.
        """
        queryset = Game.objects.filter(is_active=True, end_time__gt=timezone.now()).order_by('-created_at')

        reel_id = self.request.query_params.get('reel_id')
        if reel_id:
            queryset = queryset.filter(reel_id=reel_id)

        return queryset
    

    def get_object(self):
        """
        Return a single game object.

        - For active games: return normally.
        - If the game is inactive or ended, raise a custom 404 with a friendly message
        suggesting to check the game history.
        """
        game_id = self.kwargs.get("pk")
        try:
            # Fetch the game without filtering by active status
            game = Game.objects.get(pk=game_id)
        except Game.DoesNotExist:
            raise exceptions.NotFound(detail="No game matches the given ID.")

        # Check if game is inactive or ended
        if not game.is_active or game.end_time <= timezone.now():
            raise exceptions.NotFound(
                detail="No active game matches the given query, or it may have ended. You can check the game history."
            )

        return game

        
    
    def perform_create(self, serializer):
        """Assign creator, set end_time, generate winning numbers with provably fair encryption"""
        user = self.request.user
        game_instance = serializer.save(creator=user, is_active=True)

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
            ",".join(map(str, winning_numbers)),
            settings.FERNET_SECRET_KEY
        )

        game_instance.salt = salt
        game_instance.hash_value = hash_value
        game_instance.winning_numbers_encrypted = encrypted_numbers
        game_instance.save(update_fields=['end_time', 'salt', 'hash_value', 'winning_numbers_encrypted'])

    def perform_update(self, serializer):
        """Restrict updates if participants exist and only allow creator/staff"""
        instance = serializer.instance
        user = self.request.user

        if not (user.is_staff or user == instance.creator):
            raise PermissionDenied("You cannot update this game.")

        # Allow partial updates
        partial = getattr(serializer, 'partial', False)

        # Only enforce restricted fields if participants exist
        if instance.submissions.exists() and not partial:
            restricted_fields = [
                'title', 'description', 'image', 'reward_type', 'link',
                'guess_min', 'guess_max', 'number_of_winners',
                'auto_close', 'auto_select_winner',
            ]
            for field in restricted_fields:
                if field in serializer.validated_data:
                    raise serializers.ValidationError(
                        f"Cannot update '{field}' because participants have already submitted guesses."
                    )
            if 'winners_selected' in serializer.validated_data:
                raise serializers.ValidationError(
                    "You cannot manually change 'winners_selected'. It is set automatically."
                )

        serializer.save()



    def destroy(self, request, *args, **kwargs):
        """Soft-delete game with custom response"""
        instance = self.get_object()
        user = self.request.user

        if not (user.is_staff or user == instance.creator):
            raise PermissionDenied("You cannot delete this game.")

        if not instance.is_active:
            return Response(
                {"detail": f"Game '{instance.title}' is already deleted."},
                status=status.HTTP_404_NOT_FOUND
            )

        if instance.submissions.exists():
            raise serializers.ValidationError(
                "Cannot delete this game because participants have already submitted guesses."
            )

        instance.is_active = False
        instance.save(update_fields=['is_active'])

        return Response(
            {"detail": f"Game '{instance.title}' deleted successfully."},
            status=status.HTTP_200_OK
        )


# -----------------------
# Game Submission ViewSet
# -----------------------
class GameSubmissionViewSet(viewsets.ModelViewSet):
    serializer_class = GameSubmissionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return GameSubmission.objects.all().order_by('submitted_at')
        return GameSubmission.objects.filter(user=user).order_by('submitted_at')

    def perform_create(self, serializer):
        now = timezone.now()
        game = serializer.validated_data.get('game')

        # --- Check if game already ended ---
        if game.end_time and now > game.end_time:
            if game.is_active:  # only update once
                game.is_active = False
                game.auto_close = True
                game.auto_select_winner = True
                game.winners_selected = True
                game.save(update_fields=['is_active', 'auto_close', 'auto_select_winner', 'winners_selected'])
            raise serializers.ValidationError("This game has ended.")

        if not game.is_active:
            raise serializers.ValidationError("This game is closed. You cannot submit guesses.")

        # Prevent duplicate submission
        if GameSubmission.objects.filter(game=game, user=self.request.user).exists():
            raise serializers.ValidationError("You have already submitted.")

        # Pass user to serializer
        serializer.save(user=self.request.user, submitted_at=now)
        

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def mark_winners(self, request, pk=None):
        """Allow admin to mark winners manually"""
        submission = self.get_object()
        game = submission.game
        submissions = game.submissions.order_by('submitted_at')
        winners_count = game.number_of_winners

        position = 1
        for sub in submissions:
            if position > winners_count:
                break
            sub.mark_winner(position=position)
            position += 1

        return Response({'status': f'{winners_count} winners marked.'})

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def my_submissions(self, request):
        """Return only current user submissions"""
        submissions = GameSubmission.objects.filter(user=request.user).order_by('-submitted_at')
        serializer = self.get_serializer(submissions, many=True)
        return Response(serializer.data)


# -----------------------
# Winning Number ViewSet
# -----------------------
class WinningNumberViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WinningNumberSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = WinningNumber.objects.all().order_by('prize_position')
        game_id = self.request.query_params.get('game_id')
        if game_id:
            queryset = queryset.filter(game_id=game_id)
        return queryset


# -----------------------
# Optional JWT for public access
# -----------------------

class OptionalJWTAuthentication(JWTAuthentication):
    """
    Allow unauthenticated requests without failing.
    """
    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except exceptions.AuthenticationFailed:
            return None  # silently ignore invalid/missing tokens




class GameHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only viewset for GameHistory.
    - Public users see limited info (PublicGameHistorySerializer)
    - Authenticated users see full info (GameHistorySerializer)
    """
    serializer_class = GameHistorySerializer
    authentication_classes = [OptionalJWTAuthentication]
    permission_classes = [permissions.AllowAny]  # public by default

    def get_queryset(self):
        """
        Return filtered GameHistory queryset safely.
        Only returns games if relevant filters are passed.
        Starts empty to prevent exposing all games.
        """
        queryset = GameHistory.objects.none()  # start empty
        params = self.request.query_params

        # --- Helper to safely convert ID lists to integers ---
        def valid_int_list(param_list):
            return [int(x) for x in param_list if x.isdigit()]

        # --- Define all filters in one place ---
        filters = [
            ("creator_id", "game__creator_id__in", True),
            ("creator_name", "game__creator__username__in", False),
            ("winner_id", "all_winners__id__in", True),
            ("winner_name", "all_winners__username__in", False),
            ("game_id", "game_id__in", True),
            ("participant_id", "late_correct_guesses__user__id__in", True),
            ("participant_name", "late_correct_guesses__user__username__in", False),
        ]

        # --- Apply filters ---
        for param_name, lookup, is_id in filters:
            values = params.getlist(param_name)
            if not values:
                continue

            if is_id:
                values = valid_int_list(values)
            if not values:
                continue

            # If we already have a queryset, filter it further
            if queryset.exists():
                queryset = queryset.filter(**{lookup: values})
            else:
                # First filter, start a new queryset
                queryset = GameHistory.objects.filter(**{lookup: values})

        # Remove duplicates
        queryset = queryset.distinct()

        # Return most recent first
        return queryset.order_by("-created_at")
    
    #--------------------------------
    #  Get Serializer Class method 
    #--------------------------------
    def get_serializer_class(self):
        """
        Public serializer for unauthenticated users.
        Full serializer for authenticated users.
        """
        user = self.request.user
        if not user or not user.is_authenticated:
            return PublicGameHistorySerializer  # hide sensitive info
        return GameHistorySerializer

    # -----------------------
    # Custom action: by-game
    # -----------------------
    @action(detail=True, methods=['get'], url_path='by-game')
    def by_game(self, request, pk=None):
        try:
            game = Game.objects.get(pk=pk)
        except Game.DoesNotExist:
            return Response({"detail": "Game not found."}, status=404)

        history_qs = GameHistory.objects.filter(game=game).order_by('-completed_at')
        if not history_qs.exists():
            return Response({"detail": "No GameHistory for this Game."}, status=404)

        serializer = self.get_serializer(history_qs, many=True)
        return Response(serializer.data)



# -----------------------
# Winner History ViewSet
# -----------------------
class WinnerHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Returns winner history based on the requesting user.

    Rules:
    - Unauthenticated: cannot access.
    - Creator: sees full details of all winners for their games.
    - Winner: sees full details of their own winner history.
    - Other authenticated: sees minimal info (username, prize position, number).
    """

    serializer_class = WinnerHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Returns WinnerHistory objects filtered based on request sender.

        Optional query parameter:
        - ?game_id=<id> to filter a specific game
        """

        user = self.request.user
        game_id = self.request.query_params.get("game_id")

        # Base query: all winner history
        queryset = WinnerHistory.objects.all().order_by("-claimed_at")

        # Filter by game_id if provided
        if game_id:
            queryset = queryset.filter(game_history__game__id=game_id)

        # Keep logic simple: filtering is handled in serializer for who can see full or minimal info
        return queryset


# -----------------------
# RewardMessage ViewSet
# -----------------------
class RewardMessageViewSet(viewsets.ModelViewSet):
    serializer_class = RewardMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return messages only for sender or winner/creator"""
        user = self.request.user
        return RewardMessage.objects.filter(
            winner_history__user=user
        ) | RewardMessage.objects.filter(
            winner_history__game_history__creator=user
        )

    def perform_create(self, serializer):
        """Validate permission and assign sender"""
        wh = serializer.validated_data.get("winner_history")
        user = self.request.user

        if user != wh.user and user != wh.game_history.creator:
            raise PermissionDenied("You are not allowed to send messages for this reward.")

        serializer.save(sender=user)




# -----------------------
# Winner History ViewSet
# -----------------------
class GameComplaintViewSet(viewsets.ModelViewSet):
    """
    Handles complaints in a single class.

    - Winners: can only create complaints for their own rewards.
    - Admins/Staff: can view, update, and resolve any complaint.
    """

    serializer_class = GameComplaintSerializer
    queryset = GameComplaint.objects.all()

    def get_permissions(self):
        """
        Winners: only 'create' allowed.
        Admins: full access.
        """
        if self.action in ["create"]:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAdminUser()]

    def perform_create(self, serializer):
        """
        Attach user automatically & enforce winner-only rule.
        """
        user = self.request.user
        winner_history = serializer.validated_data.get("winner_history")

        # Rule 1: Only the actual winner can file a complaint
        if user != winner_history.user:
            raise PermissionDenied("Only the winner can submit a complaint for this reward.")

        # Rule 2: Winner must still be a follower of the creator
        if user not in winner_history.game.creator.profile.followers.all():
            raise PermissionDenied("You must be following the creator to submit a complaint.")

        serializer.save(user=user)
