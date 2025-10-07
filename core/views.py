from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from reels.models import Reel
from games.models import ( GameHistory, WinnerHistory, RewardMessage

)
from django.contrib.auth import get_user_model
from .serializers import ( UserSearchSerializer, ReelSearchSerializer,
GameHistorySerializer, WinnerHistorySerializer, RewardMessageSerializer
)

User = get_user_model()

class SearchView(APIView):
    """
    Unified search endpoint for users and reels.
    Supports cursor-based pagination via last_user_id and last_reel_id.
    Supports `type` parameter: 'user', 'reel', or both (default).
    """

    permission_classes = [IsAuthenticated]
    DEFAULT_LIMIT = 20

    def get(self, request, format=None):
        query = request.GET.get("q", "").strip()
        if not query:
            return Response({"users": [], "reels": []})

        limit = int(request.GET.get("limit", self.DEFAULT_LIMIT))
        last_user_id = request.GET.get("last_user_id")
        last_reel_id = request.GET.get("last_reel_id")
        query_type = request.GET.get("type")  # 'user', 'reel', or None

        results = {"users": [], "reels": []}

        # -----------------------------
        # User search
        # -----------------------------
        if query_type in (None, "user"):
            users_qs = User.objects.filter(
                Q(username__icontains=query) |
                Q(name__icontains=query) |
                Q(email__icontains=query)
            ).order_by("id")

            if last_user_id:
                users_qs = users_qs.filter(id__gt=last_user_id)

            results["users"] = UserSearchSerializer(
                users_qs[:limit], many=True, context={'request': request}
            ).data

        # -----------------------------
        # Reel search
        # -----------------------------
        if query_type in (None, "reel"):
            reels_qs = Reel.objects.select_related("user").filter(
                Q(title__icontains=query) |
                Q(description__icontains=query) |
                Q(user__username__icontains=query) |
                Q(user__email__icontains=query)
            ).order_by("id")

            if last_reel_id:
                reels_qs = reels_qs.filter(id__gt=last_reel_id)

            results["reels"] = ReelSearchSerializer(
                reels_qs[:limit], many=True, context={'request': request}
            ).data

        return Response(results)



# -----------------------
# Cursor Pagination for GameHistory
# -----------------------
class GameHistoryCursorPagination(CursorPagination):
    page_size = 20  # default page size
    ordering = 'id'  # cursor ordering field


# -----------------------
# GameHistory Search View
# -----------------------
class GameHistorySearchView(APIView):
    """
    Search games with optional filtering by title, description, or reward type.
    Supports optional filtering by creator_id.
    Uses cursor-based pagination for better performance.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = GameHistoryCursorPagination

    def get(self, request, format=None):
        query = request.GET.get("q", "").strip()
        creator_id = request.GET.get("creator_id")  # optional filter
        games_qs = GameHistory.objects.select_related('creator').all()

        if creator_id:
            games_qs = games_qs.filter(creator_id=creator_id)

        if query:
            games_qs = games_qs.filter(
                Q(title__icontains=query) |
                Q(description__icontains=query) |
                Q(reward_type__icontains=query)
            )

        # Order by ID for cursor pagination
        games_qs = games_qs.order_by('id')

        # Apply pagination
        paginator = self.pagination_class()
        paginated_games = paginator.paginate_queryset(games_qs, request)
        serializer = GameHistorySerializer(paginated_games, many=True, context={"request": request})

        return paginator.get_paginated_response(serializer.data)

    

# -----------------------
# Cursor Pagination for WinnerHistory
# -----------------------
class WinnerHistoryCursorPagination(CursorPagination):
    page_size = 20  # default page size
    ordering = 'id'  # cursor ordering field


# -----------------------
# WinnerHistory Search View
# -----------------------
class WinnerHistorySearchView(APIView):
    """
    Search winners for a specific game with optional filtering by username/email.
    Supports cursor-based pagination for better performance.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = WinnerHistoryCursorPagination

    def get(self, request, game_id, format=None):
        query = request.GET.get("q", "").strip()
        winners_qs = WinnerHistory.objects.select_related('user', 'game').filter(game_id=game_id)

        if query:
            winners_qs = winners_qs.filter(
                Q(user__username__icontains=query) |
                Q(user__email__icontains=query)
            )

        # Order by ID for cursor pagination
        winners_qs = winners_qs.order_by('id')

        # Apply pagination
        paginator = self.pagination_class()
        paginated_winners = paginator.paginate_queryset(winners_qs, request)
        serializer = WinnerHistorySerializer(paginated_winners, many=True, context={"request": request})

        return paginator.get_paginated_response(serializer.data)
    
    
    
class RewardMessageCursorPagination(CursorPagination):
    page_size = 20
    ordering = 'created_at'

class RewardMessageSearchView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = RewardMessageCursorPagination

    def get(self, request, reward_chat_id, format=None):
        messages_qs = RewardMessage.objects.filter(reward_chat_id=reward_chat_id)

        # Optional filter: system messages
        is_system = request.GET.get("is_system_message")
        if is_system is not None:
            if is_system.lower() == "true":
                messages_qs = messages_qs.filter(is_system_message=True)
            elif is_system.lower() == "false":
                messages_qs = messages_qs.filter(is_system_message=False)

        messages_qs = messages_qs.order_by("created_at")

        paginator = self.pagination_class()
        paginated_messages = paginator.paginate_queryset(messages_qs, request)
        serializer = RewardMessageSerializer(paginated_messages, many=True, context={"request": request})

        return paginator.get_paginated_response(serializer.data)
