# urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    GameViewSet,
    GameSubmissionViewSet,
    WinningNumberViewSet,
    GameHistoryViewSet,
    WinnerHistoryViewSet,
    RewardMessageViewSet
)

# -----------------------
# Router
# -----------------------
router = DefaultRouter()
router.register(r'games', GameViewSet, basename='game')
router.register(r'submissions', GameSubmissionViewSet, basename='submission')
router.register(r'winning-numbers', WinningNumberViewSet, basename='winningnumber')
router.register(r'game-history', GameHistoryViewSet, basename='gamehistory')
router.register(r'winner-history', WinnerHistoryViewSet, basename='winnerhistory')
router.register(r'reward-messages', RewardMessageViewSet, basename='rewardmessage')

# -----------------------
# URL Patterns
# -----------------------
urlpatterns = [
    path('', include(router.urls)),
]
