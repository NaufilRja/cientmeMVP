from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.contrib.auth import authenticate, get_user_model
from django.utils.encoding import force_str 
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from users.models import Profile



# Get the custom user model dynamically
User = get_user_model()



# -----------------------
# Profile Serializer
# -----------------------
class ProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for the Profile model.
    Includes dynamic followers_count and list of follower IDs.
    """
    user = serializers.ReadOnlyField(source='user.username')

    # Dynamic property for number of followers
    followers_count = serializers.ReadOnlyField()
    
    
   # Show followers as list of usernames
    followers = serializers.SerializerMethodField()
    
    class Meta:
        model = Profile
        fields = [
            'id',  
            'user', 
            "total_share_points",
            "badge_earned",
            "badge_name",        
            'avatar',
            'bio',
            'generic_link',
            'qr_code',
            'followers',       # List of follower user IDs
            'followers_count', # Dynamic number of followers
            'hidden_reels',
            'created_at',    # match BaseModel
            'updated_at',
        ]
        
        read_only_fields = [
            'id',
            'user',  # ensure it's read-only
            'followers',
            'followers_count',
            'date_created',
            'date_updated',
        ]
    
    
    def get_followers(self, obj):
        """Return list of usernames instead of IDs."""
        return [user.username for user in obj.followers.all()]




# -----------------------
# User Serializer
# -----------------------
class UserSerializer(serializers.ModelSerializer):
    """Serializer for returning user details."""
    profile = ProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'username',
            "profile", 
            'name',
            'avatar',
            'is_active',
            'is_staff',
            'date_joined',
        ]
        read_only_fields = ['id', 'is_active', 'is_staff', 'date_joined', 'profile']


class SimpleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "avatar",
        ]


# -----------------------
# Signup Serializer
# -----------------------
class SignupSerializer(serializers.ModelSerializer):
    """Serializer for handling user signup."""

    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'password2']
        extra_kwargs = {
            'password': {'write_only': True},
            'email': {'required': True}
        }

    def validate_email(self, value):
        """Ensure email is unique."""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value

    def validate_username(self, value):
        """Ensure username is unique."""
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value

    def validate(self, attrs):
        """Ensure passwords match."""
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        validate_password(attrs['password'])
        return attrs

    def create(self, validated_data):
        """Create user with hashed password."""
        validated_data.pop('password2')
        user = User.objects.create_user(
            email=validated_data['email'],
            username=validated_data['username'],
            password=validated_data['password'],
        )
        return user



# -----------------------
# Login Serializer
# -----------------------
class LoginSerializer(serializers.Serializer):
    """
    Serializer for handling user login.
    Accepts username or email along with password for authentication.
    """
    
    username_or_email = serializers.CharField(
        required=True,
        help_text="Enter your username or email."
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        help_text="Enter your password."
    )
    
    def validate(self, attrs):
        """
        Validate user credentials.
        Allow login with either username or email.
        """
        username_or_email = attrs.get("username_or_email")
        password = attrs.get("password")

        # First try to authenticate with username
        user = authenticate(username=username_or_email, password=password)

        # If not authenticated with username, try email
        if user is None:
            try:
                user_obj = User.objects.get(email=username_or_email)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass

        if user is None:
            raise serializers.ValidationError("Invalid username, email, or password..")

        if not user.is_active:
            raise serializers.ValidationError("This account is inactive.")

        attrs["user"] = user
        return attrs
    
    
# -----------------------
# Forgot Password Serializer
# -----------------------
class ForgotPasswordSerializer(serializers.Serializer):
    """
    Serializer to request a password reset email.
    Only requires email to be provided.
    """
    email = serializers.EmailField(required=True, help_text="Enter the registered email.")

    def validate_email(self, value):
        """Ensure email exists in the system."""
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("No user is registered with this email.")
        return value


# -----------------------
# Reset Password Serializer
# -----------------------
class ResetPasswordSerializer(serializers.Serializer):
    """
    Serializer to reset user password.
    Requires uid (base64 encoded), token (from email), new password and confirm password.
    """
    uid = serializers.CharField(required=True)
    token = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    def validate(self, attrs):
        """Check if passwords match."""
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    def validate_token(self, value):
        """Optional token validation can be added here if needed."""
        return value

    def save(self):
        """Set new password for user."""
        uid = self.validated_data['uid']
        token = self.validated_data['token']
        password = self.validated_data['password']

        try:
            uid = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"uid": "Invalid UID."})

        if not PasswordResetTokenGenerator().check_token(user, token):
            raise serializers.ValidationError({"token": "Invalid or expired token."})

        # Set the new password
        user.set_password(password)
        user.save()
        return user
    
    
 
# -----------------------
# Change Password Serializer
# -----------------------    
class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for allowing users to change their password.
    Requires old password, new password, and confirmation.
    """    
    
    old_password = serializers.CharField(write_only=True, required=True, help_text="Current password")
    new_password = serializers.CharField(write_only=True, required=True, validators=[validate_password], help_text="New password")
    new_password2 = serializers.CharField(write_only=True, required=True, help_text="Confirm new password")


    def validate_old_password(self, value):
        """Check that old password is correct."""
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value
    
    
    def validate(self, attrs):
        """Ensure new passwords match."""
        if attrs["new_password"] != attrs["new_password2"]:
            raise serializers.ValidationError({"new_password2": "Passwords do not match."})
        return attrs
    
    
    def save(self, **kwargs):
        """Set the new password for the user."""
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save()
        return user
    
    
    
     
