from rest_framework.routers import DefaultRouter
from .views import (
    GameViewSet,
    GameSubmissionViewSet,
    WinningNumberViewSet,
    GameHistoryViewSet,
    WinnerHistoryViewSet,
)

router = DefaultRouter()
router.register(r'games', GameViewSet, basename='game')
router.register(r'submissions', GameSubmissionViewSet, basename='submission')
router.register(r'winning-numbers', WinningNumberViewSet, basename='winning-number')
router.register(r'game-history', GameHistoryViewSet, basename='game-history')
router.register(r'winner-history', WinnerHistoryViewSet, basename='winner-history')

urlpatterns = router.urls
