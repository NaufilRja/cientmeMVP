from django.contrib import admin
from .models import Game, GameSubmission, WinningNumber, GameHistory, WinnerHistory

# -----------------------
# GameSubmission Inline
# -----------------------
class GameSubmissionInline(admin.TabularInline):
    """
    Inline admin for GameSubmission.
    Allows viewing submissions directly in the Game admin.
    Submissions are read-only and cannot be deleted.
    """
    model = GameSubmission
    extra = 0
    readonly_fields = ('user', 'guessed_number', 'submitted_at', 'is_winner', 'prize_position')
    can_delete = False
    show_change_link = True



@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('title', 'creator', 'reward_type', 'number_of_winners', 'participant_count',
                    'guess_min', 'guess_max', 'is_active', 'reel', 'hash_value')
    list_filter = ('reward_type', 'is_active', 'creator')
    search_fields = ('title', 'creator__username', 'description')
    readonly_fields = ('creator', 'salt', 'hash_value','participant_count', 'winning_numbers_encrypted')
    inlines = [GameSubmissionInline]
    fields = (
        'title', 'creator', 'description', 'image', 'link', 'reward_type','number_of_winners',
        'guess_min', 'guess_max', 'reel', 'duration', 'end_time', 'is_active',
        'salt', 'hash_value', 'winning_numbers_encrypted'
    )

    def save_model(self, request, obj, form, change):
        if not obj.creator_id:
            obj.creator = request.user
        super().save_model(request, obj, form, change)



# -----------------------
# GameSubmission Admin
# -----------------------
@admin.register(GameSubmission)
class GameSubmissionAdmin(admin.ModelAdmin):
    """
    Admin interface for GameSubmission model.
    
    Features:
    - List display of key fields
    - Filter by game and winner status
    - Searchable by user, game, and guessed number
    - All fields read-only
    """
    list_display = ('user', 'game', 'guessed_number', 'submitted_at', 'is_winner', 'prize_position')
    list_filter = ('is_winner', 'game')
    search_fields = ('user__username', 'game__title', 'guessed_number')
    readonly_fields = ('user', 'game', 'guessed_number', 'submitted_at', 'is_winner', 'prize_position')


# -----------------------
# WinningNumber Admin
# -----------------------
@admin.register(WinningNumber)
class WinningNumberAdmin(admin.ModelAdmin):
    """
    Admin interface for WinningNumber model.
    
    Features:
    - Shows prize numbers, reward info, and winner if claimed
    - Filter by game and prize position
    - Searchable by number and game
    - Winner fields read-only
    """
    list_display = ('number', 'game', 'prize_position', 'winner', 'is_claimed')
    list_filter = ('game', 'prize_position', 'is_claimed')
    search_fields = ('number', 'game__title', 'winner__username')
    readonly_fields = ('winner', 'is_claimed')


# -----------------------
# GameHistory Admin
# -----------------------
@admin.register(GameHistory)
class GameHistoryAdmin(admin.ModelAdmin):
    """
    Admin interface for GameHistory model.
    
    Features:
    - View immutable history of games
    - Filter by creator
    - Searchable by title and creator
    """
    list_display = ('title', 'creator', 'number_of_winners', 'reward_type', 'guess_min', 'guess_max', 'created_at', 'completed_at')
    list_filter = ('creator', 'reward_type')
    search_fields = ('title', 'creator__username')
    readonly_fields = ('game', 'creator', 'title', 'description', 'reward_type', 'number_of_winners', 'guess_min', 'guess_max', 'reel_id', 'created_at', 'completed_at')


# -----------------------
# WinnerHistory Admin
# -----------------------
@admin.register(WinnerHistory)
class WinnerHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'game_history', 'number', 'prize_position', 'reward_type', 'claimed_at')
    list_filter = ('game_history', 'reward_type')
    search_fields = ('user__username', 'game_history__title', 'number')
    readonly_fields = (
        'game_history',
        'user',
        'number',
        'prize_position',
        'reward_type',
        'reward_description',
        'reward_image',
        'reward_link',
        'claimed_at'
    )
