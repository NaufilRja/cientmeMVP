from django.contrib import admin, messages
from django.core.mail import send_mail
from django.utils import timezone
from django.urls import reverse
from django.utils.html import format_html
from django.db.models import Count
from django.core.exceptions import ValidationError


from .models import Game, GameSubmission, GameHistory, WinningNumber, WinnerHistory, RewardChat, RewardMessage, GameReward, GameComplaint

# ------------------------
# --- Inlines
# ------------------------
class WinningNumberInline(admin.TabularInline):
    model = WinningNumber
    readonly_fields = ("number", "prize_position", "winner", "reward_type", "reward_description")
    can_delete = False
    extra = 0
    show_change_link = True

class WinnerHistoryInline(admin.TabularInline):
    model = WinnerHistory
    readonly_fields = (
        "user",
        "number",
        "prize_position",
        "is_claimed",
        "claimed_at",
        "reward_delivered",
        "reward_delivery_deadline",
        "reward_type",
        "reward_description",
        "reward_link",
    )
    can_delete = False
    extra = 0
    show_change_link = True
    
    

# ------------------------
# Reward Message Inline
# ------------------------
class RewardMessageInline(admin.StackedInline):
    model = RewardMessage
    fk_name = "winner_history"
    readonly_fields = ("sender", "message", "image", "created_at")
    extra = 0

# ------------------------
# --- Admin Actions
# ------------------------
@admin.action(description="Mark selected winner(s) as Claimed")
def mark_selected_claimed(modeladmin, request, queryset):
    updated = 0
    now = timezone.now()
    for obj in queryset.filter(is_claimed=False):
        obj.is_claimed = True
        obj.claimed_at = now
        obj.save(update_fields=["is_claimed", "claimed_at"])
        updated += 1
    modeladmin.message_user(request, f"{updated} winner(s) marked as claimed.", messages.SUCCESS)

@admin.action(description="Mark selected winner(s) as Reward Delivered")
def mark_selected_reward_delivered(modeladmin, request, queryset):
    updated = 0
    for obj in queryset.filter(reward_delivered=False):
        obj.reward_delivered = True
        obj.save(update_fields=["reward_delivered"])
        updated += 1
    modeladmin.message_user(request, f"{updated} winner(s) marked as delivered.", messages.SUCCESS)

@admin.action(description="Resend winner email(s)")
def resend_winner_emails(modeladmin, request, queryset):
    sent = 0
    for obj in queryset:
        user = getattr(obj, "user", None)
        game = getattr(obj, "game", None)
        if not user or not getattr(user, "email", None):
            continue
        subject = f"Congrats — you won in {game.title if game else 'the game'}!"
        body = (
            f"Hi {getattr(user, 'username', '')},\n\n"
            f"Congratulations — you won {obj.prize_position} for game '{getattr(game, 'title', '')}'.\n"
            f"Claim deadline: {obj.claim_deadline.strftime('%Y-%m-%d %H:%M') if getattr(obj, 'claim_deadline', None) else 'N/A'}\n\n"
            "Please claim your reward in the app.\n\nThanks,\nCientme Team"
        )
        try:
            send_mail(subject, body, None, [user.email], fail_silently=False)
            sent += 1
        except Exception:
            continue
    modeladmin.message_user(request, f"Attempted to send emails to {sent} winners.", messages.INFO)

# ------------------------
# --- WinnerHistory Admin
# ------------------------
@admin.register(WinnerHistory)
class WinnerHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_link",
        "game_link",
        "prize_position",
        "number",
        "is_claimed",
        "claimed_at",
        "reward_delivered",
        "reward_delivery_deadline",
        'forfeited',
    )
    list_filter = ("is_claimed", "reward_delivered", "prize_position", "game", 'forfeited',)
    search_fields = ("user__username", "game__title", "number")
    readonly_fields = (
        "user",
        "game",
        "number",
        "prize_position",
        "claimed_at",
        "reward_delivery_deadline",
    )
    actions = [mark_selected_claimed, mark_selected_reward_delivered, resend_winner_emails]
    inlines = [RewardMessageInline]

    def user_link(self, obj):
        if obj.user:
            url = reverse("admin:auth_user_change", args=(obj.user.pk,))
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return "-"
    user_link.short_description = "User"

    def game_link(self, obj):
        if obj.game:
            url = reverse("admin:games_game_change", args=(obj.game.pk,))
            return format_html('<a href="{}">{}</a>', url, obj.game.title)
        return "-"
    game_link.short_description = "Game"



# ------------------------
# --- Game Admin
# ------------------------
@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "creator_link",
        "reward_type",
        "number_of_winners",
        "external_link",
        "participant_count",
        "is_active",
        "winners_selected",
        "created_at",
        "end_time",
    )
    list_filter = ("is_active", "winners_selected", "reward_type")
    search_fields = ("title", "creator__username", "description")
    actions = ["close_and_select_winners"]
    change_list_template = "admin/game_changelist.html"

    # ------------------------
    # Read-only fields
    # ------------------------
    readonly_fields = (
        "creator",
        "participant_count",
        "is_active",
        "winners_selected",
        "created_at",
        "updated_at",
        "end_time",
        "salt",
        "hash_value",
        "winning_numbers_encrypted",
    )

    # Group fields logically for clarity
    fieldsets = (
        ("Game Info", {
            "fields": ("title", "description", "image", "creator", "reward_type", "number_of_winners"),
            "description": "🎨 Cover Image is optional, used as the game's banner/advertisement. Reward type is optional: first prize or all prizes if same kind."
        }),
        ("Prizes", {
            "fields": (
                "first_prize_image", "first_prize_link",
                "second_prize_image", "second_prize_link",
                "third_prize_image", "third_prize_link",
            ),
            "description": "⚡ First prize image is required. Links are optional. Second/Third prize images are optional."
        }),
        ("Rules", {"fields": ("guess_min", "guess_max", "reel")}),
        ("Timing", {"fields": ("duration", "end_time")}),
        ("Status", {"fields": ("is_active", "auto_close", "auto_select_winner", "winners_selected")}),
    )

    # ------------------------
    # Dashboard stats in changelist
    # ------------------------
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        total_games = Game.objects.count()
        active_games = Game.objects.filter(is_active=True).count()
        total_winners = WinnerHistory.objects.count()
        claimed_rewards = WinnerHistory.objects.filter(is_claimed=True).count()
        delivered_rewards = WinnerHistory.objects.filter(reward_delivered=True).count()

        extra_context["dashboard_stats"] = {
            "total_games": total_games,
            "active_games": active_games,
            "total_winners": total_winners,
            "claimed_rewards": claimed_rewards,
            "delivered_rewards": delivered_rewards,
        }
        return super().changelist_view(request, extra_context=extra_context)

    # ------------------------
    # Custom field methods
    # ------------------------
    def creator_link(self, obj):
        if obj.creator:
            url = reverse("admin:auth_user_change", args=(obj.creator.pk,))
            return format_html('<a href="{}">{}</a>', url, obj.creator.username)
        return "-"
    creator_link.short_description = "Creator"
    
    def external_link(self, obj):
        if obj.link:
            return format_html('<a href="{}" target="_blank">Visit</a>', obj.link)
        return "-"
    external_link.short_description = "Website"

    # ------------------------
    # Action: close and select winners
    # ------------------------
    def close_and_select_winners(self, request, queryset):
        updated = 0
        for game in queryset.filter(is_active=True).iterator():  # iterator() for large querysets
            game.close_game_and_select_winners()
            updated += 1
        self.message_user(request, f"{updated} game(s) closed and winners selected.", messages.SUCCESS)

    # ------------------------
    # Validation before save
    # ------------------------
    def save_model(self, request, obj, form, change):
        if not obj.title:
            raise ValidationError("Game title is required.")
        if not obj.description:
            raise ValidationError("Game description is required.")
        if not obj.first_prize_image:
            raise ValidationError("First prize image is required before saving the game.")
        # Optional: allow reward_type to be blank
        if obj.reward_type is None:
            obj.reward_type = None
        super().save_model(request, obj, form, change)
        
        
        

# ------------------------
# --- GameSubmission Admin (full dashboard)
# ------------------------
@admin.register(GameSubmission)
class GameSubmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "user_link", "game_link", "guessed_number", "is_winner", "prize_position", "submitted_at")
    list_filter = ("game", "is_winner")
    search_fields = ("user__username", "guessed_number")
    change_list_template = "admin/game_submission_changelist.html"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        total_submissions = GameSubmission.objects.count()
        total_winning_submissions = GameSubmission.objects.filter(is_winner=True).count()
        total_pending_submissions = total_submissions - total_winning_submissions
        submissions_per_game = (
            GameSubmission.objects.values("game__title")
            .annotate(total=Count("id"))
            .order_by("-total")
        )

        extra_context["dashboard_stats"] = {
            "total_submissions": total_submissions,
            "total_winning_submissions": total_winning_submissions,
            "total_pending_submissions": total_pending_submissions,
            "submissions_per_game": list(submissions_per_game),
        }

        return super().changelist_view(request, extra_context=extra_context)

    def user_link(self, obj):
        if obj.user:
            url = reverse("admin:auth_user_change", args=(obj.user.pk,))
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return "-"
    user_link.short_description = "User"

    def game_link(self, obj):
        if obj.game:
            url = reverse("admin:games_game_change", args=(obj.game.pk,))
            return format_html('<a href="{}">{}</a>', url, obj.game.title)
        return "-"
    game_link.short_description = "Game"
    
    

# ------------------------
# --- WinningNumber Admin
# ------------------------
@admin.register(WinningNumber)
class WinningNumberAdmin(admin.ModelAdmin):
    list_display = ("id", "game", "number", "prize_position", "winner", "reward_type")
    list_filter = ("game", "prize_position", "reward_type")
    search_fields = ("number",)
    
    


# ------------------------
# --- Game Reward Admin
# ------------------------
@admin.register(GameReward)
class GameRewardAdmin(admin.ModelAdmin):
    list_display = ('game', 'position', 'reward_title', 'reward_type', 'is_claimed')
    list_filter = ('reward_type', 'is_claimed', 'game')
    search_fields = ('reward_title', 'game__title')
    readonly_fields = ('is_claimed', 'claimed_at')
    ordering = ('game', 'position')
    

# ------------------------
# Reward Chat Admin
# ------------------------
@admin.register(RewardChat)
class RewardChatAdmin(admin.ModelAdmin):
    list_display = ('creator', 'winner', 'created_at', 'is_active')
    search_fields = ('creator__username', 'winner__username')
    list_filter = ('is_active',)


# ------------------------
# --- RewardMessage Admin
# ------------------------
@admin.register(RewardMessage)
class RewardMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "winner_history_link", "sender", "short_message", "created_at")
    readonly_fields = ("winner_history", "sender", "message", "image", "created_at")
    search_fields = ("winner_history__user__username", "sender__username", "message")

    def winner_history_link(self, obj):
        if obj.winner_history:
            url = reverse("admin:games_winnerhistory_change", args=(obj.winner_history.pk,))
            return format_html('<a href="{}">Winner #{}</a>', url, obj.winner_history.pk)
        return "-"
    winner_history_link.short_description = "Winner"

    def short_message(self, obj):
        return (obj.message[:75] + "...") if obj.message and len(obj.message) > 75 else (obj.message or "")
    short_message.short_description = "Message (preview)"

# ------------------------
# --- GameHistory Admin
# ------------------------
@admin.register(GameHistory)
class GameHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "game_link", "reward_type", "total_winners", "created_at", "completed_at")
    list_filter = ("reward_type",)
    search_fields = ("title", "game_id")

    def game_link(self, obj):
        if obj.game:
            url = reverse("admin:games_game_change", args=(obj.game.pk,))
            return format_html('<a href="{}">{}</a>', url, obj.game.title)
        return "-"
    game_link.short_description = "Game"

    def total_winners(self, obj):
        return WinnerHistory.objects.filter(game=obj.game).count() if obj.game else 0
    total_winners.short_description = "Total Winners"



@admin.register(GameComplaint)
class GameComplaintAdmin(admin.ModelAdmin):
    """
    Admin panel configuration for complaints.
    Provides quick visibility into complaints with filtering and search.
    """
    list_display = ("id", "user", "winner_history", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "message", "winner_history__game__title")
    readonly_fields = ("created_at",)
