from rest_framework import(viewsets, permissions, serializers, 
status, exceptions , generics, views
)

from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import FieldError
from django.db.models import Prefetch, OuterRef, Subquery, Count, Max, F, Q, IntegerField
from django.db.models.functions import Coalesce

from core.utils.auth import OptionalJWTAuthentication
from core.pagination import StandardCursorPagination, ChatMessagePagination
import logging

from .services.game_fairness import GameFairness
from .services.game_logic import generate_winning_numbers

from .models import (
    Game, GameSubmission, WinningNumber,
    GameHistory, WinnerHistory, RewardMessage, RewardChat, GameComplaint, 
)

from .serializers import (
    GameSerializer, PublicGameSerializer, 
    GameSubmissionSerializer,WinningNumberSerializer, GameHistorySerializer, WinnerHistorySerializer, RewardMessageSerializer, GameComplaintSerializer, PublicGameHistorySerializer, PublicWinnerSerializer,
    ChatListSerializer, ClaimedWinnerSerializer
)



logger = logging.getLogger(__name__)


# -----------------------
# Game ViewSet
# -----------------------
class GameViewSet(viewsets.ModelViewSet):
    serializer_class = GameSerializer
    authentication_classes = [OptionalJWTAuthentication]
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


    # -----------------------
    # Dynamic serializer for public vs authenticated users
    # -----------------------
    def get_serializer_class(self):  # updated here
        if self.request.user.is_authenticated:
            return GameSerializer  # full detail for logged-in users
        return PublicGameSerializer  # minimal public info for unauthenticated users
    
    # ---------------------
    #  Get Quetryset Method
    # --------------------- 
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
    
    # ---------------------
    #  Get Object Method
    # ---------------------   
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

        
    # ------------------------------
    #  Game Perform Create  Method
    # ------------------------------
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

    # ------------------------------
    #  Game Perform Upadte  Method
    # ------------------------------
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


    # ----------------------
    #  Destroy Method
    # ----------------------
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
# UnPlayed Game ViewSet
# -----------------------
class UnplayedGamesListView(generics.ListAPIView):
    """
    Shows all games created by the user that ended without any participants.
    """
    serializer_class = GameSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        now = timezone.now()
        return Game.objects.annotate(
            participant_count_real=Count('submissions')  # replace 'submissions' with your related_name
        ).filter(
            creator=user,
            participant_count_real=0,
            end_time__lt=now
        ).order_by('-created_at')



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


    # ----------------------
    # Perform Create Method
    # ----------------------
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
        
        
    # ----------------------
    #  Mark Winner Method
    # ----------------------
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
# Game History ViewSet
# -----------------------

class GameHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only viewset for GameHistory.

    - If the request is unauthenticated -> use PublicGameHistorySerializer (minimal)
    - If authenticated -> use GameHistorySerializer (full)
    - Supports filtering by:
        * creator_id (via URL kwargs or via creator_id query param)
        * game_id (query param)
        * title (partial match)
        * winner_name (partial match on WinnerHistory.user.username)
    """

    # Default serializer (will be switched by get_serializer_class)
    serializer_class = GameHistorySerializer
    authentication_classes = [OptionalJWTAuthentication]
    permission_classes = [permissions.AllowAny]  # public by default

    # --------------------------
    # Helper: validate integer
    # --------------------------
    def _valid_int(self, value):
        return str(value).isdigit()

    # --------------------------
    # Main queryset builder
    # --------------------------
    def get_queryset(self):
        """
        Build queryset using safe lookups. Start with all GameHistory, then
        apply creator filter (if in kwargs), then apply optional query params.
        """
        try:
            qs = GameHistory.objects.all()
            params = self.request.query_params

            # --- Creator filter from kwargs (used for creator profile: /games-history/creator/<id>/ )
            creator_id = self.kwargs.get("creator_id")
            if creator_id and self._valid_int(creator_id):
                qs = qs.filter(game__creator_id=int(creator_id))

            # --- Optional filters from query params ---
            game_id = params.get("game_id")
            if game_id and self._valid_int(game_id):
                qs = qs.filter(game_id=int(game_id))

            title = params.get("title")
            if title:
                # search the game title (partial)
                qs = qs.filter(game__title__icontains=title)

            winner_name = params.get("winner_name")
            if winner_name:
                # IMPORTANT: winners -> related WinnerHistory model, whose user FK is 'user'
                # so we must look through winners__user__username
                qs = qs.filter(winners__user__username__icontains=winner_name)

            # Distinct to avoid duplicates when joining across winners/submissions
            qs = qs.distinct().order_by("-completed_at")
            return qs

        except FieldError as e:
            # Defensive: don't let a bad lookup crash the server
            # Return an empty queryset so DRF will return an empty list for the endpoint.
            # Alternatively you could raise a ValidationError here.
            # We'll raise a DRF Response with 400 so client sees the problem.
            raise

    # --------------------------
    # Serializer selection
    # --------------------------
    def get_serializer_class(self):
        """
        Use public serializer for unauthenticated requests, full serializer otherwise.
        """
        user = self.request.user
        if not user or not user.is_authenticated:
            return PublicGameHistorySerializer
        return GameHistorySerializer

    # --------------------------
    # Extra: endpoint to fetch a creator's history cleanly:
    # GET /api/games/games-history/creator/<creator_id>/
    # --------------------------
    @action(detail=False, methods=['get'], url_path=r'creator/(?P<creator_id>[^/.]+)')
    def creator_history(self, request, creator_id=None):
        if not creator_id or not self._valid_int(creator_id):
            return Response({"detail": "creator_id must be a numeric id."}, status=status.HTTP_400_BAD_REQUEST)

        queryset = GameHistory.objects.filter(game__creator_id=int(creator_id)).distinct().order_by('-completed_at')
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    # --------------------------
    # Extra: by-game endpoint (query param)
    # GET /api/games/games-history/by-game/?game_id=19
    # --------------------------
    @action(detail=False, methods=['get'], url_path='by-game')
    def by_game(self, request):
        """
        Return GameHistory for a specific game_id.
        Handles missing or invalid game IDs safely.
        """
        game_id = request.query_params.get('game_id')

        # Validate presence
        if not game_id:
            return Response(
                {"detail": "game_id query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate numeric value
        if not game_id.isdigit():
            return Response(
                {"detail": "Invalid game_id format. Must be numeric."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check game existence
        game = Game.objects.filter(id=game_id).first()
        if not game:
            return Response(
                {"detail": "Game not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Fetch related GameHistory
        qs = GameHistory.objects.filter(game_id=game_id).order_by('-completed_at')
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    

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
    authentication_classes = [OptionalJWTAuthentication]
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    
     # -----------------------
    # Dynamic serializer for public vs authenticated users
    # -----------------------
    def get_serializer_class(self):  # updated here
        if self.request.user.is_authenticated:
            return WinnerHistorySerializer  # full detail for logged-in users
        return PublicWinnerSerializer  # minimal public info for unauthenticated users

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
    
    
    # -----------------------------
    #  Winner claims their reward
    # -----------------------------
    @action(detail=True, methods=['post'], url_path='claim', permission_classes=[permissions.IsAuthenticated])
    def claim_reward(self, request, pk=None):
        """
        Endpoint for the winner to claim their reward.
        POST /api/winner-history/<id>/claim/
        """
        try:
            winner_history = self.get_object()

            # Ensure only the actual winner can claim their reward
            if winner_history.user != request.user:
                return Response(
                    {"detail": "You are not allowed to claim this reward."},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # NEW: Prevent claiming if winner already confirmed receipt
            if winner_history.reward_received:
                return Response(
                    {"detail": "Reward has already been confirmed received. Cannot claim again or dispute."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Attempt reward claim using model method
            winner_history.claim_reward()

            return Response(
                {"detail": "Reward successfully claimed!"},
                status=status.HTTP_200_OK
            )

        except ValueError as e:
            # Expected model-level validation (e.g., already claimed, expired)
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            # Log unexpected errors for debugging and monitoring
            logger.exception(f"Unexpected error during reward claim for WinnerHistory ID {pk}")
            # Remove this print after testing (kept for local debug)
            print(f"[DEBUG] Error claiming reward: {e}")  # ← remove later after verifying logs
            return Response(
                {"detail": "An unexpected error occurred while claiming the reward."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
            
    @action(detail=True, methods=['post'], url_path='deliver', permission_classes=[permissions.IsAuthenticated])
    def mark_delivered(self, request, pk=None):
        winner_history = self.get_object()
        
        if request.user != winner_history.game_history.game.creator:
            return Response({"detail": "Only the creator can mark as delivered."}, status=403)
        
        try:
            winner_history.mark_delivered()  # call the model method
            return Response({"detail": "Reward marked as delivered!"}, status=200)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
            
        
    # -----------------------------------------
    #  Winner confirms it received the reward
    # -----------------------------------------     
    @action(detail=True, methods=["post"], url_path="confirm-receipt")
    def confirm_receipt(self, request, pk=None):
        """
        Winner confirms they received the reward.
        Only allowed if reward was claimed and delivered by creator.
        """
        winner_history = self.get_object()

        if winner_history.user != request.user:
            return Response({"detail": "You are not the winner of this reward."}, status=403)

        if not winner_history.is_claimed:
            return Response({"detail": "Reward must be claimed first."}, status=400)

        if not winner_history.reward_delivered:
            return Response({"detail": "Reward has not been marked as delivered by creator yet."}, status=400)
        

        # Prevent duplicate confirmation
        if winner_history.reward_received:
            return Response({"detail": "Reward already confirmed received. No further actions allowed."}, status=400)

        winner_history.reward_received = True
        winner_history.received_at = timezone.now()
        winner_history.save(update_fields=["reward_received", "received_at"])

        return Response({"detail": "Reward receipt confirmed!"})        



# ------------------------------------------------------
# Claimed Winner List ViewSet for spesific and all games
# -----------------------------------------------------
class ClaimedWinnerListView(views.APIView):
    """
    Returns list of winners who claimed rewards.
    - If `game_id` is provided → winners for that specific game.
    - If no `game_id` → all winners across the creator's games.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        game_id = request.query_params.get("game_id")

        # Base queryset: all claimed, unreceived rewards for this creator
        winners = WinnerHistory.objects.filter(
            game_history__creator=user,
            is_claimed=True,
            reward_received=False
        ).order_by('-claimed_at')

        # Filter by specific game if game_id provided
        if game_id:
            winners = winners.filter(game_history_id=game_id)

        serializer = ClaimedWinnerSerializer(winners, many=True, context={"request": request})
        return Response(serializer.data)


# -----------------------
# RewardMessage ViewSet
# -----------------------
class RewardMessageViewSet(viewsets.ModelViewSet):
    """
    Handles RewardMessage CRUD with bidirectional chat (winner ↔ creator).
    Messaging blocked after reward confirmed.
    """
    serializer_class = RewardMessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = ChatMessagePagination

    def get_queryset(self):
        user = self.request.user

        reward_chat_id = self.request.query_params.get("reward_chat")
        if not reward_chat_id:
            return RewardMessage.objects.none()

        # Fetch all messages for this chat
        queryset = RewardMessage.objects.filter(reward_chat_id=reward_chat_id)

        # Include only messages visible to the current user
        # (creator/winner can see system messages too)
        queryset = queryset.filter(
            Q(winner_history__user=user) | Q(winner_history__game_history__creator=user)
        )

        # Optional: filter system messages if explicitly requested
        is_system = self.request.query_params.get("is_system_message")
        if is_system is not None:
            queryset = queryset.filter(is_system_message=(is_system.lower() == "true"))

        # Mark unread messages as read
        unread_qs = queryset.filter(~Q(sender=user), is_read=False)
        if unread_qs.exists():
            unread_qs.update(is_read=True)

        # Oldest first
        return queryset.order_by("created_at")

    def create(self, request, *args, **kwargs):
        user = request.user

        # Update last_online
        if hasattr(user, "profile"):
            user.profile.last_online = timezone.now()
            user.profile.save(update_fields=["last_online"])

        # Let the serializer handle winner_history validation and creation
        response = super().create(request, *args, **kwargs)

        # response.data already has reward_chat_id from serializer
        reward_chat_id = response.data.get("reward_chat_id")

        return Response({
            "detail": "Message sent successfully",
            "reward_chat_id": reward_chat_id,
            "message": response.data
        })


    def update(self, request, *args, **kwargs):
        raise exceptions.MethodNotAllowed("PUT", detail="Editing messages is not allowed.")

    def partial_update(self, request, *args, **kwargs):
        raise exceptions.MethodNotAllowed("PATCH", detail="Editing messages is not allowed.")

    def destroy(self, request, *args, **kwargs):
        raise exceptions.MethodNotAllowed("DELETE", detail="Deleting messages is not allowed.")




# -----------------------
# ChatListView
# -----------------------
class ChatListView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardCursorPagination

    def get(self, request):
        user = request.user
        query = request.GET.get("q", "").strip()

        # -----------------------
        # Remove duplicate RewardChats (keep earliest)
        # -----------------------
        unique_pairs = set()
        duplicates = []

        for chat in RewardChat.objects.all().only("id", "creator_id", "winner_id"):
            key = tuple(sorted([chat.creator_id, chat.winner_id]))  # unique pair
            if key in unique_pairs:
                duplicates.append(chat.id)
            else:
                unique_pairs.add(key)

        if duplicates:
            RewardChat.objects.filter(id__in=duplicates).delete()

        # -----------------------
        # Base queryset — user involved as creator or winner
        # -----------------------
        chats = (
            RewardChat.objects.filter(Q(creator=user) | Q(winner=user))
            .prefetch_related("messages", "creator__profile", "winner__profile")
            .annotate(last_message_time=Max("messages__created_at"))
        )

        # -----------------------
        # Mark messages delivered for this user
        # -----------------------
        RewardMessage.objects.filter(
            reward_chat__in=chats,
            is_delivered=False
        ).exclude(sender=user).update(is_delivered=True)


        # -----------------------
        # Separate chats with and without messages
        # -----------------------
        chats_with_msg = chats.filter(last_message_time__isnull=False)
        chats_without_msg = chats.filter(last_message_time__isnull=True)

        # Combine (messages first, then empty)
        chats = chats_with_msg.union(chats_without_msg).order_by("-last_message_time", "-id")

        # -----------------------
        # Search filter
        # -----------------------
        if query:
            chats = chats.filter(
                Q(creator__username__icontains=query)
                | Q(winner__username__icontains=query)
            )

        # -----------------------
        # Pagination
        # -----------------------
        paginator = self.pagination_class()
        paginated_chats = paginator.paginate_queryset(chats, request)

        # -----------------------
        # Serialize
        # -----------------------
        serializer = ChatListSerializer(
            paginated_chats, many=True, context={"request": request}
        )

        return paginator.get_paginated_response(serializer.data)



# -----------------------
# Game Complaint ViewSet
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
