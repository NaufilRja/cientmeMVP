from django.urls import path
from core.views import (
    SearchView,
    GameHistorySearchView,
    WinnerHistorySearchView,
   
)

urlpatterns = [
    # Existing search for users and reels
    path("search/", SearchView.as_view(), name="search"),

    # GameHistory search with optional creator filter
    path("games-history/search/", GameHistorySearchView.as_view(), name="gamehistory-search"),


    # WinnerHistory search for a specific game
    path("games/<int:game_id>/winners-history/search/", WinnerHistorySearchView.as_view(), name="winnerhistory-search"),

    
]
