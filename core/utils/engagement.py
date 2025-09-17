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
    if engagement_reach > 0:
        random_boost = engagement_reach * random.uniform(0.05, 0.2)
    else:
        random_boost = 0

    total_reach_before_cap = initial_reach + engagement_reach + random_boost

    # ----------------------
    # Step 3: Cap based on engagement rate
    # ----------------------
    engagement_rate = engagement_reach / max(1, reel.views + 1)
    cap_mult = 1 + min(engagement_rate * 5, 10)
    max_reach = initial_reach * cap_mult

    final_total_reach = min(total_reach_before_cap, max_reach)

    # ----------------------
    # Step 4: Viral chance
    # ----------------------
    if engagement_reach > 10:
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
# Reel Feed Calculation
# -----------------------
def calculate_feed_score(reel, user, following_ids=None, season_keywords=None):
    """
    Calculate feed score for a reel, balancing:
        - Followers priority
        - Engagement
        - Fresh/new creators
        - Seasonal/time-of-day relevance
        - Viral boost (chance for new or under-the-radar reels)
    
    Args:
        reel: Reel instance
        user: Current user viewing the feed
        following_ids: List of user IDs current user follows
        season_keywords: list of keywords relevant to current season/event

    Returns:
        float: final feed score
    """
    following_ids = following_ids or []
    score = 0

    # ----------------------
    # 1. Personalization: Followers & new creators
    # ----------------------
    if reel.user.id in following_ids:
        score += 200  # strong weight for followed creators
    else:
        # Give smaller boost for new/less-followed creators
        if reel.user.profile.followers.count() < 50:  # threshold for new creators
            score += 50  # chance for new users to appear

    # ----------------------
    # 2. Engagement contributions
    # ----------------------
    score += reel.likes.count() * 2
    score += reel.comments.filter(parent__isnull=True).count() * 3   # top-level comments
    score += reel.comments.exclude(parent__isnull=True).count() * 2   # replies
    score += reel.shares * 8
    score += reel.saves.count() * 4
    score += reel.views * 0.5

    # Include share points
    score += calculate_share_points(reel)

    # ----------------------
    # 3. Recency decay
    # ----------------------
    hours_old = (timezone.now() - reel.created_at).total_seconds() / 3600
    score -= hours_old

    # ----------------------
    # 4. Seasonal relevance
    # ----------------------
    if season_keywords:
        for keyword in season_keywords:
            if keyword.lower() in reel.caption.lower():
                score += 50  # additive boost instead of multiplicative
                break

    # ----------------------
    # 5. Time-of-day relevance (morning/evening)
    # ----------------------
    hour = timezone.now().hour
    if 7 <= hour < 10:
        score += 20  # morning boost
    elif 19 <= hour < 23:
        score += 40  # evening peak
    elif 0 <= hour < 5:
        score -= 20  # late night reduction

    # ----------------------
    # 6. Viral/fresh chance for new users
    # ----------------------
    # 10% chance for a new or low-engagement reel to get boosted
    if reel.user.profile.followers.count() < 50 or reel.views < 100:
        if random.random() < 0.1:
            score *= random.uniform(1.5, 2.0)  # temporary boost

    # ----------------------
    # 7. Cap final score to prevent one reel dominating
    # ----------------------
    MAX_SCORE = 1000
    score = min(score, MAX_SCORE)

    return round(score, 2)