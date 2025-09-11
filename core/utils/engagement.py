from django.conf import settings
from django.contrib.auth import get_user_model
import random
from core.constants import (
    LIKE_WEIGHT, COMMENT_WEIGHT, REPLY_COMMENT_WEIGHT,
    SHARE_WEIGHT, SAVE_WEIGHT, VIEW_WEIGHT, WATCH_WEIGHT
)
User = get_user_model()

def calculate_reel_reach(reel, followers_count, badge_min_reach=None):
    """
    Calculate dynamic reach for a reel.
    
    - Base reach = followers + random(200, 700), capped by total users.
    - Engagement (likes, comments, replies, shares, saves, views, watch ratio) 
      increases reach with weighted contribution.
    - Viral chance can multiply reach.
    - Badge guarantees minimum reach.
    - Final cap = total number of users on the platform.
    """
    
    # ----------------------
    # Step 0: Total users cap
    # ----------------------
    total_users = User.objects.count()

  
    # ----------------------
    # Step 1: Initial base reach
    # ----------------------
    base_reach = followers_count + random.randint(200, 700)
    initial_reach = min(base_reach, total_users)  # cap by total users
    
    # ----------------------
    # Step 2: Engagement-driven reach
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

    # Random small boost
    random_boost = engagement_reach * random.uniform(0.05, 0.2)

    total_reach_before_cap = initial_reach + engagement_reach + random_boost

    # ----------------------
    # Step 3: Cap & Viral chance
    # ----------------------
    engagement_rate = engagement_reach / max(1, views)
    cap_mult = 1 + min(engagement_rate * 5, 10)
    max_reach = initial_reach * cap_mult

    final_total_reach = min(total_reach_before_cap, max_reach)

    # Viral chance
    viral_chance = 0.03 + (engagement_reach / 100) * 0.01
    if random.random() < min(viral_chance, 0.25):
        final_total_reach *= random.uniform(1.5, 3.0)

    # ----------------------
    # Step 4: Badge guarantee
    # ----------------------
    if badge_min_reach is not None:
        final_total_reach = max(final_total_reach, badge_min_reach)
        
    # ----------------------
    # Step 5: Final cap by total users
    # ----------------------
    final_total_reach = min(final_total_reach, total_users) 
    
    
    
    
    # ----------------------
    # Debug Logging (only in DEBUG mode)
    # ----------------------
    if settings.DEBUG:
        print({
            "base_reach": base_reach,
            "initial_reach": initial_reach,
            "engagement_reach": engagement_reach,
            "random_boost": random_boost,
            "before_cap": total_reach_before_cap,
            "max_reach": max_reach,
            "final_reach": final_total_reach,
            # "viral_triggered": viral_triggered
        })   

    return round(final_total_reach)
