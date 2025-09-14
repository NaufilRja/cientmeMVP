from django.contrib.auth import get_user_model
from django.utils import timezone
import random

from core.constants import (
    LIKE_WEIGHT,
    COMMENT_WEIGHT,
    REPLY_COMMENT_WEIGHT,
    SHARE_WEIGHT,
    SAVE_WEIGHT,
    VIEW_WEIGHT,
    WATCH_WEIGHT
)

User = get_user_model()


# -----------------------
# Share / Engagement Points
# -----------------------
def calculate_share_points(reel):
    """
    Calculate engagement points when a reel is shared.

    Points are based on:
        - Likes
        - Comments
        - Replies
        - Saves
        - Views
        - Current share (counts once)
    Reduces points for already viral reels and guarantees a minimum bonus.

    Args:
        reel: Reel instance

    Returns:
        int: Points awarded for the share
    """
    likes = reel.likes.count()
    comments = reel.comments.filter(parent__isnull=True).count()
    replies = reel.comments.exclude(parent__isnull=True).count()
    saves = reel.saves.count()
    views = reel.views

    # Initial points
    initial_points = (
        likes * LIKE_WEIGHT +
        comments * COMMENT_WEIGHT +
        replies * REPLY_COMMENT_WEIGHT +
        saves * SAVE_WEIGHT +
        SHARE_WEIGHT +  # each share counts once
        views * VIEW_WEIGHT
    )

    # ----------------------
    # Reduce points for viral reels
    # ----------------------
    if reel.reach and reel.reach > 5000:
        viral_factor = max(0.3, 1 - (reel.reach / 100000))
    else:
        viral_factor = 1.0  # full points

    # ----------------------
    # Minimum share bonus
    # ----------------------
    MIN_SHARE_BONUS = 50
    final_points = max(initial_points * viral_factor, MIN_SHARE_BONUS)

    return round(final_points)


# -----------------------
# Reel Reach Calculation
# -----------------------
def calculate_reel_reach(reel, followers_count, badge_min_reach=None):
    """
    Calculate dynamic reach for a reel based on followers, engagement, virality, and badges.

    Args:
        reel: Reel instance
        followers_count: Number of followers of the reel owner
        badge_min_reach: Optional minimum reach guaranteed by a badge

    Returns:
        float: Total calculated reach
    """
    total_users = User.objects.count()

    # ----------------------
    # Step 1: Base reach
    # ----------------------
    base_reach = followers_count + random.randint(200, 700)
    initial_reach = min(base_reach, total_users)

    # ----------------------
    # Step 2: Engagement-based reach
    # ----------------------
    likes = reel.likes.count()
    comments = reel.comments.filter(parent__isnull=True).count()
    replies = reel.comments.exclude(parent__isnull=True).count()
    shares = reel.shares
    saves = reel.saves.count()
    views = reel.views
    watch_ratio = getattr(reel, "watch_ratio", 1)

    engagement_reach = (
        likes * LIKE_WEIGHT +
        comments * COMMENT_WEIGHT +
        replies * REPLY_COMMENT_WEIGHT +
        shares * SHARE_WEIGHT +
        saves * SAVE_WEIGHT +
        views * VIEW_WEIGHT +
        watch_ratio * WATCH_WEIGHT
    )

    # Small random boost
    random_boost = engagement_reach * random.uniform(0.05, 0.2)

    total_reach_before_cap = initial_reach + engagement_reach + random_boost

    # ----------------------
    # Step 3: Cap based on engagement rate
    # ----------------------
    engagement_rate = engagement_reach / max(1, views)
    cap_mult = 1 + min(engagement_rate * 5, 10)
    max_reach = initial_reach * cap_mult

    final_total_reach = min(total_reach_before_cap, max_reach)

    # ----------------------
    # Step 4: Viral chance
    # ----------------------
    viral_chance = 0.03 + (engagement_reach / 100) * 0.01
    if random.random() < min(viral_chance, 0.25):
        final_total_reach *= random.uniform(1.5, 3.0)

    # ----------------------
    # Step 5: Badge guarantee
    # ----------------------
    if badge_min_reach is not None:
        final_total_reach = max(final_total_reach, badge_min_reach)

    # ----------------------
    # Step 6: Final cap by total users
    # ----------------------
    final_total_reach = min(final_total_reach, total_users)

    return round(final_total_reach)


# -----------------------
# Feed Score Calculation
# -----------------------
def calculate_feed_score(reel, user, following_ids=None):
    """
    Calculate a feed score for a reel for sorting the feed.

    Score is based on:
        - Whether the reel owner is followed
        - Likes, comments, shares
        - Recency decay (older reels score less)

    Args:
        reel: Reel instance
        user: Current user viewing the feed
        following_ids: List of user IDs that the current user follows

    Returns:
        float: Feed score for ranking
    """
    following_ids = following_ids or []
    score = 0

    # Bonus if the reel owner is followed
    if reel.user.id in following_ids:
        score += 50

    # Engagement contributions
    score += reel.likes.count() * 2
    score += reel.comments.count() * 3
    score += reel.shares * 5

    # Recency decay
    hours_old = (timezone.now() - reel.created_at).total_seconds() / 3600
    score -= hours_old

    return round(score, 2)
