from django.urls import path
from core.views import SearchView

urlpatterns = [
    path("search/", SearchView.as_view(), name="search"),
]