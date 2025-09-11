from __future__ import annotations
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from users.views import (CurrentUserView, SignupView, LoginView, LogoutView, ForgotPasswordView, ResetPasswordView, ChangePasswordView
)

from users.views import ProfileViewSet

# DRF router for profile endpoints
router = DefaultRouter()
router.register(r'profiles', ProfileViewSet, basename='profile')


urlpatterns = [
    # Login endpoint
    path("me/", CurrentUserView.as_view(), name="user-detail"),
    
    # Signup endpoint
    path("signup/", SignupView.as_view(), name="signup"),
   
   # Login endpoint 
    path("login/", LoginView.as_view(), name="login"),
    
    # Logout endpoint
    path("logout/", LogoutView.as_view(), name="logout"),
    
    # Forget-Password endpoint
    path("forget-password/", ForgotPasswordView.as_view(), name="forget-password"),
    
    # Reset-Password endpoint
    path("reset-password/", ResetPasswordView.as_view(), name="reset-password"),
    
    # Change-Password endpoint
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),

    
     # Include profile viewset routes
    path("", include(router.urls)),
    
]