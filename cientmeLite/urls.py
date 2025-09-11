from __future__ import annotations
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static


from django.contrib import admin
from django.urls import path, include


from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView
)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('favicon.ico', RedirectView.as_view(url='/static/favicon.ico')),
    
    # Users app (authentication & profiles)
    path("api/users/", include("users.urls")),
    path("api/core/", include("core.urls")),
    path("api/reels/", include("reels.urls")),
    
    # JWT login endpoint (get access & refresh tokens)
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),

    # JWT refresh endpoint (get new access token)
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # JWT verify endpoint (verify token validity)
    path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
