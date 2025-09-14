from django.db import models
from django.conf import settings
from core.models.base import BaseModel
from reels.models import Reel
from core.utils.validators import validate_image_file_size, validate_http_url
from core.utils.upload_paths import user_avatar_upload_to
from core.constants import BIO_MAX_LENGTH, USERNAME_MAX_LENGTH, EMAIL_MAX_LENGTH


from django.contrib.auth.models import (
    AbstractBaseUser, BaseUserManager, PermissionsMixin
)
from django.utils import timezone



# -----------------------
# Custom User Manager
# -----------------------
class UserManager(BaseUserManager):
    """
    Custom manager for User model.
    Handles:
    - create_user (for normal users)
    - create_superuser (for admin users)
    Uses email as the unique identifier instead of username.
    """

    def create_user(self, email, username, password=None, **extra_fields):
        """
        Create and return a regular user.
        """
        if not email:
            raise ValueError("The Email field is required.")
        if not username:
            raise ValueError("The Username field is required.")

        # Normalize email (lowercase domain part)
        email = self.normalize_email(email)

        # Create user instance
        user = self.model(email=email, username=username, **extra_fields)

        # Set hashed password
        user.set_password(password)

        # Save user to database
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password=None, **extra_fields):
        """
        Create and return a superuser (admin user).
        Ensures:
        - is_staff = True
        - is_superuser = True
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, username, password, **extra_fields)


# -----------------------
# Custom User Model
# -----------------------
class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model for production:
    - Uses email as unique identifier (USERNAME_FIELD)
    - Includes username, avatar, bio for profile
    - Includes is_staff and is_active flags for permission handling
    with ban control
    """

    # Core authentication fields
    email = models.EmailField(max_length=EMAIL_MAX_LENGTH, unique=True, help_text="User's email address (used for login).")
    username = models.CharField(max_length=USERNAME_MAX_LENGTH, unique=True, help_text="Unique username for the user.")
    name = models.CharField(max_length=30, blank=True, help_text="Full name of the user (optional).")

    # Permission-related fields
    is_staff = models.BooleanField(
        default=False,
        help_text="Designates whether the user can access the Django admin site."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this user should be treated as active."
    )

    # Other useful fields
    date_joined = models.DateTimeField(default=timezone.now, help_text="When the user joined.")
    avatar = models.ImageField(
        upload_to="avatars/",
        blank=True,
        null=True,
        help_text="Optional profile picture."
    )
    
    created_at = models.DateTimeField(auto_now_add=True) 
    updated_at = models.DateTimeField(auto_now=True, )
    
    is_banned = models.BooleanField(default=False, help_text="Ban this user from using the app")

    def ban(self):
        """Ban user and deactivate account."""
        self.is_banned = True
        self.is_active = False  # built-in field (prevents login)
        self.save()

    def unban(self):
        """Unban user and reactivate account."""
        self.is_banned = False
        self.is_active = True
        self.save()

    # Attach custom manager
    objects = UserManager()

    # Authentication settings
    USERNAME_FIELD = "email"           # Email will be used for login
    REQUIRED_FIELDS = ["username"]     # Username is required when creating superuser

    def __str__(self):
        """String representation for admin panel and debugging."""
        return self.email



# -----------------------
# Users Profiles
# -----------------------
class Profile(BaseModel):
    """
    Profile model linked one-to-one with the custom User model.
    Stores additional information like avatar, bio, social links, and QR code.
    """

    # One-to-one relationship with User
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        help_text="Link to the user account."
    )

    # Optional profile fields
    avatar = models.ImageField(
        upload_to=user_avatar_upload_to,
        blank=True,
        null=True,
        help_text="Optional profile picture.",
        validators=[validate_image_file_size]
    )
    bio = models.CharField(
        max_length=BIO_MAX_LENGTH,
        blank=True,
        null=True,
        help_text="Short bio for the user."
    )
    generic_link = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Optional  Instagram/Youtube profile link.",
        validators=[validate_http_url]
    )
   
    qr_code = models.ImageField(
        upload_to="profile_qrcodes/",
        blank=True,
        null=True,
        help_text="Optional QR code image for the user."
    )
    
    
    # Followers system
    followers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="following_profiles",
        help_text="Users who follow this profile."
    )

   
    engaged_tags = models.ManyToManyField(
        "reels.Tag",
        blank=True,
        related_name="engaged_by_profiles",
        help_text="Tags the user interacts with or likes."
    )

    # -----------------------
    # Hidden Reels (for Hide feature)
    # -----------------------
    hidden_reels = models.ManyToManyField(
        Reel,
        blank=True,
        related_name='hidden_by',
        help_text="Reels hidden by the user, will not appear in their feed."
    )
    
    total_share_points = models.PositiveIntegerField(default=0)
    badge_type = models.CharField(
        max_length=10,
        choices=[("silver", "Silver"), ("gold", "Gold"), ("black", "Black")],
        null=True,
        blank=True
    )


    # store badge display info
    badge_name = models.CharField(max_length=50, default="Blue Tick")
    
    # -----------------------
    # TOTAL REACH FIELD
    # -----------------------
    total_reach = models.PositiveIntegerField(default=0, help_text="Sum of reach from all user's reels.")

    
    def __str__(self):
        """
        String representation: returns the user's username.
        """
        return self.user.username
    
    
    @property
    def followers_count(self):
        """Dynamic followers count."""
        return self.followers.count()
    
    
    # -----------------------
    # TOTAL REACH
    # -----------------------
    def recompute_total_reach(self):
        """Recalculate and update total reach from user's reels."""
        total = Reel.objects.filter(user=self.user).aggregate(total=models.Sum("reach"))["total"] or 0
        self.total_reach = total
        self.save(update_fields=["total_reach"])
        return self.total_reach