import random
from reels.models import Reel

def get_user_feed(user, limit=20):
    """
    Return a mixed feed for the user:
    - 70% personalized based on engagement
    - 30% random/new reels
    """

    # Step 1: Reels the user engaged with or similar tags
    engaged_reels = Reel.objects.filter(
        tags__in=user.engaged_tags.all()  # assuming you track tags user engaged
    ).exclude(id__in=user.hidden_reels.values_list('id', flat=True))  # hide excluded
    personalized_count = int(limit * 0.7)
    personalized_reels = random.sample(list(engaged_reels), min(personalized_count, len(engaged_reels)))

    # Step 2: Random / new reels
    all_reels = Reel.objects.exclude(id__in=[r.id for r in personalized_reels]).exclude(id__in=user.hidden_reels.values_list('id', flat=True))
    random_count = limit - len(personalized_reels)
    random_reels = random.sample(list(all_reels), min(random_count, len(all_reels)))

    # Combine and shuffle for variety
    feed = personalized_reels + random_reels
    random.shuffle(feed)
    return feed[:limit]
