from __future__ import annotations
import os
from datetime import datetime
from .helpers import random_filename
import os



def dated_path(*parts: str) -> str:
    """Build a yyyy/mm/dd path joined with given parts."""
    today = datetime.utcnow()
    return os.path.join(*parts, str(today.year), f"{today.month:02d}", f"{today.day:02d}")




def user_avatar_upload_to(instance, filename: str) -> str:
    """Upload path for user avatars.
    Requires instance to have `id` or `pk` (may be None before first save).
    """
    user_id = getattr(instance, "pk", None) or "anon"
    return os.path.join(dated_path("avatars"), str(user_id), random_filename(filename, prefix="avatar"))




def post_media_upload_to(instance, filename: str) -> str:
    """Generic post media path: core/posts/yyyy/mm/dd/<post_id>/<random>"""
    post_id = getattr(instance, "pk", None) or "new"
    return os.path.join(dated_path("posts"), str(post_id), random_filename(filename, prefix="media"))




def reel_upload_to(instance, filename):
    """Upload path for reel videos."""
    obj_id = getattr(instance, "pk", None) or "new"
    return os.path.join(dated_path("reels"), str(obj_id), random_filename(filename, prefix="reel"))

def reel_thumbnail_upload_to(instance, filename):
    """Upload path for reel thumbnails."""
    obj_id = getattr(instance, "pk", None) or "new"
    return os.path.join(dated_path("reel_thumbnails"), str(obj_id), random_filename(filename, prefix="thumbnail"))


