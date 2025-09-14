from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested.routers import NestedDefaultRouter
from .views import ReelViewSet, CommentViewSet, HideReelView, ReportReelView

# Main DRF router
router = DefaultRouter()
router.register(r"reels", ReelViewSet, basename="reel")

# Nested router for comments under a reel
comments_router = NestedDefaultRouter(router, r"reels", lookup="reel")
comments_router.register(r"comments", CommentViewSet, basename="reel-comments")

# Nested router for replies under a comment
replies_router = NestedDefaultRouter(comments_router, r"comments", lookup="comment")
replies_router.register(r"replies", CommentViewSet, basename="comment-replies")


urlpatterns = [
    path("", include(router.urls)),
    path("", include(comments_router.urls)),
    path("", include(replies_router.urls)),

    # Hide Feature for Reel
    path("reels/hide/<int:reel_id>/", HideReelView.as_view(), name="hide-reel"),

    # Report Feature for Reel
    path("reels/<int:reel_id>/report/", ReportReelView.as_view(), name="report-reel"),
]
