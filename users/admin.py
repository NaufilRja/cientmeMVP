from django.contrib import admin
from .models import User, Profile


# -----------------
#   User Admin       
# -----------------
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('id', 'email', 'is_active', 'is_staff')
    list_display_links = ('id', 'email')
    search_fields = ('email', 'bio')
    list_filter = ('is_active', 'is_staff')
    fields = ('email', 'bio', 'is_active', 'is_staff', 'password')


# -----------------
#   Profile Admin
# -----------------
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'bio',
        'followers_count',
        'total_share_points',
        'badge_earned',
        'badge_name'
    )
    list_display_links = ('id', 'user')
    search_fields = ('user__username', 'bio')
    list_filter = ('user__is_active', 'badge_earned')
    readonly_fields = ('followers_count', 'total_share_points', 'badge_earned')
