from __future__ import annotations

from rest_framework import status, generics, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.core.mail import send_mail
from django.conf import settings


from users.models import Profile
from .serializers import(SignupSerializer, LoginSerializer, UserSerializer, ForgotPasswordSerializer, ResetPasswordSerializer, ProfileSerializer, ChangePasswordSerializer
)

from core.mixins.action_mixins import OwnerActionsMixin
from core.permissions.general import IsProfileOwnerOrReadOnly, IsActiveUser, AllowReadOnly


from django.contrib.auth import get_user_model


User = get_user_model() 


# -----------------------
# Profile View
# -----------------------   
class ProfileViewSet(OwnerActionsMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing user profiles.

    Features:
    - List all profiles (read-only for non-staff)
    - Retrieve profile details
    - Update own profile (owner only)
    - Activate / Deactivate profile (soft delete using BaseModel)
    - Uses OwnerActionsMixin for standard success/fail responses
    """    
    
    
    serializer_class = ProfileSerializer
    queryset = Profile.objects.select_related("user").all()
    
    
    # Permissions: 
    # - Active users only
    # - Owners can edit their own profile
    # - Others have read-only access
    permission_classes = [IsActiveUser, IsProfileOwnerOrReadOnly | AllowReadOnly]
    
    
    lookup_field = "user__username"  # Allow retrieving profile by username


    def get_queryset(self):
        """
        Customize queryset:
        - Only active profiles by default
        - Prefetch followers for efficiency
        """
        qs = super().get_queryset().filter(is_active=True)
        qs = qs.prefetch_related("followers")
        return qs
    
    
    
    @action(
        detail=True,
        methods=["post"],
        url_path="follow",
        permission_classes=[permissions.IsAuthenticated]  # Only logged-in users can follow/unfollow

    )
    def follow(self, request, user__username=None):
        username = self.kwargs.get("user__username")
        profile = get_object_or_404(Profile, user__username=username, is_active=True)
        user = request.user

        # Prevent following self
        if user == profile.user:
            return self.success({"message": "You cannot follow yourself."})

        # Toggle follow/unfollow
        if user in profile.followers.all():
            profile.followers.remove(user)
            return self.success({
            "message": "Unfollowed successfully.",
            "followers_count": profile.followers.count()
        })

        profile.followers.add(user)
        return self.success({
        "message": "Followed successfully.",
        "followers_count": profile.followers.count()
        })
        
        
    # -----------------------
    # Followers count action
    # -----------------------
    @action(
        detail=True,
        methods=["get"],
        url_path="followers-count",
        permission_classes=[permissions.AllowAny]  # Anyone can check followers count
    )
    def followers_count(self, request, user__username=None):
        """
        Return the number of followers for this profile.
        """
        username = self.kwargs.get("user__username")
        profile = get_object_or_404(Profile, user__username=username, is_active=True)
        return self.success({"followers_count": profile.followers.count()})



# -----------------------
# Current User Detail View
# -----------------------
class CurrentUserView(generics.RetrieveAPIView):
    """
    API endpoint to fetch the currently authenticated user's details.
    Requires JWT or Session authentication.
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        """Return the currently logged-in user."""
        return self.request.user


# -----------------------
# Signup View
# -----------------------
class SignupView(generics.CreateAPIView):
    """
    API endpoint for user signup.
    - Allows anonymous users to create accounts.
    - Uses SignupSerializer for validation & user creation.
    """
    queryset = User.objects.all()
    serializer_class = SignupSerializer
    permission_classes = [permissions.AllowAny]
    
    
    def create(self, request, *args, **kwargs):
        """
        Override create to customize response structure.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()  # Creates the user
        
        return Response({
    "message": "User registered successfully! Please login to continue.",
    "user": {
        "id": user.id,
        "username": user.username,
        "email": user.email,
    }
}, status=status.HTTP_201_CREATED)

        
        

# -----------------------
# Login View
# -----------------------
class LoginView(APIView):
    """
    API endpoint for user login.
    Generates JWT tokens (access + refresh) for valid credentials.
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, *args, **kwargs):
        """
        Handle POST request for login.
        """
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)


        user = serializer.validated_data["user"]

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                },
            },
            status=status.HTTP_200_OK
        )
        
        
# -----------------------
# Login View
# -----------------------        
class LogoutView(APIView):
    """
    Handle user logout by blacklisting the refresh token.
    Requires the refresh token to be sent in the request body.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        """
        Invalidate the refresh token to log out the user.
        Expected JSON body: {"refresh": "<refresh_token>"}
        """
        refresh_token = request.data.get("refresh")
        
        if not refresh_token:
            return Response(
                {"detail": "Refresh token is required for logout."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()  # Blacklist the token
            return Response({"detail": "Logout successful."}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({"detail": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)
        
        
# -----------------------
# Forgot Password View
# -----------------------
class ForgotPasswordView(generics.GenericAPIView):
    """
    API to request a password reset email.
    User provides their registered email and receives a password reset link.
    """
    serializer_class = ForgotPasswordSerializer
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        user = User.objects.get(email=email)
        
        # Generate token and UID for reset link
        token = PasswordResetTokenGenerator().make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))


        # Construct reset URL for frontend
        reset_url = f"{request.scheme}://{request.get_host()}/reset-password/?uid={uid}&token={token}"


        # Send reset email
        send_mail(
            subject="Password Reset Request",
            message=f"Hi {user.username},\nUse this link to reset your password:\n{reset_url}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        
        return Response({"detail": "Password reset link sent to your email."}, status=status.HTTP_200_OK)


# -----------------------
# Reset Password View
# -----------------------
class ResetPasswordView(generics.GenericAPIView):
    """
    API to reset password using token and UID from email link.
    """
    serializer_class = ResetPasswordSerializer
    permission_classes = [permissions.AllowAny]
    
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        serializer.save()  # This sets the new password
        return Response({"detail": "Password reset successful."}, status=status.HTTP_200_OK)
    
    
 
 
 


# -----------------------
# Change Password View
# -----------------------     
class ChangePasswordView(generics.UpdateAPIView):
    """
    Allows authenticated users to change their password.
    """
    serializer_class = ChangePasswordSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user


    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password updated successfully."}, status=status.HTTP_200_OK)
    
    
 
