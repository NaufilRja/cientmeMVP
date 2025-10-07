from django.urls import path
from core.views import (
    SearchView,
    GameHistorySearchView,
    WinnerHistorySearchView,
    RewardMessageSearchView
)

urlpatterns = [
    # Existing search for users and reels
    path("search/", SearchView.as_view(), name="search"),

    # GameHistory search with optional creator filter
    path("games/search/", GameHistorySearchView.as_view(), name="gamehistory-search"),

    # WinnerHistory search for a specific game
    path("games/<int:game_id>/winners/search/", WinnerHistorySearchView.as_view(), name="winnerhistory-search"),

    # RewardMessage search for a specific chat
    path("games/reward-messages/<int:reward_chat_id>/search/", RewardMessageSearchView.as_view(), name="rewardmessage-search"),
]
