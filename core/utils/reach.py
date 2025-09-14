from django.db import transaction

def update_profile_reach(profile, delta: int):
    """
    Incrementally update profile.total_reach by a given delta.
    """
    if delta == 0:
        return

    with transaction.atomic():
        profile.total_reach = (profile.total_reach or 0) + delta
        if profile.total_reach < 0:
            profile.total_reach = 0
        profile.save(update_fields=["total_reach"])
