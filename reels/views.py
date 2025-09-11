from rest_framework import viewsets, status, permissions, generics
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response


from core.mixins.action_mixins import OwnerActionsMixin, ActionResponseMixin
from core.permissions.general import IsProfileOwnerOrReadOnly
from .models import Reel, Comment, Share, Audio

from .serializers import ReelSerializer, CommentSerializer,  ReelReportSerializer 

from core.utils.engagement import calculate_reel_reach
from rest_framework.pagination import LimitOffsetPagination
from core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE



# -----------------------
# Pagination Class
# -----------------------
class ReelPagination(LimitOffsetPagination):
    default_limit = DEFAULT_PAGE_SIZE
    max_limit = MAX_PAGE_SIZE


# -----------------------
# Reel ViewSet
# -----------------------
class ReelViewSet(OwnerActionsMixin, ActionResponseMixin, viewsets.ModelViewSet):
    """
    ViewSet for handling CRUD and user interactions on Reels:
    - Like / Unlike
    - Save / Unsave
    - Share (with points, reach, and badge logic)
    - Increment Views
    """

    queryset = Reel.objects.select_related("user").prefetch_related(
        "likes", "saves", "comments__likes"
    ).all()
    serializer_class = ReelSerializer
    permission_classes = [permissions.IsAuthenticated, IsProfileOwnerOrReadOnly]

    # -----------------------
    # Like / Unlike
    # -----------------------
    @action(detail=True, methods=["post"])
    def like(self, request, pk=None):
        """Toggle like/unlike on a reel."""
        reel = self.get_object()
        user = request.user

        if reel.likes.filter(id=user.id).exists():
            reel.likes.remove(user)
            liked = False
        else:
            reel.likes.add(user)
            liked = True

        return self.success({"liked": liked, "likes_count": reel.likes.count()})

    # -----------------------
    # Save / Unsave
    # -----------------------
    @action(detail=True, methods=["post"])
    def save(self, request, pk=None):
        """Toggle save/unsave on a reel."""
        reel = self.get_object()
        user = request.user

        if reel.saves.filter(id=user.id).exists():
            reel.saves.remove(user)
            saved = False
        else:
            reel.saves.add(user)
            saved = True

        return self.success({"saved": saved, "saves_count": reel.saves.count()})

    # -----------------------
    # Share a Reel
    # -----------------------
    @action(detail=True, methods=["post"])
    def share(self, request, pk=None):
        """
        Share a reel:
        - Prevent duplicate shares by same user.
        - Increment reel share count.
        - Award points & badge if threshold met.
        - Guarantee minimum reach for next reel if badge earned.
        """
        reel = self.get_object()
        user = request.user

        # Prevent duplicate shares
        share_obj, created = Share.objects.get_or_create(reel=reel, sharer=user)
        if not created:
            return self.success({
                "message": "You already shared this reel.",
                "points_earned": share_obj.points_earned,
                "badge_earned": user.profile.badge_earned
            })

        # Increment reel shares
        reel.shares += 1
        reel.save(update_fields=["shares"])

        # Engagement points calculation
        points = (
            reel.likes.count() * 1.5 +
            reel.comments.filter(parent__isnull=True).count() * 3 +
            reel.comments.exclude(parent__isnull=True).count() * 4 +
            reel.saves.count() * 5 +
             6 +  # only this new share
            reel.views * 0.5
        )
        share_obj.points_earned = points
        share_obj.save()
        

        # Update user profile points + badge
        profile = user.profile
        profile.total_share_points += points

        if profile.total_share_points >= settings.TARGET_SHARE_POINTS and not profile.badge_earned:
            profile.badge_earned = True

        profile.save(update_fields=["total_share_points", "badge_earned"])

        # Update reel reach
        reel.reach = calculate_reel_reach(reel, reel.user.followers.count())
        reel.save(update_fields=["reach"])

        # Guarantee minimum reach for next reel if badge earned
        if profile.badge_earned:
            next_reel = Reel.objects.filter(user=user).order_by("-created_at").first()
            if next_reel:
                next_reel.reach = max(next_reel.reach, 10000)  # Configurable guaranteed reach
                next_reel.save(update_fields=["reach"])

        serializer = self.get_serializer(reel, context={"request": request})

        return self.success({
            "message": "Reel shared successfully",
            "points_earned": share_obj.points_earned,
            "total_share_points": profile.total_share_points,
            "badge_earned": profile.badge_earned,
            "reel": serializer.data
        })

    # -----------------------
    # Add View
    # -----------------------
    @action(detail=True, methods=["post"])
    def add_view(self, request, pk=None):
        """Increment view count for a reel (≥2 seconds watched)."""
        reel = self.get_object()

        reel.views += 1
        reel.reach = calculate_reel_reach(reel, reel.user.followers.count())
        reel.save(update_fields=["views", "reach"])

        return self.success({"views": reel.views, "reach": reel.reach})

    # -----------------------
    # Reuse Audio
    # -----------------------
    @action(detail=True, methods=["post"])
    def reuse_audio(self, request, pk=None):
        """
        Reuse audio from an existing reel.
        - If the reel has audio, return that audio metadata.
        - If no audio exists, return error.
        """
        source_reel = self.get_object()
        if not source_reel.audio:
            return Response({"error": "This reel has no audio to reuse."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = AudioSerializer(source_reel.audio, context={"request": request})
        return Response(serializer.data)

    # -----------------------
    # Reels by Audio
    # -----------------------
    @action(detail=False, methods=["get"], url_path="audio/(?P<audio_id>[^/.]+)")
    def reels_by_audio(self, request, audio_id=None):
        """
        List all reels using a specific audio.
        Example: GET /api/reels/audio/12/
        """
        try:
            audio = Audio.objects.get(pk=audio_id)
        except Audio.DoesNotExist:
            return Response({"error": "Audio not found."}, status=status.HTTP_404_NOT_FOUND)

        reels = audio.reels.all().select_related("user").prefetch_related("likes", "saves")
        serializer = ReelSerializer(reels, many=True, context={"request": request})
        return Response(serializer.data)

    # -----------------------
    # Create Reel
    # -----------------------
    def perform_create(self, serializer):
        """Assign user and calculate reach when reel is created."""
        user = self.request.user
        profile = user.profile
        badge_min_reach = 10000 if profile.badge_earned else None

        reel = serializer.save(user=user)

        reel.reach = calculate_reel_reach(
            reel,
            followers_count=profile.followers.count(),
            badge_min_reach=badge_min_reach,
        )
        reel.save(update_fields=["reach"])
        
        
# -----------------------
# Comment ViewSet
# -----------------------
# views.py
class CommentViewSet(OwnerActionsMixin, viewsets.ModelViewSet):
    """
    CRUD for Comments/Replies with Instagram/TikTok-style preview.
    """
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticated, IsProfileOwnerOrReadOnly]

    def get_queryset(self):
        reel_id = self.kwargs.get("reel_pk")
        parent_id = self.kwargs.get("comment_pk", None)

        qs = Comment.objects.filter(reel_id=reel_id)
        if parent_id:
            qs = qs.filter(parent_id=parent_id)
        else:
            qs = qs.filter(parent__isnull=True)

        return qs.select_related("user").prefetch_related("likes", "replies")

    def perform_create(self, serializer):
        reel_id = self.kwargs.get("reel_pk") or self.request.data.get("reel_id")
        parent_id = self.request.data.get("parent_id") or self.kwargs.get("comment_pk")
        if not reel_id:
            raise ValueError("reel_id is required")

        parent = None
        if parent_id:
            parent = Comment.objects.get(id=parent_id)

        serializer.save(user=self.request.user, reel_id=reel_id, parent=parent)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def likes(self, request, pk=None, reel_pk=None):
        comment = self.get_object()
        user = request.user

        if comment.likes.filter(id=user.id).exists():
            comment.likes.remove(user)
            liked = False
        else:
            comment.likes.add(user)
            liked = True

        return Response({
            "liked": liked,
            "likes_count": comment.likes.count()
        })

    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def replies(self, request, pk=None, reel_pk=None):
        """
        Lazy fetch all replies for a comment (pagination supported)
        """
        comment = self.get_object()
        qs = comment.replies.select_related("user").prefetch_related("likes").all()
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = CommentSerializer(page, many=True, context=self.get_serializer_context())
            return self.get_paginated_response(serializer.data)

        serializer = CommentSerializer(qs, many=True, context=self.get_serializer_context())
        return Response(serializer.data)

    def perform_update(self, serializer):
        comment = self.get_object()
        if comment.is_deleted:
            raise ValidationError("Cannot update a deleted comment.")
        serializer.save()


# -----------------------
# Hide Reel ViewSet
# -----------------------          
class HideReelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, reel_id):
        try:
            reel = Reel.objects.get(id=reel_id)
            request.user.profile.hidden_reels.add(reel)
            return Response({"status": "success", "message": "Reel hidden"})
        except Reel.DoesNotExist:
            return Response({"status": "error", "message": "Reel not found"}, status=404)

        
        
# -----------------------
# Reel Report ViewSet
# -----------------------       
class ReportReelView(APIView):
    """
    API endpoint to allow authenticated users to report a reel.

    Endpoint: POST /api/reels/<reel_id>/report/
    Request body: {"reason": "spam" | "inappropriate" | "other"}

    Workflow:
    1. Check if reel exists.
    2. Validate the report reason using serializer.
    3. Add the user to the reel's reports field.
    4. Save the last report reason.
    5. Return success or error response.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, reel_id):
        """
        Handle POST request to report a reel.

        Args:
            request: DRF request object containing user and POST data.
            reel_id: ID of the reel being reported.

        Returns:
            Response with status and message.
        """
        
        try:
            # Fetch the reel by ID
            reel = Reel.objects.get(id=reel_id)
        except Reel.DoesNotExist:
            # Reel not found
            return Response({"status": "error", "message": "Reel not found"}, status=404)
        
        # Reel not found
        serializer = ReelReportSerializer(data=request.data)
        if serializer.is_valid():
            # Add the reporting user to the reel's reports
            reel.reports.add(request.user)
            
            
            # Add the reporting user to the reel's reports
            reel.last_report_reason = serializer.validated_data["reason"]
            reel.save()
            
            # Success response
            return Response({"status": "success", "message": "Reel reported successfully"})
        else:
            # Validation error response
            return Response(serializer.errors, status=400)
