from django.contrib import admin
from .models import Reel, Comment, Share, Audio, Tag


# -----------------------
# Comment Inline for Reel
# -----------------------
class CommentInline(admin.TabularInline):
    model = Comment
    extra = 1
    readonly_fields = ("user", "created_at", "updated_at")
    fields = ("user", "comment", "parent", "likes", "created_at")
    filter_horizontal = ("likes",)


# -----------------------
# Share Inline for Reel
# -----------------------
class ShareInline(admin.TabularInline):
    model = Share
    extra = 0
    readonly_fields = ("sharer", "points_earned", "badge_earned", "created_at")


# -----------------------
# Tag Admin
# -----------------------
@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}  # auto-generate slug from name
    ordering = ("name",)




# -----------------------
# Reel Admin
# -----------------------
@admin.register(Reel)
class ReelAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "user",
        "is_ad",
        "views",
        "likes_count",
        "saves_count",
        "shares",
        "reach",
        "created_at",
    )
    list_filter = ("is_ad", "is_banned", "created_at")
    search_fields = ("title", "user__username")
    inlines = [CommentInline, ShareInline]
    readonly_fields = ("video_size_mb", "video_duration")

    def likes_count(self, obj):
        return obj.likes.count()
    likes_count.short_description = "Likes"

    def saves_count(self, obj):
        return obj.saves.count()
    saves_count.short_description = "Saves"

    def reach(self, obj):
        """
        Example: Define reach as views + shares.
        Adjust formula as per your business logic.
        """
        return obj.views + obj.shares
    reach.short_description = "Reach"


# -----------------------
# Comment Admin
# -----------------------
@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("user", "reel", "parent", "likes_count", "created_at")
    search_fields = ("user__username", "reel__title", "comment")
    list_filter = ("created_at",)
    readonly_fields = ("likes",)

    def likes_count(self, obj):
        return obj.likes.count()
    likes_count.short_description = "Likes"


# -----------------------
# Share Admin
# -----------------------
@admin.register(Share)
class ShareAdmin(admin.ModelAdmin):
    list_display = ("sharer", "reel", "points_earned", "badge_earned", "created_at")
    search_fields = ("sharer__username", "reel__title")
    list_filter = ("badge_earned", "created_at")
    readonly_fields = ("points_earned", "badge_earned", "created_at")


# -----------------------
# Audio Admin
# -----------------------
@admin.register(Audio)
class AudioAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "created_by", "duration", "is_from_reel", "reels_count", "created_at")
    search_fields = ("title", "created_by__username")
    list_filter = ("is_from_reel", "created_at")
    readonly_fields = ("reels_count",)
