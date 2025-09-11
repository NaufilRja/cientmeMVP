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
    URL: /api/search/?q=<query>
    Returns JSON with 'users' and 'reels'.
    Permissions: Authenticated users only.
    """

    permission_classes = [IsAuthenticated]
    
    DEFAULT_LIMIT = 20  # You can adjust this

    def get(self, request, format=None):
        query = request.GET.get("q", "").strip()
        limit = int(request.GET.get("limit", self.DEFAULT_LIMIT))
        last_user_id = request.GET.get("last_user_id")
        last_reel_id = request.GET.get("last_reel_id")

        if not query:
            return Response({"users": [], "reels": []})


        # -----------------------------
        # User search with cursor
        # -----------------------------
        users_qs = User.objects.filter(
            Q(username__icontains=query) | Q(name__icontains=query)
        ).order_by("id")

        if last_user_id:
            users_qs = users_qs.filter(id__gt=last_user_id)

        users_qs = users_qs.only("id", "username", "name", "avatar")[:limit]
        users_serializer = UserSearchSerializer(users_qs, many=True)


        # -----------------------------
        # Reel search with cursor
        # -----------------------------
        reels_qs = Reel.objects.select_related("user").filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        ).order_by("id")

        if last_reel_id:
            reels_qs = reels_qs.filter(id__gt=last_reel_id)

        reels_qs = reels_qs.only("id", "title", "thumbnail", "user")[:limit]
        reels_serializer = ReelSearchSerializer(reels_qs, many=True)

        return Response({
            "users": users_serializer.data,
            "reels": reels_serializer.data
        })