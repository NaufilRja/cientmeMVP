from django.db import models
from django.conf import settings
from core.models.base import BaseModel
from django.utils import timezone
from datetime import timedelta
from cryptography.fernet import Fernet
from django.core.mail import send_mail
from rest_framework.exceptions import ValidationError
import random
import string
import hashlib



# -----------------------
# GAME MODEL
# -----------------------
class Game(BaseModel):
    """
    Represents a guessing game where users can participate to win rewards.
    """

    REWARD_TYPE_CHOICES = [
        ("cash", "Cash"),
        ("digital", "Digital"),
        ("product", "Product"),
    ]

    # Core fields
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_games",
        help_text="User who created this game."
    )
    title = models.CharField(max_length=255, help_text="Title of the game.")
    description = models.TextField(blank=True, null=True, help_text="Optional description of the game.")
    image = models.ImageField(upload_to="game_rewards/", help_text="Image representing the reward.")
    link = models.URLField(blank=True, null=True, help_text="Optional external link for the game.")

    # Reward & Winners
    reward_type = models.CharField(max_length=20, choices=REWARD_TYPE_CHOICES, help_text="Type of reward offered.")
    number_of_winners = models.PositiveIntegerField(default=1, help_text="Number of winners allowed.")

    # Game rules
    guess_min = models.PositiveIntegerField(default=1, help_text="Minimum guess number.")
    guess_max = models.PositiveIntegerField(default=100, help_text="Maximum guess number.")

    # Related content
    reel = models.ForeignKey(
        "reels.Reel",
        on_delete=models.SET_NULL,
        related_name="games",
        blank=True,
        null=True,
        help_text="Optional reel linked to this game."
    )

    # Timing
    duration = models.DurationField(default=timezone.timedelta(hours=24), help_text="Game duration (default: 24 hours).")
    end_time = models.DateTimeField(blank=True, null=True, help_text="End time (auto-calculated on save).")

    # Security & provably fair
    salt = models.CharField(max_length=255, blank=True, null=True, editable=False, help_text="Random salt for hash generation.")
    hash_value = models.CharField(max_length=255, blank=True, null=True, editable=False, help_text="Hash of winning numbers (for fairness verification).")
    winning_numbers_encrypted = models.TextField(blank=True, null=True, editable=False, help_text="Encrypted winning numbers.")

    # Status & auto-close
    is_active = models.BooleanField(default=True, help_text="Whether the game is active or soft-deleted.")
    auto_close = models.BooleanField(default=True, help_text="Whether the game should auto-close when end_time is reached.")
    auto_select_winner = models.BooleanField(default=True, help_text="Automatically select winners when game closes.")
    winners_selected = models.BooleanField(default=False, help_text="Whether winners have already been selected.")

    # ---------------------
    # Save method
    # ---------------------
    def save(self, *args, **kwargs):
        if self.duration and not self.end_time:
            self.end_time = timezone.now() + self.duration
        if not self.salt:
            self.salt = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        super().save(*args, **kwargs)

    def clean(self):
        if self.pk and self.submissions.exists() and not self.is_active:
            raise ValidationError("Cannot delete a game with participants.")

    @property
    def participant_count(self):
        return self.submissions.count()

    def __str__(self):
        return f"{self.title} (by {self.creator.username})"

    # ---------------------
    # Auto-close and winner selection
    # ---------------------
    def close_game_and_select_winners(self):
        if not self.auto_close or not self.is_active:
            return

        self.is_active = False
        self.save(update_fields=['is_active'])

        decrypted_numbers = []
        if self.winning_numbers_encrypted:
            try:
                fernet = Fernet(settings.FERNET_SECRET_KEY)
                decrypted_str = fernet.decrypt(self.winning_numbers_encrypted.encode()).decode()
                decrypted_numbers = [int(n) for n in decrypted_str.split(",")]
            except Exception as e:
                print(f"Failed to decrypt winning numbers: {e}")
                return

        game_history = GameHistory.objects.create(
            game=self,
            creator=self.creator,
            title=self.title,
            description=self.description,
            reward_type=self.reward_type,
            number_of_winners=self.number_of_winners,
            guess_min=self.guess_min,
            guess_max=self.guess_max,
            reel=self.reel,
            created_at=self.created_at
        )

        submissions = self.submissions.filter(submitted_at__lte=self.end_time).order_by("submitted_at")

        if len(decrypted_numbers) < self.number_of_winners:
            remaining_needed = self.number_of_winners - len(decrypted_numbers)
            random_subs = submissions.exclude(guessed_number__in=decrypted_numbers)[:remaining_needed]
            decrypted_numbers.extend([s.guessed_number for s in random_subs])

        position = 1
        for number in decrypted_numbers:
            if position > self.number_of_winners:
                break
            winner_submission = submissions.filter(guessed_number=number).first()
            if not winner_submission:
                continue

            wn, _ = WinningNumber.objects.get_or_create(
                game=self,
                number=number,
                defaults={
                    "prize_position": position,
                    "reward_description": self.description,
                    "reward_type": self.reward_type,
                    "reward_image": self.image,
                    "winner": winner_submission.user,
                    "is_claimed": False,
                }
            )

            claim_deadline = timezone.now() + timedelta(days=14)
            reward_delivery_deadline = claim_deadline + timedelta(days=7)

            wh = WinnerHistory.objects.create(
                game_history=game_history,
                game=self,
                user=winner_submission.user,
                number=number,
                prize_position=position,
                reward_type=self.reward_type,
                reward_description=self.description,
                reward_image=self.image,
                reward_link=self.link,
                claimed_at=None,
                is_claimed=False,
                claim_deadline=claim_deadline,
                reward_delivery_deadline=reward_delivery_deadline,
                reward_delivered=False,
            )

            RewardMessage.objects.create(
                winner_history=wh,
                sender=self.creator,
                message="Reward claiming is now open. Please share delivery details or proof here.",
                image=None
            )

            try:
                send_mail(
                    subject=f"🎉 Congratulations! You won '{self.title}'",
                    message=(
                        f"Hello {winner_submission.user.username},\n\n"
                        f"You are a winner in '{self.title}'!\n"
                        f"Reward: {self.reward_type} - {self.description}\n"
                        f"Claim before: {claim_deadline.strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"Delivery deadline: {reward_delivery_deadline.strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"Game Link: https://cientme.com/game/{self.id}\n\n"
                        "You can now use in-app messaging to coordinate with the creator.\n"
                        "Thank you for playing on Cientme!"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[winner_submission.user.email],
                    fail_silently=False,
                )
            except Exception as e:
                print(f"Failed to send winner email: {e}")

            position += 1

        # Notify creator
        try:
            send_mail(
                subject=f"Your game '{self.title}' has ended!",
                message=(
                    f"Hello {self.creator.username},\n\n"
                    f"Your game '{self.title}' on Cientme has officially ended.\n"
                    f"Participants: {self.participant_count}\n"
                    f"Winners: {self.number_of_winners}\n\n"
                    f"Winners have 14 days to claim their prizes.\n"
                    f"Delivery deadline: 7 days after claim.\n"
                    f"View the game: https://cientme.com/game/{self.id}\n\n"
                    "Thank you for using Cientme!"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.creator.email],
                fail_silently=False,
            )
        except Exception as e:
            print(f"Failed to send creator email: {e}")

        self.winners_selected = True
        self.save(update_fields=['winners_selected'])

    @classmethod
    def auto_close_expired_games(cls):
        now = timezone.now()
        for game in cls.objects.filter(is_active=True, end_time__lte=now, auto_close=True):
            game.close_game_and_select_winners()

    # ---------------------
    # Provable fairness verification
    # ---------------------
    def verify_fairness(self, winning_numbers: list):
        """
        Verify that a given set of winning numbers matches the published hash.
        """
        numbers_str = ",".join(map(str, winning_numbers)) + self.salt
        hash_check = hashlib.sha256(numbers_str.encode()).hexdigest()
        return hash_check == self.hash_value


# -----------------------
# WinningNumber Model
# -----------------------
class WinningNumber(BaseModel):
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

    class Meta:
        unique_together = ('game', 'number')

    def __str__(self):
        return f"Game: {self.game.title}, Number: {self.number}, Prize: {self.prize_position}"


# -----------------------
# GameSubmission Model
# -----------------------
class GameSubmission(BaseModel):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='submissions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    guessed_number = models.PositiveIntegerField()
    submitted_at = models.DateTimeField(default=timezone.now)
    is_winner = models.BooleanField(default=False)
    prize_position = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('game', 'user')

    def save(self, *args, **kwargs):
        if self.guessed_number < self.game.guess_min or self.guessed_number > self.game.guess_max:
            raise ValueError(f"Guessed number must be between {self.game.guess_min} and {self.game.guess_max}")
        super().save(*args, **kwargs)

    def mark_winner(self, position: int = None):
        self.is_winner = True
        if position is not None:
            self.prize_position = position
        self.save(update_fields=['is_winner', 'prize_position'])


# -----------------------
# GameHistory Model
# -----------------------
class GameHistory(BaseModel):
    game = models.OneToOneField(Game, on_delete=models.CASCADE, related_name="history")
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    reward_type = models.CharField(max_length=20)
    number_of_winners = models.PositiveIntegerField()
    guess_min = models.PositiveIntegerField()
    guess_max = models.PositiveIntegerField()
    reel = models.ForeignKey("reels.Reel", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField()
    completed_at = models.DateTimeField(auto_now_add=True)
    decrypted_winning_numbers = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        verbose_name = "Game History"
        verbose_name_plural = "Game Histories"

    def __str__(self):
        return f"{self.title} by {self.creator.username if self.creator else 'Unknown'}"


# -----------------------
# WinnerHistory Model
# -----------------------
class WinnerHistory(models.Model):
    game_history = models.ForeignKey("GameHistory", on_delete=models.CASCADE, related_name="winners")
    game = models.ForeignKey("Game", on_delete=models.SET_NULL, related_name="winner_histories", null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="winner_histories")
    number = models.PositiveIntegerField(help_text="The number guessed by the winner.")
    prize_position = models.PositiveIntegerField(help_text="Winner's rank/position.")
    reward_type = models.CharField(max_length=20, help_text="Type of reward (cash/digital/product).")
    reward_description = models.TextField(blank=True, null=True)
    reward_image = models.ImageField(upload_to="winner_rewards/", blank=True, null=True)
    reward_link = models.URLField(blank=True, null=True)
    claimed_at = models.DateTimeField(blank=True, null=True)
    is_claimed = models.BooleanField(default=False)
    claim_deadline = models.DateTimeField(blank=True, null=True)
    reward_delivery_deadline = models.DateTimeField(blank=True, null=True)
    reward_delivered = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Winner History"
        verbose_name_plural = "Winner Histories"
        permissions = [
            ("can_mark_claimed", "Can mark winner as claimed"),
            ("can_mark_reward_delivered", "Can mark reward as delivered"),
        ]

    def __str__(self):
        return f"Winner {self.user.username if self.user else 'Unknown'} (GameHistory {self.game_history.id})"

    # Claim reward method
    def claim_reward(self):
        if self.is_claimed:
            raise ValueError("Reward already claimed.")
        if self.claim_deadline and timezone.now() > self.claim_deadline:
            raise ValueError("Claim period has expired.")

        self.is_claimed = True
        self.claimed_at = timezone.now()
        self.reward_delivery_deadline = self.claimed_at + timedelta(days=7)
        self.save(update_fields=['is_claimed', 'claimed_at', 'reward_delivery_deadline'])

        # Notify creator
        try:
            send_mail(
                subject=f"Reward claimed by {self.user.username}",
                message=f"Winner {self.user.username} has claimed their reward for '{self.game_history.title}'. Deliver before {self.reward_delivery_deadline.strftime('%Y-%m-%d %H:%M:%S')}.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.game_history.creator.email],
                fail_silently=True,
            )
        except Exception as e:
            print(f"❌ Failed to notify creator: {e}")

        RewardMessage.objects.create(
            winner_history=self,
            sender=self.user,
            message="✅ I have claimed my reward.",
            image=None
        )

    def mark_delivered(self):
        if not self.is_claimed:
            raise ValueError("Cannot mark as delivered before winner claims.")
        if self.reward_delivery_deadline and timezone.now() > self.reward_delivery_deadline:
            raise ValueError("Delivery period has expired.")
        if self.reward_delivered:
            raise ValueError("Reward already marked as delivered.")

        self.reward_delivered = True
        self.save(update_fields=['reward_delivered'])

        RewardMessage.objects.create(
            winner_history=self,
            sender=self.game_history.creator,
            message="📦 Reward has been delivered by the creator.",
            image=None
        )

        try:
            send_mail(
                subject=f"Your reward for '{self.game_history.title}' has been delivered!",
                message=f"Hello {self.user.username},\n\nThe creator has marked your reward as delivered for '{self.game_history.title}'.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.user.email],
                fail_silently=True,
            )
        except Exception as e:
            print(f"❌ Failed to notify winner: {e}")


# -----------------------
# RewardMessage Model
# -----------------------
class RewardMessage(models.Model):
    winner_history = models.ForeignKey(WinnerHistory, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to="reward_messages/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.winner_history or not self.sender:
            raise ValueError("WinnerHistory and sender must be provided.")

        now = timezone.now()
        wh = self.winner_history
        allowed_until = wh.reward_delivery_deadline or wh.claim_deadline or now

        if now > allowed_until:
            raise ValueError("Messaging period has expired.")

        super().save(*args, **kwargs)
