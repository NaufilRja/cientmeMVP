from django.urls import path, include
from rest_framework_nested import routers
from .views import (
    GameViewSet,
    GameSubmissionViewSet,
    WinningNumberViewSet,
    GameHistoryViewSet,
    WinnerHistoryViewSet,
    RewardMessageViewSet,
    GameComplaintViewSet,
    UnplayedGamesListView,
    ChatListView

)

# -----------------------
# Main router
# -----------------------
router = routers.DefaultRouter()

# Game management endpoints
router.register(r'active-games', GameViewSet, basename='game')

# Game submissions (flat route, optional if you still want global access)
router.register(r'submissions', GameSubmissionViewSet, basename='submission')

# Winning numbers (for reference/admin)
router.register(r'winning-numbers', WinningNumberViewSet, basename='winningnumber')

# Game history
router.register(r'games-history', GameHistoryViewSet, basename='gamehistory')

# Winner history (filtered internally by user / optional game_id)
router.register(r'winner-history', WinnerHistoryViewSet, basename='winner-history')

# Reward messages
router.register(r'reward-messages', RewardMessageViewSet, basename='rewardmessage')

# Game complaints
router.register(r'game-complaint', GameComplaintViewSet, basename='gamecomplaint')

# -----------------------
# Nested router for submissions under a specific game
# -----------------------
games_router = routers.NestedDefaultRouter(router, r'active-games', lookup='game')
games_router.register(r'submissions', GameSubmissionViewSet, basename='game-submissions')

# -----------------------
# URL Patterns
# -----------------------
urlpatterns = [
    path('', include(router.urls)),        # Main routes
    path('', include(games_router.urls)),  # Nested routes
        
    
    path('unplayed/', UnplayedGamesListView.as_view(), name='unplayed-games'),
    path('reward-chat-list/', ChatListView.as_view(), name='reward-chat-list'),
]
