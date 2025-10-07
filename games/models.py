from django.db import models
from django.conf import settings
from core.models.base import BaseModel
from django.utils import timezone
from datetime import timedelta
from cryptography.fernet import Fernet
from django.core.mail import send_mail
from rest_framework.exceptions import ValidationError
from rest_framework.exceptions import PermissionDenied
from core.utils.image_utils import compress_image
from core.utils.upload_paths import game_reward_upload_to , reward_message_upload_to
from core.utils.validators import validate_image_file_size
import random
import string
import hashlib
import uuid
import logging

logger = logging.getLogger(__name__)

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

    # -----------------------
    # Core details
    # -----------------------
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_games",
        help_text="User who created this game."
    )
    title = models.CharField(max_length=255, help_text="Title of the game.")
    description = models.TextField(blank=True, null=True, help_text="Optional description of the game.")
    
    image = models.ImageField(
        upload_to=game_reward_upload_to,
        blank=True,    
        null=True,     
        validators=[validate_image_file_size],
        help_text="Game Banner/Cover image (used for promotion, not for prize)"
    )
    
    link = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Optional: Website or sponsor link (visible to all players)."
    )
    
    
    
    # Top prize images & links (optional)
    first_prize_image = models.ImageField(
        upload_to=game_reward_upload_to,
        blank=False, null=False,
        validators=[validate_image_file_size],
        help_text="Image for first prize"
    )
    first_prize_link = models.URLField(blank=True, null=True, help_text="Optional link for first prize")

    second_prize_image = models.ImageField(
        upload_to=game_reward_upload_to,
        blank=True, null=True,
        validators=[validate_image_file_size],
        help_text="Image for second prize"
    )
    second_prize_link = models.URLField(blank=True, null=True, help_text="Optional link for second prize")

    third_prize_image = models.ImageField(
        upload_to=game_reward_upload_to,
        blank=True, null=True,
        validators=[validate_image_file_size],
        help_text="Image for third prize"
    )
    third_prize_link = models.URLField(blank=True, null=True, help_text="Optional link for third prize")
    # -----------------------
    # Reward & Winners
    # -----------------------
    reward_type = models.CharField(
        max_length=20,
        choices=REWARD_TYPE_CHOICES,
        blank=True,    # optional
        null=True,     # optional
        help_text="Optional: Type of first prize or all prizes if same kind."
)
    number_of_winners = models.PositiveIntegerField(default=1, help_text="Number of winners allowed.")

    # -----------------------
    # Game rules
    # -----------------------
    guess_min = models.PositiveIntegerField(default=1, help_text="Minimum guess number.")
    guess_max = models.PositiveIntegerField(default=100, help_text="Maximum guess number.")

    # -----------------------
    # Related content
    # -----------------------
    reel = models.OneToOneField(
        "reels.Reel",
        on_delete=models.SET_NULL,
        related_name="games",
        blank=True,
        null=True,
        help_text="Optional reel linked to this game."
    )

    # -----------------------
    # Timing
    # -----------------------
    duration = models.DurationField(default=timezone.timedelta(hours=24), help_text="Game duration (default: 24 hours).")
    end_time = models.DateTimeField(blank=True, null=True, help_text="End time (auto-calculated on save).")

    # -----------------------
    # Security & provably fair
    # -----------------------
    salt = models.CharField(max_length=255, blank=True, null=True, editable=False, help_text="Random salt for hash generation.")
    hash_value = models.CharField(max_length=255, blank=True, null=True, editable=False, help_text="Hash of winning numbers (for fairness verification).")
    winning_numbers_encrypted = models.TextField(blank=True, null=True, editable=False, help_text="Encrypted winning numbers.")

    # -----------------------
    # Status & automation
    # -----------------------
    is_active = models.BooleanField(default=True, help_text="Whether the game is active or soft-deleted.")
    auto_close = models.BooleanField(default=True, help_text="Whether the game should auto-close when end_time is reached.")
    auto_select_winner = models.BooleanField(default=True, help_text="Automatically select winners when game closes.")
    winners_selected = models.BooleanField(default=False, help_text="Whether winners have already been selected.")


    # -----------------------
    # Dynamic winner info (for 4th, 5th, 6th… winners)
    # -----------------------
    winner_titles = models.JSONField(default=list, blank=True, help_text="Custom titles for winners 4,5,6...")
    winner_descriptions = models.JSONField(default=list, blank=True, help_text="Custom descriptions for winners 4,5,6...")
    winner_links = models.JSONField(default=list, blank=True, help_text="Custom reward links for winners 4,5,6...")


    # ---------------------
    # Save method
    # ---------------------
    def save(self, *args, **kwargs):
        if self.duration and not self.end_time:
            self.end_time = timezone.now() + self.duration
            
        if not self.salt:
            self.salt = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
            
        # Compress reward image if present
        if self.image:
            self.image = compress_image(self.image, max_size=(600, 600), quality=75)
    
        super().save(*args, **kwargs)


    # -----------------------
    # Validation
    # -----------------------
    def clean(self):
        # Prevent deletion if participants exist - FIXED
        if self.pk and self.submissions.exists() and not self.is_active:
            raise ValidationError("Cannot delete a game with participants.")

    @property
    def participant_count(self):
        return self.submissions.count()

    def __str__(self):
        return f"{self.title} (by {self.creator.username})"

    # -----------------------
    # Auto-close and winner selection
    # -----------------------
    def close_game_and_select_winners(self):
        # Validation: reward count must match number_of_winners
        total_rewards = self.rewards.count() if hasattr(self, "rewards") else 0
        if total_rewards != self.number_of_winners:
            raise ValidationError(
                f"Number of rewards ({total_rewards}) does not match number of winners ({self.number_of_winners}). "
                "Please adjust rewards before closing the game."
            )
        
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
                logger.error(f"Failed to decrypt winning numbers for game '{self.title}': {e}")
                return

        submissions = self.submissions.filter(submitted_at__lte=self.end_time).order_by("submitted_at")

        # Ensure enough numbers
        if len(decrypted_numbers) < self.number_of_winners:
            remaining_needed = self.number_of_winners - len(decrypted_numbers)
            random_subs = submissions.exclude(guessed_number__in=decrypted_numbers)[:remaining_needed]
            decrypted_numbers.extend([s.guessed_number for s in random_subs])

        if not decrypted_numbers:
            decrypted_numbers = list(range(self.guess_min, self.guess_min + self.number_of_winners))

        decrypted_numbers_str = ",".join(map(str, decrypted_numbers)) or ""

        # -----------------------
        # Create GameHistory
        # -----------------------
        game_history = GameHistory.objects.create(
            game=self,
            creator=self.creator,
            title=self.title,
            description=self.description,
            reward_type=self.reward_type if self.reward_type else None,
            number_of_winners=self.number_of_winners,
            guess_min=self.guess_min,
            guess_max=self.guess_max,
            reel=self.reel,
            created_at=self.created_at,
            decrypted_winning_numbers=decrypted_numbers_str 
        )
        game_history.decrypted_winning_numbers = decrypted_numbers_str
        game_history.save(update_fields=['decrypted_winning_numbers'])

        # -----------------------
        # Assign winners and rewards
        # -----------------------
        position = 1
        for number in decrypted_numbers:
            if position > self.number_of_winners:
                break

            matched_submissions = submissions.filter(guessed_number=number)
            if not matched_submissions.exists():
                logger.info(f"No submission matched winning number {number} for game '{self.title}'.")
                continue

            winner_submission = matched_submissions.first()

            # -----------------------
            # Determine reward title/description/link dynamically
            # -----------------------
            if position > 3:
                idx = position - 4  # 0-based index for 4th+ winners
                reward_title = (self.winner_titles[idx] if idx < len(self.winner_titles) else f"{self.title} - Prize {position}")
                reward_description = (self.winner_descriptions[idx] if idx < len(self.winner_descriptions) else self.description)
                reward_link = (self.winner_links[idx] if idx < len(self.winner_links) else None)
            else:
                reward_title = f"{self.title} - Prize {position}"
                reward_description = self.description
                if position == 1:
                    reward_link = self.first_prize_link
                elif position == 2:
                    reward_link = self.second_prize_link
                elif position == 3:
                    reward_link = self.third_prize_link

            # -----------------------
            # Create/Update GameReward
            # -----------------------
            gr, _ = GameReward.objects.update_or_create(
                game=self,
                position=position,
                defaults={
                    "reward_type": self.reward_type if self.reward_type else "product",
                    "reward_title": reward_title,
                    "reward_description": reward_description,
                    "reward_link": reward_link,
                    "is_claimed": False,
                    "claimed_at": None,
                }
            )
            logger.info(f"GameReward created/updated for Game '{self.title}' | Position: {position}")

            # -----------------------
            # Create WinnerHistory
            # -----------------------
            wh = WinnerHistory.objects.create(
                game_history=game_history,
                game=self,
                user=winner_submission.user,
                number=number,
                prize_position=position,
                reward_type=self.reward_type if self.reward_type else None,
                reward_description=reward_description,
                reward_link=reward_link,
                claimed_at=None,
                is_claimed=False,
                claim_deadline=timezone.now() + timedelta(days=14),
                reward_delivery_deadline=timezone.now() + timedelta(days=21),
                reward_delivered=False,
            )
            logger.info(f"WinnerHistory created | User: {winner_submission.user.username} | Game: {self.title} | Position: {position}")

            position += 1

        self.winners_selected = True
        self.save(update_fields=['winners_selected'])
            
    @property
    def is_finished(self):
        """
        Returns True if the game's end_time has passed, False otherwise.
        """
        if not self.end_time:
            return False
        return timezone.now() >= self.end_time
            
    
    @property
    def is_active_dynamic(self):
        # If the game is manually active but end_time passed, consider it inactive
        if self.end_time and timezone.now() >= self.end_time:
            return False
        return self.is_active        
        
    # ---------------------
    # Auto-close games
    # ---------------------
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
# Winning Number Model
# -----------------------
class WinningNumber(BaseModel):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="winning_numbers")
    number = models.PositiveIntegerField(help_text="The winning number for this game.")
    reward_description = models.TextField(blank=True, null=True)
    reward_image = models.ImageField(upload_to='game_rewards/', blank=True, null=True)
    reward_link = models.URLField(blank=True, null=True)
    reward_type = models.CharField(max_length=20, blank=True, null=True,  choices=Game.REWARD_TYPE_CHOICES)
    prize_position = models.PositiveIntegerField(default=1, help_text="1st prize, 2nd prize, etc.")
    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="won_numbers"
    )
    is_claimed = models.BooleanField(default=False)


    class Meta:
        unique_together = ('game', 'number')

    def __str__(self):
        return f"Game: {self.game.title}, Number: {self.number}, Prize: {self.prize_position}"


# -----------------------
# Game Submission Model
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
        # 1️ Check guessed number is within range
        if self.guessed_number < self.game.guess_min or self.guessed_number > self.game.guess_max:
            raise ValueError(f"Guessed number must be between {self.game.guess_min} and {self.game.guess_max}")

        # 2️ Followers-only participation check
        if self.user not in self.game.creator.profile.followers.all():
            raise ValueError("You must follow the creator to participate in this game.")

        # 3️ Save submission
        super().save(*args, **kwargs)


    def mark_winner(self, position: int = None):
        self.is_winner = True
        if position is not None:
            self.prize_position = position
        self.save(update_fields=['is_winner', 'prize_position'])





# -----------------------
# Game History Model
# -----------------------
class GameHistory(BaseModel):
    id = models.BigAutoField(primary_key=True)
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    game = models.OneToOneField(Game, on_delete=models.CASCADE, related_name="history")
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    reward_type = models.CharField(max_length=20, blank=True, null=True)
    number_of_winners = models.PositiveIntegerField()
    guess_min = models.PositiveIntegerField()
    guess_max = models.PositiveIntegerField()
    reel = models.ForeignKey("reels.Reel", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField()
    completed_at = models.DateTimeField(auto_now_add=True)
    decrypted_winning_numbers = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "Game History"
        verbose_name_plural = "Game Histories"

    def __str__(self):
        return f"{self.title} by {self.creator.username if self.creator else 'Unknown'}"


# -----------------------
# Winner History Model
# -----------------------
class WinnerHistory(models.Model):
    game_history = models.ForeignKey("GameHistory", on_delete=models.CASCADE, related_name="winners")
    game = models.ForeignKey("Game", on_delete=models.SET_NULL, related_name="winner_histories", null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="winner_histories")
    number = models.PositiveIntegerField(help_text="The number guessed by the winner.")
    prize_position = models.PositiveIntegerField(help_text="Winner's rank/position.")
    reward_type = models.CharField(max_length=20, blank=True, null=True,  help_text="Type of reward (cash/digital/product).")
    reward_description = models.TextField(blank=True, null=True)
    reward_image = models.ImageField(upload_to="winner_rewards/", blank=True, null=True)
    reward_link = models.URLField(blank=True, null=True)
    claimed_at = models.DateTimeField(blank=True, null=True)
    is_claimed = models.BooleanField(default=False)
    claim_deadline = models.DateTimeField(blank=True, null=True)
    reward_delivery_deadline = models.DateTimeField(blank=True, null=True)
    reward_delivered = models.BooleanField(default=False)
    reward_received = models.BooleanField(default=False, help_text="Winner confirms they received the reward.")
    received_at = models.DateTimeField(blank=True, null=True)
    forfeited = models.BooleanField(default=False, help_text="Marks if the reward was not claimed in time.")


    class Meta:
        verbose_name = "Winner History"
        verbose_name_plural = "Winner Histories"
        permissions = [
            ("can_mark_claimed", "Can mark winner as claimed"),
            ("can_mark_reward_delivered", "Can mark reward as delivered"),
        ]

    def __str__(self):
        return f"Winner {self.user.username if self.user else 'Unknown'} (GameHistory {self.game_history.id})"

    @property
    def can_message(self):
        now = timezone.now()
        if self.reward_delivered:
            return False
        if self.claim_deadline and not self.is_claimed and now > self.claim_deadline:
            return False
        return True

    # Claim reward method
    def claim_reward(self):
        if self.is_claimed:
            raise ValueError("Reward already claimed.")

        now = timezone.now()

        # 1️ Followers-only claim check
        if self.user not in self.game.creator.profile.followers.all():
            chat, _ = RewardChat.objects.get_or_create(
                creator=self.game.creator,
                winner=self.user
            )
            
            chat.is_active = True  # reactivate chat when new reward claim starts
            chat.save() 
            
            RewardMessage.objects.create(
                reward_chat=chat,
                winner_history=self,
                sender=self.game.creator,
                message="You cannot claim this reward because you are not a follower. Reward forfeited.",
                is_system_message=True
            )
            raise ValueError("You must be following the creator to claim the reward. Reward forfeited.")

        # 2️ Check if claim deadline has passed
        if self.claim_deadline and now > self.claim_deadline:
            self.forfeited = True
            self.save(update_fields=['forfeited'])

            chat, _ = RewardChat.objects.get_or_create(
                creator=self.game.creator,
                winner=self.user
            )
            RewardMessage.objects.create(
                reward_chat=chat,
                winner_history=self,
                sender=self.game.creator,
                message=" Claim period expired. Reward forfeited.",
                is_system_message=True
            )
            raise ValueError("Claim period has expired. Reward forfeited.")  #  required

        # 3️ Proceed with claim
        self.is_claimed = True
        self.claimed_at = now
        self.reward_delivery_deadline = self.claimed_at + timedelta(days=7)
        self.save(update_fields=['is_claimed', 'claimed_at', 'reward_delivery_deadline'])

        # 4️ Notify creator via email
        try:
            send_mail(
                subject=f"Reward claimed by {self.user.username}",
                message=f"Winner {self.user.username} has claimed their reward for '{self.game.title}'. Deliver before {self.reward_delivery_deadline.strftime('%Y-%m-%d %H:%M:%S')}.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.game.creator.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.warning(f"Failed to notify creator about reward claim: {e}")

        # 5️ Create in-app reward message confirming claim
        chat, _ = RewardChat.objects.get_or_create(
            creator=self.game.creator,
            winner=self.user
        )
        RewardMessage.objects.create(
            reward_chat=chat,
            winner_history=self,
            sender=self.user,
            message="I have claimed my reward.",
            is_system_message=True
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
        
        # Block the chat after delivery
        chat, _ = RewardChat.objects.get_or_create(
            creator=self.game.creator,
            winner=self.user
        )
        chat.is_active = False  # block chat
        chat.save()


        # Create in-app system message
        try:
            RewardMessage.objects.create(
                reward_chat=chat,
                winner_history=self,
                sender=self.game.creator,
                message="Reward has been delivered by the creator.",
                is_system_message=True
            )
        except Exception as e:
            logger.warning(f"Could not send reward message: {e}")

        # Send email notification to winner
        try:
            send_mail(
                subject=f"Your reward for '{self.game.title}' has been delivered!",
                message=f"Hello {self.user.username},\n\nThe creator has marked your reward as delivered for '{self.game.title}'.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.user.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Failed to send reward delivery email to {self.user.email}: {e}")

                
    def delete(self, *args, **kwargs):
        raise PermissionDenied("Winner history cannot be deleted.")    


# -----------------------
# Game Reward Model
# -----------------------
class GameReward(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="rewards")
    position = models.PositiveIntegerField(help_text="Winner position (1, 2, 3, etc.)")
    reward_type = models.CharField(max_length=20, choices=Game.REWARD_TYPE_CHOICES)
    reward_title = models.CharField(max_length=100, help_text="Title or name of the reward")
    reward_description = models.TextField(blank=True, null=True, help_text="Optional description")
    reward_link = models.URLField(blank=True, null=True)
    is_claimed = models.BooleanField(default=False)
    claimed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ("game", "position")

    def __str__(self):
        return f"{self.game.title} - Position {self.position} Reward: {self.reward_title}"




# -----------------------
# Game Complaint Model
# -----------------------
class RewardChat(models.Model):
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_reward_chats"
    )
    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="won_reward_chats"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('creator', 'winner')

    def __str__(self):
        return f"Chat between {self.creator} and {self.winner}"


# -----------------------
# Reward Message Model
# -----------------------
class RewardMessage(models.Model):
    """
    Represents a message between the game creator and the winner.
    Supports continuous chat across multiple games (same creator-winner pair).
    """

    # link to shared chat thread (creator-winner pair)
    reward_chat = models.ForeignKey(
        RewardChat,
        on_delete=models.CASCADE,
        null=True,       # allow existing messages to stay valid
        blank=True,
        related_name="messages",
        help_text="Chat thread between creator and winner"
    )


    #  Optional: still keep reference to the specific game history
    winner_history = models.ForeignKey(
        "WinnerHistory",
        on_delete=models.CASCADE,
        related_name="messages"
    )

    # Optional: direct link to Game for cross-game referencing
    game = models.ForeignKey(
        "Game",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reward_messages"
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    message = models.TextField(blank=True, null=True)
    image = models.ImageField(
        upload_to=reward_message_upload_to,
        blank=True,
        null=True,
        validators=[validate_image_file_size]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_system_message = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.winner_history or not self.sender:
            raise ValueError("WinnerHistory and sender must be provided.")

        now = timezone.now()
        wh = self.winner_history

        # Determine if messaging is allowed
        messaging_allowed = True
        if wh.reward_delivered:
            messaging_allowed = False
        elif wh.claim_deadline and not wh.is_claimed and now > wh.claim_deadline:
            messaging_allowed = False

        if not messaging_allowed:
            raise ValueError("Messaging is no longer allowed for this winner.")

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Message from {self.sender} in chat {self.reward_chat_id}"






# -----------------------
# Game Complaint Model
# -----------------------
class GameComplaint(models.Model):
    """
    Represents a complaint submitted by a winner regarding issues with claiming 
    or receiving a reward in a game. 
    
    Rules enforced:
    1. Only winners can submit a complaint.
    2. Optionally, the winner must still follow the game creator.
    3. Tracks complaint status: pending, resolved, or rejected.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("resolved", "Resolved"),
        ("rejected", "Rejected"),
    ]

    # The WinnerHistory object that this complaint is associated with
    winner_history = models.ForeignKey(
        "WinnerHistory",
        on_delete=models.CASCADE,
        related_name="complaints",
        help_text="The winner who is filing the complaint."
    )

    # The user submitting the complaint (must be the winner)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="game_complaints",
        help_text="The user submitting the complaint (must be the winner)."
    )

    # Detailed message of the complaint
    message = models.TextField(help_text="Details of the complaint.")

    # Timestamps and status
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        help_text="Current status of the complaint."
    )
    resolved_at = models.DateTimeField(
        blank=True, 
        null=True,
        help_text="Timestamp when the complaint was resolved or rejected."
    )

    # Optional response from the creator or admin
    response = models.TextField(
        blank=True, 
        null=True,
        help_text="Response from the creator or admin regarding this complaint."
    )

    class Meta:
        verbose_name = "Game Complaint"
        verbose_name_plural = "Game Complaints"

    def save(self, *args, **kwargs):
        """
        Overrides save() to enforce rules:
        1. Only the winner can submit the complaint.
        2. Optionally, the winner must still follow the creator.
        Compress message image before saving
        """
        # Ensure only the winner can submit
        if self.user != self.winner_history.user:
            raise ValueError("Only the winner can submit a complaint for this reward.")

        # Optional Ensure winner is still a follower
        if self.user not in self.winner_history.game.creator.profile.followers.all():
            raise ValueError("You must be following the creator to submit a complaint.")
        

        # Proceed with saving the complaint
        super().save(*args, **kwargs)

    def mark_resolved(self, response_message: str = ""):
        """
        Marks the complaint as resolved and optionally adds a response message.
        """
        self.status = "resolved"
        self.resolved_at = timezone.now()
        self.response = response_message
        self.save(update_fields=["status", "resolved_at", "response"])

    def mark_rejected(self, response_message: str = ""):
        """
        Marks the complaint as rejected and optionally adds a response message.
        """
        self.status = "rejected"
        self.resolved_at = timezone.now()
        self.response = response_message
        self.save(update_fields=["status", "resolved_at", "response"])

    def __str__(self):
        """
        String representation for admin or debugging purposes.
        """
        return f"Complaint by {self.user.username} for game '{self.winner_history.game_history.title}' (Status: {self.status})"
