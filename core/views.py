from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from reels.models import Reel
from django.contrib.auth import get_user_model
from .serializers import UserSearchSerializer, ReelSearchSerializer

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
