from django.db import models
from django.conf import settings
from reels.models import Reel
from core.models.base import BaseModel
from django.utils import timezone


class Game(BaseModel):
    """
    Represents a guessing game where users can participate to win rewards.
    """

    # ---------------------
    # Reward Type Choices
    # ---------------------
    REWARD_TYPE_CHOICES = [
        ("cash", "Cash"),
        ("digital", "Digital"),
        ("product", "Product"),
    ]

    # ---------------------
    # Game Core Fields
    # ---------------------
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_games",
        help_text="User who created this game."
    )
    title = models.CharField(
        max_length=255,
        help_text="Title of the game."
    )
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Optional description of the game."
    )
    image = models.ImageField(
        upload_to="game_rewards/",
        help_text="Image representing the reward."
    )
    link = models.URLField(
        blank=True,
        null=True,
        help_text="Optional external link for the game."
    )

    # ---------------------
    # Reward & Winners
    # ---------------------
    reward_type = models.CharField(
        max_length=20,
        choices=REWARD_TYPE_CHOICES,
        help_text="Type of reward offered."
    )
    number_of_winners = models.PositiveIntegerField(
        default=1,
        help_text="Number of winners allowed."
    )

    # ---------------------
    # Game Rules (Guesses)
    # ---------------------
    guess_min = models.PositiveIntegerField(
        default=1,
        help_text="Minimum guess number."
    )
    guess_max = models.PositiveIntegerField(
        default=100,
        help_text="Maximum guess number."
    )

    # ---------------------
    # Related Content
    # ---------------------
    reel = models.ForeignKey(
        "reels.Reel",   # safer than direct import to avoid circular issues
        on_delete=models.CASCADE,
        related_name="games",
        blank=True,
        null=True,
        help_text="Optional reel linked to this game."
    )

    # ---------------------
    # Timing
    # ---------------------
    duration = models.DurationField(
        default=timezone.timedelta(hours=24),
        help_text="Game duration (default: 24 hours)."
    )
    end_time = models.DateTimeField(
        blank=True,
        null=True,
        help_text="End time (auto-calculated on save)."
    )

    # ---------------------
    # Security (Provably Fair)
    # ---------------------
    salt = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        editable=False,
        help_text="Random salt for hash generation."
    )
    hash_value = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        editable=False,
        help_text="Hash of winning numbers (for fairness verification)."
    )
    winning_numbers_encrypted = models.TextField(
        blank=True,
        null=True,
        editable=False,
        help_text="Encrypted winning numbers."
    )

    # ---------------------
    # Status
    # ---------------------
    is_active = models.BooleanField(
        default=True,
        help_text="Whether the game is active or soft-deleted."
    )

    # ---------------------
    # Methods
    # ---------------------
    def save(self, *args, **kwargs):
        """Auto-calculate end_time when creating a game."""
        if self.duration and not self.end_time:
            self.end_time = timezone.now() + self.duration
        super().save(*args, **kwargs)

    @property
    def participant_count(self):
        """Number of users who submitted guesses for this game."""
        return self.submissions.count()

    def __str__(self):
        return f"{self.title} (by {self.creator.username})"


# -----------------------
# WinningNumber Model
# -----------------------
class WinningNumber(BaseModel):
    """
    Stores each winning number for a game along with its prize and position.
    """

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="winning_numbers")
    number = models.PositiveIntegerField(help_text="The winning number for this game.")
    reward_description = models.TextField(blank=True, null=True)
    reward_image = models.ImageField(upload_to='game_rewards/', blank=True, null=True)
    reward_link = models.URLField(blank=True, null=True)
    reward_type = models.CharField(max_length=20, choices=Game.REWARD_TYPE_CHOICES)
    prize_position = models.PositiveIntegerField(default=1, help_text="1st prize, 2nd prize, etc.")
    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="won_numbers"
    )
    is_claimed = models.BooleanField(default=False, help_text="Has this winning number been claimed by someone?")

    class Meta:
        unique_together = ('game', 'number')  # Prevent duplicate winning numbers for a game

    def __str__(self):
        return f"Game: {self.game.title}, Number: {self.number}, Prize: {self.prize_position}"





class GameSubmission(BaseModel):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='submissions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    guessed_number = models.PositiveIntegerField()
    submitted_at = models.DateTimeField(default=timezone.now)
    is_winner = models.BooleanField(default=False)
    prize_position = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('game', 'user')

    def mark_winner(self, position: int = None):
        """Mark submission as winner and optionally assign prize_position."""
        self.is_winner = True
        if position is not None:
            self.prize_position = position
        self.save(update_fields=['is_winner', 'prize_position'])


# -----------------------
# Game History Model
# -----------------------
class GameHistory(BaseModel):
    """
    Stores immutable history of all games once they are completed.
    Includes basic info of the game, creator, rewards, and linked winners.
    """
    game = models.OneToOneField(Game, on_delete=models.CASCADE, related_name="history")
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    reward_type = models.CharField(max_length=20)
    number_of_winners = models.PositiveIntegerField()
    guess_min = models.PositiveIntegerField()
    guess_max = models.PositiveIntegerField()
    reel_id = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField()
    completed_at = models.DateTimeField(auto_now_add=True)
    decrypted_winning_numbers = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        verbose_name = "Game History"
        verbose_name_plural = "Game Histories"

    def __str__(self):
        return f"{self.title} by {self.creator.username if self.creator else 'Unknown'}"



    

# -----------------------
# Winner History Model
# -----------------------
class WinnerHistory(BaseModel):
    """
    Stores immutable record of winners for a completed game.
    Includes guessed number and prize details.
    """
    game_history = models.ForeignKey(
        GameHistory,
        on_delete=models.CASCADE,
        related_name="winners",
        blank=True,
        null=True,   # allow existing rows to be null
        help_text="Link to the related GameHistory record."
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    number = models.PositiveIntegerField(help_text="The number guessed by the winner.")
    prize_position = models.PositiveIntegerField(help_text="Winner's rank/position.")
    reward_type = models.CharField(max_length=20, help_text="Type of reward (cash/digital/product).")
    reward_description = models.TextField(blank=True, null=True, help_text="Description of the reward.")
    reward_image = models.ImageField(upload_to="winner_rewards/", blank=True, null=True)
    reward_link = models.URLField(blank=True, null=True, help_text="Optional link for reward claim.")
    claimed_at = models.DateTimeField(auto_now_add=True, help_text="When the reward was claimed/winner decided.")

    class Meta:
        verbose_name = "Winner History"
        verbose_name_plural = "Winner Histories"

    def __str__(self):
        return f"Winner {self.user.username if self.user else 'Unknown'} (GameHistory {self.game_history.id})"
