from django.db.models.signals import post_save, post_delete
from django.db.models import Sum
from django.dispatch import receiver
from reels.models import Reel

@receiver([post_save, post_delete], sender=Reel)
def update_user_total_reach(sender, instance, **kwargs):
    user = instance.user
    profile = getattr(user, "profile", None)
    if not profile:
        return


    #  Only include active reels
    total = Reel.objects.filter(user=user, is_active=True).aggregate(total=Sum("reach"))["total"] or 0
    
    profile.total_reach = total
    profile.save(update_fields=["total_reach"])
