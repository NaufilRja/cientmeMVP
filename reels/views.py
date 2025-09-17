from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from django.conf import settings
from datetime import timedelta, datetime, timezone as dt_timezone
from django.utils import timezone
from django.shortcuts import get_object_or_404
from moviepy.editor import VideoFileClip
import os, uuid


from core.utils.feed import get_user_feed
from core.utils.reach import update_profile_reach
from core.mixins.action_mixins import OwnerActionsMixin, ActionResponseMixin
from core.permissions.general import IsProfileOwnerOrReadOnly
from .models import(
    Reel, 
    Comment, 
    Share, 
    Audio
) 

from .serializers import(
ReelSerializer, 
CommentSerializer, 
ReelReportSerializer, 
ReelUpdateSerializer,
AudioSerializer 
)

from core.utils.engagement import (
calculate_share_points,
calculate_reel_reach, 
calculate_feed_score
)
from rest_framework.pagination import LimitOffsetPagination
from core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE





# -----------------------
# Helper functions for Feed
# -----------------------
# (1️) Get fresh/random reels for discovery
def get_fresh_feed(user, limit=20):
    """
    Return a list of fresh reels for the user to discover.
    - Excludes reels uploaded by the current user
    - Orders by creation date (newest first)
    - Can be later extended to include viral boost for new users
    """
    return Reel.objects.exclude(user=user).order_by('-created_at')[:limit]


# (2️) Get reels from people the user follows
def get_following_feed(user, following_ids, limit=20):
    """
    Return reels uploaded by the users that the current user follows.
    - Priority feed for social engagement
    - Ordered by creation date (most recent first)
    """
    if not following_ids:
        return []  # if user follows no one, return empty
    return Reel.objects.filter(user__id__in=following_ids).order_by('-created_at')[:limit]


# (3) Get current seasonal/event keywords
def get_current_season_keywords():
    """
    Return list of current seasonal/event keywords for boosting relevant reels.
    - Can be used in feed scoring
    - Example: festive season, holidays, morning/evening activities
    """
    month = datetime.now().month
    if month in [11, 12]:
        return ['diwali', 'christmas', 'new year']  # winter festivals
    elif month in [6, 7, 8]:
        return ['summer', 'vacation', 'holidays']  # summer season
    elif month in [3, 4]:
        return ['spring', 'holi']  # spring season
    else:
        return []  # default, no special season




# -----------------------
# Helper function for reel audio
# -----------------------
def extract_audio_from_reel(reel_instance):
    """Extract audio from reel video and link to Audio model i  not     already linked."""
    if reel_instance.audio or not reel_instance.video:
        return None  # already has audio or no video

    video_path = reel_instance.video.path
    clip = VideoFileClip(video_path)

    # Generate a temp audio file
    audio_filename = f"{uuid.uuid4()}.mp3"
    audio_path = os.path.join("media/reel_audio/", audio_filename)

    # Make sure the directory exists
    os.makedirs(os.path.dirname(audio_path), exist_ok=True)

    # Extract audio
    clip.audio.write_audiofile(audio_path)

    # Create Audio object
    audio = Audio.objects.create(
        title=f"Audio from Reel {reel_instance.id}",
        file=f"reel_audio/{audio_filename}",
        duration=clip.duration,
        created_by=reel_instance.user,
        is_from_reel=True
    )

    # Link reel to this audio
    reel_instance.audio = audio
    reel_instance.save(update_fields=["audio"])

    return audio
    


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

    serializer_class = ReelSerializer
    permission_classes = [permissions.IsAuthenticated, IsProfileOwnerOrReadOnly]
    
    # -----------------------
    # Default queryset for CRUD
    # -----------------------
    def get_queryset(self):
        user = self.request.user
        return Reel.objects.select_related("user").prefetch_related(
            "likes", "saves", "comments__likes"
        ).exclude(id__in=user.profile.hidden_reels.values_list("id", flat=True))




    # -----------------------
    # Custom actions
    # -----------------------
    @action(detail=False, methods=["get"], url_path="feed",     permission_classes=[permissions.IsAuthenticated])
    def feed(self, request):
        """
        Return reels for feed with a hybrid approach:
        - 70% personalized (tags/engagement)
        - 20% fresh/new reels
        - 10% social boost (following)
        Then scored & sliced using cursor-based pagination.
        """
        user = request.user
        following_ids = list(user.following_profiles.values_list("id",  flat=True))
        hidden_ids = list(user.profile.hidden_reels.values_list('id',   flat=True))

        # Step 1: Get reels for each category
        personalized_feed = get_user_feed(user, limit=70)   # personalized  based on tags/engagement
        fresh_feed = get_fresh_feed(user, limit=20)               # new/unseen    reels
        social_feed = get_following_feed(user, following_ids, limit=10)
        # reels  from followed users

        # Combine all feeds
        combined_feed = list(personalized_feed) + list(fresh_feed) + list   (social_feed)

        # Remove hidden reels
        combined_feed = [r for r in combined_feed if r.id not in    hidden_ids]

        # Remove duplicates by ID
        seen_ids = set()
        unique_feed = []
        for reel in combined_feed:
            if reel.id not in seen_ids:
                unique_feed.append(reel)
                seen_ids.add(reel.id)

        combined_feed = unique_feed

        # Step 2: Calculate score for each reel
        scored_reels = [
            (reel, calculate_feed_score(
                reel,
                user,
                following_ids=following_ids,
                season_keywords=get_current_season_keywords()  # optional seasonal keywords
            ))
            for reel in combined_feed
        ]

        # Step 3: Sort by score
        scored_reels.sort(key=lambda x: x[1], reverse=True)

        # ------------------------
        # Step 4: Cursor-based slicing (after sorting)
        # ------------------------
        last_reel_id = request.GET.get("last_reel_id")
        if last_reel_id:
            try:
                # find index of last reel in scored_reels
                last_index = next(i for i, (r, _) in enumerate(scored_reels)        if r.id == int(last_reel_id))
                scored_reels = scored_reels[last_index + 1:]  # next page
            except StopIteration:
                scored_reels = scored_reels  # last_id not found, return first page

        limit = int(request.GET.get("limit", 20))
        reels_list = [reel for reel, _ in scored_reels]
        paginated_reels = reels_list[:limit]


        # Step 5: Serialize
        top_reels = [self.serialize_reel_with_counts(reel, request) for reel        in paginated_reels]
        
        
        
        # Step 6: Response with last_id for frontend cursor
        last_id = top_reels[-1]["id"] if top_reels else None
        return Response({
                "results": top_reels,
                "last_id": last_id,   # 👈 this is the cursor for the next page
                "count": len(top_reels)
            })



    # -----------------------
    # Like / Unlike
    # -----------------------
    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
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
    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def saved(self, request, pk=None):
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


    #  Utility function
    def serialize_reel_with_counts(self, reel, request):
        return self.get_serializer(reel, context={"request": request}).data


    # -----------------------
    # Share a Reel
    # -----------------------
    @action(detail=True, methods=["post"], url_path="share", permission_classes=[permissions.IsAuthenticated])
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
        now = timezone.now()

        # -----------------------
        # Step 0: Calculate potential points first
        # -----------------------
        one_hour_ago = now - timedelta(hours=1)
        today_start = datetime(year=now.year, month=now.month, day=now.day, tzinfo=dt_timezone.utc)

        shares_last_hour = Share.objects.filter(sharer=user, created_at__gte=one_hour_ago).count()
        shares_today = Share.objects.filter(sharer=user, created_at__gte=today_start).count()

        points = calculate_share_points(reel)  # potential points

        # Optional bonus multiplier for first few shares of the day
        if shares_today == 0:
            points = round(points * 1.5)
        elif shares_today <= 2:
            points = round(points * 1.2)

        # -----------------------
        # Step 1: Hourly & Daily Cap Checks
        # -----------------------
        MAX_HOURLY_SHARES = 3
        MAX_DAILY_SHARES = 10

        if shares_last_hour >= MAX_HOURLY_SHARES:
            return Response({
                "message": f"Hourly share limit reached ({MAX_HOURLY_SHARES}/hour). Try again later.",
                "points_earned": points,
                "badge_type": user.profile.badge_type,
                "reel": self.get_serializer(reel, context={"request": request}).data
            }, status=status.HTTP_200_OK)

        if shares_today >= MAX_DAILY_SHARES:
            return Response({
                "message": f"Daily share limit reached ({MAX_DAILY_SHARES}/day). Try again tomorrow.",
                "points_earned": points,
                "badge_type": user.profile.badge_type,
                "reel": self.get_serializer(reel, context={"request": request}).data
            }, status=status.HTTP_200_OK)

        # -----------------------
        # Step 2: Prevent duplicate shares
        # -----------------------
        share_obj, created = Share.objects.get_or_create(reel=reel, sharer=user)
        if not created:
            return Response({
                "message": "You already shared this reel.",
                "points_earned": share_obj.points_earned,
                "badge_type": user.profile.badge_type,
                "reel": self.get_serializer(reel, context={"request": request}).data
            }, status=status.HTTP_200_OK)

        # -----------------------
        # Step 3: Increment reel shares
        # -----------------------
        reel.shares += 1
        reel.save(update_fields=["shares"])

        # -----------------------
        # Step 4: Engagement points calculation
        # -----------------------
        share_obj.points_earned = points
        share_obj.save()

        # -----------------------
        # Step 5: Update user profile points + badge (Updated for new BADGE_TIERS)
        # -----------------------
        profile = user.profile
        profile.total_share_points += points

        # --- Badge assignment according to new BADGE_TIERS ---
        if profile.total_share_points >= settings.BADGE_TIERS["cientium"]:
            profile.badge_type = "cientium"
        elif profile.total_share_points >= settings.BADGE_TIERS["platinum"]:
            profile.badge_type = "platinum"
        elif profile.total_share_points >= settings.BADGE_TIERS["gold"]:
            profile.badge_type = "gold"
        elif profile.total_share_points >= settings.BADGE_TIERS["silver"]:
            profile.badge_type = "silver"
        else:
            profile.badge_type = ""  # no badge

        # --- Cap points at cientium (Updated from platinum) ---
        if profile.total_share_points > settings.BADGE_TIERS["cientium"]:
            profile.total_share_points = settings.BADGE_TIERS["cientium"]

        profile.save(update_fields=["total_share_points", "badge_type"])

        # -----------------------
        # Step 6: Update reel reach (Updated for tier-based min reach)
        # -----------------------
        old_reach = reel.reach

        # --- Determine badge-specific minimum reach ---
        badge_min_reach = None
        if profile.badge_type == "silver":
            badge_min_reach = 10_000
        elif profile.badge_type == "gold":
            badge_min_reach = 100_000
        elif profile.badge_type == "platinum":
            badge_min_reach = 1_000_000
        elif profile.badge_type == "cientium":
            badge_min_reach = 10_000_000

        reel.reach = calculate_reel_reach(
            reel,
            followers_count=reel.user.profile.followers.count(),
            badge_min_reach=badge_min_reach
        ) or 0

        reel.save(update_fields=["reach"])
        
        # 🔑 Update profile reach incrementally
        delta = (reel.reach or 0) - (old_reach or 0)
        update_profile_reach(reel.user.profile, delta)

        # -----------------------
        # Step 7: Guarantee minimum reach for next reel if badge earned     (Updated for tiers)
        # -----------------------
        if profile.badge_type in ["silver", "gold", "platinum", "cientium"]:
            next_reel = Reel.objects.filter(user=user).exclude(id=reel.id). order_by("-created_at").first()
            if next_reel:
                next_reel.reach = max(next_reel.reach, badge_min_reach)  #  Configurable by badge tier
                next_reel.save(update_fields=["reach"])

        # -----------------------
        # Step 8: Return response
        # -----------------------
        serializer = self.get_serializer(reel, context={"request":  request})
        return Response({
            "message": "Reel shared successfully",
            "points_earned": share_obj.points_earned,
            "total_share_points": profile.total_share_points,
            "badge_type": profile.badge_type,
            "reel": serializer.data
        }, status=status.HTTP_200_OK)

        
    # -----------------------
    # Add View
    # -----------------------
    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def add_view(self, request, pk=None):
        """Increment view count for a reel (≥2 seconds watched)."""
        reel = self.get_object()

        reel.views += 1
        reel.reach = calculate_reel_reach(reel, reel.user.profile.followers.count())
        reel.save(update_fields=["views", "reach"])

        return self.success({"views": reel.views, "reach": reel.reach})

    # -----------------------
    # Reuse Audio
    # -----------------------
    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
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
    @action(detail=False, methods=["get"], url_path="audio/(?P<audio_id>[^/.]+)", permission_classes=[permissions.IsAuthenticated])
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
    def get_serializer_class(self):
        if self.action in ["update", "partial_update"]:
            return ReelUpdateSerializer
        return ReelSerializer    
        
    
    # -----------------------
    # Create Reel
    # -----------------------
    def perform_create(self, serializer):
        """Assign user, tags, and calculate reach when reel is created."""
        user = self.request.user
        profile = user.profile
        badge_min_reach = 10000 if profile.badge_type else None

        # Save reel instance
        reel = serializer.save(user=user)

        # Assign tags if provided
        tag_ids = serializer.validated_data.get('tags')
        if tag_ids:
            reel.tags.set(tag_ids)

       
        # Calculate reach
        reel.reach = calculate_reel_reach(
            reel,
            followers_count=profile.followers.count(),
            badge_min_reach=badge_min_reach,
        ) or 0
        reel.save(update_fields=["reach"])
        
        # Extract audio from video
        extract_audio_from_reel(reel)
        
        
     
    # -----------------------
    # custom delete
    # -----------------------   
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({"message": "Reel has been deleted."},  status=status.HTTP_200_OK)
  
  
        
# -----------------------
# Comment ViewSet
# -----------------------
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
    
    

    # -----------------------
    # Create a comment or a reply
    # -----------------------
    def perform_create(self, serializer):
        reel_id = self.kwargs.get("reel_pk") or self.request.data.get("reel_id")
        parent_id = self.request.data.get("parent_id") or self.kwargs.get("comment_pk")
        if not reel_id:
            raise ValueError("reel_id is required")

        parent = None
        if parent_id:
            parent = Comment.objects.get(id=parent_id)

        serializer.save(user=self.request.user, reel_id=reel_id, parent=parent)
        
        
        
    # -----------------------
    #  like Comment and like replies 
    # -----------------------   
    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def like(self, request, reel_pk=None, comment_pk=None, pk=None):
        """
        Handles likes for both comments and replies.
        Nested route passes:
        - reel_pk: ID of the reel
        - comment_pk: ID of the parent comment (if it's a reply)
        - pk: ID of the comment or reply itself
        """
        if comment_pk:  # It's a reply
            parent_comment = get_object_or_404(Comment, pk=comment_pk)
            obj = get_object_or_404(Comment, pk=pk, parent=parent_comment)
        else:  # It's a top-level comment
            obj = get_object_or_404(Comment, pk=pk)

        user = request.user
        # Add or toggle like
        if user in obj.likes.all():
            obj.likes.remove(user)
            liked = False
        else:
            obj.likes.add(user)
            liked = True

        return Response({"liked": liked, "likes_count": obj.likes.count()})
    
    
    # -----------------------
    # Get all replies for a comment
    # -----------------------
    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def replies(self, request, reel_pk=None, pk=None):
        """
        Fetch all replies for a comment (pagination supported)
        """
        try:
            comment = Comment.objects.get(pk=pk)
        except Comment.DoesNotExist:
            return Response({"detail": "Comment not found."}, status=404)

        qs = comment.replies.select_related("user").prefetch_related("likes").all()
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = CommentSerializer(page, many=True, context=self.   get_serializer_context())
            return self.get_paginated_response(serializer.data)

        serializer = CommentSerializer(qs, many=True, context=self. get_serializer_context())
        return Response(serializer.data)
    
    
    # -----------------------
    # Add a reply (POST)
    # -----------------------
    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def add_reply(self, request, reel_pk=None, pk=None):
        parent_comment = get_object_or_404(Comment, pk=pk)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user, reel_id=parent_comment.reel.id, parent=parent_comment)
        return Response(serializer.data, status=201)
    
    
    # perform update method
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
        reel = get_object_or_404(Reel, id=reel_id)
        profile = request.user.profile

        if profile.hidden_reels.filter(id=reel.id).exists():
            profile.hidden_reels.remove(reel)
            return Response({"status": "success", "message": "Reel unhidden"}, status=status.HTTP_200_OK)
        else:
            profile.hidden_reels.add(reel)
            return Response({"status": "success", "message": "Reel hidden"}, status=status.HTTP_200_OK)
    
    
        
        
# -----------------------
# Reel Report ViewSet
# -----------------------            
class ReportReelView(APIView):
    """
    API endpoint to allow authenticated users to report a reel.

    Endpoint: POST /api/reels/<reel_id>/report/
    Request body: {"reason": "spam" | "inappropriate" | "sexual" | "harassment" | "hate_speech" | "other", "other_text": "..."}
    """

    permission_classes = [permissions.IsAuthenticated]
    
    
    def get(self, request,  reel_id=None):
        """
        Return the list of available report reasons for the frontend.
        """
        reasons = [{"key": key, "label": label} for key, label in ReelReportSerializer.REASONS]
        return Response({"reasons": reasons})


    def post(self, request, reel_id):
        """
        Handle POST request to report a reel.
        """
        # Fetch the reel
        reel = get_object_or_404(Reel, id=reel_id)

        # Validate the report data using ReelReportSerializer
        serializer = ReelReportSerializer(data=request.data)
        if serializer.is_valid():
            reason = serializer.validated_data["reason"]
            other_text = serializer.validated_data.get("other_text", "")

            # Optional: enforce text if reason is "other"
            if reason == "other" and not other_text:
                return Response(
                    {"status": "error", "message": "Please provide a reason for 'Other'"},
                    status=400
                )

            # Add user to reports
            reel.reports.add(request.user)

            # Save last report reason (combine with text if "other")
            reel.last_report_reason = f"{reason}: {other_text}" if reason == "other" else reason
            reel.save()

            return Response({"status": "success", "message": "Reel reported successfully"})
        else:
            return Response(serializer.errors, status=400)
