"""Core business logic: pantry-vs-recipe matching and shopping-list generation."""
import re
from decimal import Decimal
from math import ceil
from urllib.parse import parse_qs, urlparse

from .models import PantryItem, Recipe


def pantry_map(user):
    """{ingredient_id: quantity} for the user's pantry."""
    if not user.is_authenticated:
        return {}
    return {p.ingredient_id: p.quantity for p in PantryItem.objects.filter(user=user)}


def build_gap(recipe, pantry, servings=None):
    """
    Compare a recipe (scaled to `servings`) with the pantry.
    Returns a dict with per-ingredient lines, match %, and the cost of what is missing.
    """
    servings = servings or recipe.base_servings
    scale = Decimal(servings) / Decimal(recipe.base_servings)
    lines = []
    covered = 0
    total_cost = 0
    missing_cost = 0
    for item in recipe.items.all():
        ing = item.ingredient
        needed = (item.quantity * scale).quantize(Decimal("0.01"))
        have = pantry.get(ing.id, Decimal("0"))
        missing = max(needed - have, Decimal("0"))
        # Whole pieces can't be bought fractionally
        if ing.unit == "pc":
            missing = Decimal(ceil(missing))
        line_cost = int(ceil(missing * ing.price_per_unit_rwf))
        full_cost = int(ceil(needed * ing.price_per_unit_rwf))
        in_pantry = missing == 0
        if in_pantry:
            covered += 1
        total_cost += full_cost
        missing_cost += line_cost
        lines.append(
            {
                "ingredient_id": ing.id,
                "name": ing.name,
                "kinyarwanda_name": ing.kinyarwanda_name,
                "unit": ing.unit,
                "needed": float(needed),
                "have": float(min(have, needed)),
                "missing": float(missing),
                "cost_rwf": line_cost,
                "in_pantry": in_pantry,
            }
        )
    count = len(lines) or 1
    return {
        "servings": servings,
        "lines": lines,
        "match_percent": round(100 * covered / count),
        "missing_count": count - covered,
        "full_cost_rwf": total_cost,
        "missing_cost_rwf": missing_cost,
        "savings_rwf": total_cost - missing_cost,
    }


def video_embed_url(url):
    """Return a safe embeddable URL for YouTube / Vimeo links, or None for anything else."""
    if not url:
        return None
    try:
        u = urlparse(url.strip())
    except ValueError:
        return None
    if u.scheme not in ("http", "https"):
        return None
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    if host == "youtu.be":
        vid = u.path.lstrip("/")[:11]
    elif host in ("youtube.com", "music.youtube.com"):
        if u.path == "/watch":
            vid = parse_qs(u.query).get("v", [""])[0]
        else:
            m = re.match(r"^/(?:embed|shorts|live)/([\w-]{11})", u.path)
            vid = m.group(1) if m else ""
    elif host == "vimeo.com":
        m = re.match(r"^/(\d+)", u.path)
        return f"https://player.vimeo.com/video/{m.group(1)}" if m else None
    else:
        return None
    return f"https://www.youtube-nocookie.com/embed/{vid}" if re.fullmatch(r"[\w-]{11}", vid) else None


def media_info(recipe):
    """(images, video) for a recipe. Uses prefetched images when available."""
    images = [{"id": i.id, "url": i.image.url, "caption": i.caption} for i in recipe.images.all()]
    video = None
    if recipe.video_file:
        video = {"type": "file", "url": recipe.video_file.url}
    elif recipe.video_url:
        embed = video_embed_url(recipe.video_url)
        if embed:
            video = {"type": "embed", "url": embed}
    return images, video


def recipe_to_dict(recipe, pantry, user=None, servings=None):
    gap = build_gap(recipe, pantry, servings)
    images, video = media_info(recipe)
    return {
        "images": images,
        "cover": images[0]["url"] if images else None,
        "video": video,
        "id": recipe.id,
        "title": recipe.title,
        "description": recipe.description,
        "emoji": recipe.emoji,
        "meal_type": recipe.meal_type,
        "prep_minutes": recipe.prep_minutes,
        "base_servings": recipe.base_servings,
        "calories_per_serving": recipe.calories_per_serving,
        "doctor_note": recipe.doctor_note,
        "focuses": [{"slug": f.slug, "name": f.name, "icon": f.icon} for f in recipe.health_focuses.all()],
        "instructions": [s for s in recipe.instructions.splitlines() if s.strip()],
        **gap,
    }


def visible_recipes(user, focus_slugs=None, meal_type=None, use_profile=False):
    qs = (
        Recipe.objects.filter(is_published=True)
        .prefetch_related("health_focuses", "items__ingredient", "images")
        .distinct()
    )
    if focus_slugs:
        qs = qs.filter(health_focuses__slug__in=focus_slugs)
    if meal_type:
        qs = qs.filter(meal_type=meal_type)
    recipes = list(qs)
    # Hide recipes containing ingredients the user said to avoid
    if user.is_authenticated and hasattr(user, "profile"):
        avoid = user.profile.avoided_names()
        if avoid:
            recipes = [
                r for r in recipes if not any(i.ingredient.name.lower() in avoid for i in r.items.all())
            ]
    return recipes
