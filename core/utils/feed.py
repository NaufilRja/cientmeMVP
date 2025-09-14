from reels.models import Reel
from .engagement import calculate_feed_score
import random

# -----------------------
# Hybrid User Feed
# -----------------------
def get_user_feed(user, limit=20):
    """
    Hybrid feed + scoring:
    - 70% personalized (tags/engagement)
    - 20% fresh/random
    - 10% social/follows
    - Sort candidate reels by calculate_feed_score
    """

    #  Fix hidden reels reference
    hidden_ids = user.profile.hidden_reels.values_list('id', flat=True)

    # (1️⃣) Personalized (70%)
    engaged_tags = user.profile.engaged_tags.values_list("id", flat=True)

    if engaged_tags.exists():
        personalized_qs = Reel.objects.filter(tags__in=engaged_tags).exclude(id__in=hidden_ids).distinct()
    else:
        # fallback to recent reels if no engaged tags
        personalized_qs = Reel.objects.exclude(id__in=hidden_ids).order_by("-created_at")

    personalized_count = int(limit * 0.7)
    personalized_reels = list(personalized_qs[:personalized_count])

    # (2️) Social boost (10%)
    social_count = max(1, int(limit * 0.1))
    follow_ids = user.profile.user.following_profiles.values_list("id", flat=True)

    social_qs = Reel.objects.filter(
        user_id__in=follow_ids
    ).exclude(id__in=hidden_ids).exclude(
        id__in=[r.id for r in personalized_reels]
    )
    social_reels = list(social_qs.order_by("-created_at")[:social_count])

    # (3️) Fresh / random (20%)
    random_count = limit - len(personalized_reels) - len(social_reels)
    fresh_qs = Reel.objects.exclude(
        id__in=[r.id for r in personalized_reels + social_reels]
    ).exclude(id__in=hidden_ids)
    fresh_reels = list(fresh_qs.order_by("-created_at")[:200])  # cap for performance
    fresh_reels = random.sample(fresh_reels, min(random_count, len(fresh_reels)))

    # (4️) Combine all candidate reels
    candidate_reels = personalized_reels + social_reels + fresh_reels

    # (5️) Rank with calculate_feed_score
    scored_reels = [
        (calculate_feed_score(r, user, follow_ids), r) for r in candidate_reels
    ]
    scored_reels.sort(key=lambda x: x[0], reverse=True)

    # (6️) Return ordered feed limited to `limit`
    final_feed = [r for _, r in scored_reels][:limit]
    return final_feed
