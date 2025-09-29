from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers


from .views import (
    GameViewSet,
    GameSubmissionViewSet,
    WinningNumberViewSet,
    GameHistoryViewSet,
    WinnerHistoryViewSet,
    RewardMessageViewSet,
    GameComplaintViewSet
)

# -----------------------
# Router Configuration
# -----------------------
# Using DRF's DefaultRouter to automatically generate RESTful routes
router = DefaultRouter()

# Game management endpoints
router.register(r'games', GameViewSet, basename='game')  # CRUD for games


# -----------------------
# Nested router for submissions
# -----------------------
games_router = routers.NestedDefaultRouter(router, r'games', lookup='game')
games_router.register(r'submissions', GameSubmissionViewSet, basename='game-submissions')


# Game participation / submissions
router.register(r'submissions', GameSubmissionViewSet, basename='submission')  # Submit guesses

# Winning numbers (for reference/admin)
router.register(r'winning-numbers', WinningNumberViewSet, basename='winningnumber')

# Game history endpoints
router.register(r'games-history', GameHistoryViewSet, basename='gamehistory')

# Winner history / reward claiming
router.register(r'winner-history', WinnerHistoryViewSet, basename='winnerhistory')

# Reward messages (in-app notifications)
router.register(r'reward-messages', RewardMessageViewSet, basename='rewardmessage')

# Game complaints (only winners can file, admin/staff manage)
router.register(r'game-complaint', GameComplaintViewSet, basename='gamecomplaint')

# -----------------------
# URL Patterns
# -----------------------
# Include all router-generated endpoints
urlpatterns = [
    path('', include(router.urls)),
    path('', include(games_router.urls)),
]
