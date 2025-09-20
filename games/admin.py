from django.contrib import admin, messages
from django.core.mail import send_mail
from django.utils import timezone
from django.urls import reverse
from django.utils.html import format_html
from django.db.models import Count

from .models import Game, GameSubmission, GameHistory, WinningNumber, WinnerHistory, RewardMessage

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
    )
    list_filter = ("is_claimed", "reward_delivered", "prize_position", "game")
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

    def creator_link(self, obj):
        if obj.creator:
            url = reverse("admin:auth_user_change", args=(obj.creator.pk,))
            return format_html('<a href="{}">{}</a>', url, obj.creator.username)
        return "-"
    creator_link.short_description = "Creator"

    def close_and_select_winners(self, request, queryset):
        updated = 0
        for game in queryset.filter(is_active=True):
            game.close_game_and_select_winners()
            updated += 1
        self.message_user(request, f"{updated} game(s) closed and winners selected.", messages.SUCCESS)

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
