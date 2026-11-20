import json
from decimal import Decimal, InvalidOperation
from math import ceil

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .models import (
    DeliveryZone,
    HealthFocus,
    Ingredient,
    Order,
    OrderItem,
    PantryItem,
    Profile,
    Recipe,
    RecipeImage,
    RecipeIngredient,
)
from .services import build_gap, media_info, pantry_map, recipe_to_dict, video_embed_url, visible_recipes

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
MAX_IMAGES_PER_RECIPE = 8


# ---------------------------------------------------------------- helpers
def api_login_required(view):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


def api_staff_required(view):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        if not request.user.is_staff:
            return JsonResponse({"error": "Staff only"}, status=403)
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


def body(request):
    try:
        return json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return {}


def to_decimal(value, default=None):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return default


def ingredient_to_dict(i):
    return {
        "id": i.id,
        "name": i.name,
        "kinyarwanda_name": i.kinyarwanda_name,
        "category": i.category,
        "category_label": i.get_category_display(),
        "unit": i.unit,
        "price_per_unit_rwf": float(i.price_per_unit_rwf),
        "is_local": i.is_local,
    }


# ---------------------------------------------------------------- pages
def landing(request):
    """Public marketing page. Meals, costs and counts come straight from the database."""
    recipes = list(
        Recipe.objects.filter(is_published=True).prefetch_related("health_focuses", "items__ingredient", "images")
    )
    cards = []
    for r in recipes:
        items = list(r.items.all())
        total = sum(i.quantity * i.ingredient.price_per_unit_rwf for i in items)
        per_serving = int(ceil(total / max(r.base_servings, 1)))
        images = list(r.images.all())
        cards.append(
            {
                "id": r.id,
                "title": r.title,
                "emoji": r.emoji,
                "meal_type": r.meal_type,
                "prep": r.prep_minutes,
                "kcal": r.calories_per_serving,
                "cover": images[0].image.url if images else None,
                "cost_pp": per_serving,
                "cost_label": f"{per_serving:,}",
                "focuses": [{"slug": f.slug, "name": f.name, "icon": f.icon} for f in r.health_focuses.all()],
                "_items": items,
                "_servings": r.base_servings,
                "_total": total,
            }
        )

    group_defs = [
        ("breakfast", "Breakfasts", "Start the day with local grains, fruit and eggs."),
        ("lunch", "Lunches", "Filling plates built on beans, greens and tubers."),
        ("dinner", "Dinners", "Fish, chicken and vegetables for the family table."),
        ("snack", "Snacks & drinks", "Quick bites that fit a healthy day."),
    ]
    groups = [
        {"key": k, "label": label, "blurb": blurb, "recipes": [c for c in cards if c["meal_type"] == k]}
        for k, label, blurb in group_defs
    ]
    groups = [g for g in groups if g["recipes"]]

    # Pantry-savings example computed from a real recipe: pretend the first 3 ingredients are already at home.
    example = None
    # Choose the recipe with the most ingredients, and assume the user already owns a few
    # typical staples (mid-priced items; skipping the cheapest, which is usually just salt).
    pick = max((c for c in cards if len(c["_items"]) >= 5), key=lambda c: len(c["_items"]), default=None)
    if pick:
        by_cost = sorted(pick["_items"], key=lambda i: i.quantity * i.ingredient.price_per_unit_rwf)
        have_items = by_cost[1:4]
        have_cost = int(ceil(sum(i.quantity * i.ingredient.price_per_unit_rwf for i in have_items)))
        full = int(ceil(pick["_total"]))
        example = {
            "title": pick["title"],
            "emoji": pick["emoji"],
            "servings": pick["_servings"],
            "full": f"{full:,}",
            "saved": f"{have_cost:,}",
            "pay": f"{max(full - have_cost, 0):,}",
            "have": [i.ingredient.name for i in have_items],
            "need": [i.ingredient.name for i in pick["_items"] if i not in have_items][:3],
        }

    cheapest = sorted(cards, key=lambda c: c["cost_pp"])[:6]
    max_cost = max((c["cost_pp"] for c in cheapest), default=1) or 1
    for c in cheapest:
        c["bar"] = max(12, round(100 * c["cost_pp"] / max_cost))

    local_names = list(Ingredient.objects.filter(is_local=True).exclude(kinyarwanda_name="").values_list("kinyarwanda_name", "name")[:16])
    focuses = list(HealthFocus.objects.all())
    public = [{k: v for k, v in c.items() if not k.startswith("_")} for c in cards]
    cta_url = reverse("portal") if request.user.is_authenticated else reverse("register")

    return render(
        request,
        "kits/landing.html",
        {
            "groups": groups,
            "cheapest": cheapest,
            "example": example,
            "focuses": focuses,
            "ticker": local_names,
            "cta_url": cta_url,
            "stats": {
                "meals": len(cards),
                "ingredients": Ingredient.objects.count(),
                "focuses": len(focuses),
                "zones": DeliveryZone.objects.count(),
            },
            "landing_data": {
                "cta_url": cta_url,
                "recipes": public,
                "focuses": [{"slug": f.slug, "name": f.name, "icon": f.icon, "description": f.description} for f in focuses],
            },
        },
    )


def register(request):
    consent_missing = False
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        accepted = request.POST.get("accept_terms") == "on"
        if form.is_valid() and accepted:
            user = form.save()
            Profile.objects.create(user=user)
            login(request, user)
            return redirect("portal")
        consent_missing = not accepted
    else:
        form = UserCreationForm()
    return render(request, "kits/register.html", {"form": form, "consent_missing": consent_missing})


@login_required
@ensure_csrf_cookie
def portal(request):
    Profile.objects.get_or_create(user=request.user)
    return render(request, "kits/portal.html")


@ensure_csrf_cookie
@user_passes_test(lambda u: u.is_staff, login_url="login")
def dashboard(request):
    return render(request, "kits/dashboard.html")


# ---------------------------------------------------------------- shared API
@api_login_required
def api_version(request):
    """Cheap endpoint the front end polls; if the stamp changes, it re-fetches data."""
    stamp = Recipe.objects.aggregate(m=Max("updated_at"))["m"]
    return JsonResponse(
        {
            "recipes": stamp.isoformat() if stamp else None,
            "recipe_count": Recipe.objects.filter(is_published=True).count(),
        }
    )


@api_login_required
def api_meta(request):
    return JsonResponse(
        {
            "focuses": [
                {"id": f.id, "slug": f.slug, "name": f.name, "icon": f.icon, "description": f.description}
                for f in HealthFocus.objects.all()
            ],
            "zones": [
                {"id": z.id, "name": z.name, "fee_rwf": z.fee_rwf, "eta_minutes": z.eta_minutes}
                for z in DeliveryZone.objects.all()
            ],
            "meal_types": [{"value": v, "label": l} for v, l in Recipe.MEAL_TYPES],
            "categories": [{"value": v, "label": l} for v, l in Ingredient.CATEGORIES],
            "units": [{"value": v, "label": l} for v, l in Ingredient.UNITS],
            "payments": [{"value": v, "label": l} for v, l in Order.PAYMENTS],
            "user": {"username": request.user.username, "is_staff": request.user.is_staff},
        }
    )


@api_login_required
def api_ingredients(request):
    return JsonResponse({"ingredients": [ingredient_to_dict(i) for i in Ingredient.objects.all()]})


# ---------------------------------------------------------------- recipes (user)
@api_login_required
def api_recipes(request):
    focus = [s for s in request.GET.get("focus", "").split(",") if s]
    meal = request.GET.get("meal") or None
    q = request.GET.get("q", "").strip().lower()
    pantry = pantry_map(request.user)
    recipes = visible_recipes(request.user, focus, meal)
    data = [recipe_to_dict(r, pantry) for r in recipes]
    if q:
        data = [r for r in data if q in r["title"].lower() or q in r["description"].lower()]
    sort = request.GET.get("sort", "match")
    if sort == "match":
        data.sort(key=lambda r: (-r["match_percent"], r["missing_cost_rwf"]))
    elif sort == "cost":
        data.sort(key=lambda r: r["missing_cost_rwf"])
    elif sort == "calories":
        data.sort(key=lambda r: r["calories_per_serving"])
    return JsonResponse({"recipes": data})


@api_login_required
def api_recipe_detail(request, pk):
    try:
        recipe = Recipe.objects.prefetch_related("health_focuses", "items__ingredient", "images").get(pk=pk, is_published=True)
    except Recipe.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)
    servings = int(request.GET.get("servings") or recipe.base_servings)
    servings = max(1, min(servings, 20))
    return JsonResponse(recipe_to_dict(recipe, pantry_map(request.user), servings=servings))


# ---------------------------------------------------------------- pantry
@api_login_required
@require_http_methods(["GET", "POST"])
def api_pantry(request):
    if request.method == "POST":
        data = body(request)
        qty = to_decimal(data.get("quantity"))
        try:
            ing = Ingredient.objects.get(pk=data.get("ingredient_id"))
        except (Ingredient.DoesNotExist, ValueError, TypeError):
            return JsonResponse({"error": "Unknown ingredient"}, status=400)
        if qty is None or qty < 0:
            return JsonResponse({"error": "Quantity must be a positive number"}, status=400)
        if qty == 0:
            PantryItem.objects.filter(user=request.user, ingredient=ing).delete()
        else:
            PantryItem.objects.update_or_create(user=request.user, ingredient=ing, defaults={"quantity": qty})
    items = PantryItem.objects.filter(user=request.user).select_related("ingredient")
    return JsonResponse(
        {
            "pantry": [
                {"ingredient": ingredient_to_dict(p.ingredient), "quantity": float(p.quantity)} for p in items
            ]
        }
    )


@api_login_required
@require_http_methods(["DELETE"])
def api_pantry_delete(request, ingredient_id):
    PantryItem.objects.filter(user=request.user, ingredient_id=ingredient_id).delete()
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------- profile
@api_login_required
@require_http_methods(["GET", "POST"])
def api_profile(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        data = body(request)
        profile.allergies = str(data.get("allergies", ""))[:200]
        profile.phone = str(data.get("phone", ""))[:20]
        profile.address_note = str(data.get("address_note", ""))[:200]
        zone_id = data.get("delivery_zone")
        profile.delivery_zone = DeliveryZone.objects.filter(pk=zone_id).first() if zone_id else None
        profile.save()
        profile.health_focuses.set(HealthFocus.objects.filter(slug__in=data.get("focuses", [])))
    return JsonResponse(
        {
            "focuses": [f.slug for f in profile.health_focuses.all()],
            "allergies": profile.allergies,
            "phone": profile.phone,
            "address_note": profile.address_note,
            "delivery_zone": profile.delivery_zone_id,
        }
    )


# ---------------------------------------------------------------- orders
@api_login_required
@require_http_methods(["GET", "POST"])
def api_orders(request):
    if request.method == "POST":
        data = body(request)
        try:
            recipe = Recipe.objects.prefetch_related("items__ingredient").get(pk=data.get("recipe_id"), is_published=True)
            zone = DeliveryZone.objects.get(pk=data.get("zone_id"))
        except (Recipe.DoesNotExist, DeliveryZone.DoesNotExist, ValueError, TypeError):
            return JsonResponse({"error": "Choose a recipe and a delivery zone"}, status=400)
        servings = max(1, min(int(data.get("servings") or recipe.base_servings), 20))
        payment = data.get("payment_method", "momo")
        if payment not in dict(Order.PAYMENTS):
            payment = "momo"

        gap = build_gap(recipe, pantry_map(request.user), servings)
        to_buy = [l for l in gap["lines"] if l["missing"] > 0]
        if not to_buy:
            return JsonResponse({"error": "You already have everything for this meal. Nothing to buy!"}, status=400)

        with transaction.atomic():
            order = Order.objects.create(
                user=request.user,
                recipe=recipe,
                recipe_title=recipe.title,
                servings=servings,
                zone=zone,
                zone_name=zone.name,
                delivery_fee_rwf=zone.fee_rwf,
                subtotal_rwf=gap["missing_cost_rwf"],
                payment_method=payment,
            )
            OrderItem.objects.bulk_create(
                [
                    OrderItem(
                        order=order,
                        ingredient_name=l["name"],
                        unit=l["unit"],
                        quantity=Decimal(str(l["missing"])),
                        line_total_rwf=l["cost_rwf"],
                    )
                    for l in to_buy
                ]
            )
        return JsonResponse({"order": order_to_dict(order)}, status=201)

    orders = Order.objects.filter(user=request.user).prefetch_related("items")[:30]
    return JsonResponse({"orders": [order_to_dict(o) for o in orders]})


def order_to_dict(o):
    return {
        "id": o.id,
        "recipe_title": o.recipe_title,
        "servings": o.servings,
        "zone_name": o.zone_name,
        "delivery_fee_rwf": o.delivery_fee_rwf,
        "subtotal_rwf": o.subtotal_rwf,
        "total_rwf": o.total_rwf,
        "payment_method": o.get_payment_method_display(),
        "status": o.status,
        "status_label": o.get_status_display(),
        "created_at": o.created_at.isoformat(),
        "items": [
            {"name": i.ingredient_name, "unit": i.unit, "quantity": float(i.quantity), "line_total_rwf": i.line_total_rwf}
            for i in o.items.all()
        ],
    }


# ---------------------------------------------------------------- admin dashboard API
def admin_recipe_dict(r):
    return {
        "id": r.id,
        "title": r.title,
        "description": r.description,
        "instructions": r.instructions,
        "emoji": r.emoji,
        "meal_type": r.meal_type,
        "prep_minutes": r.prep_minutes,
        "base_servings": r.base_servings,
        "calories_per_serving": r.calories_per_serving,
        "doctor_note": r.doctor_note,
        "is_published": r.is_published,
        "focuses": [f.slug for f in r.health_focuses.all()],
        "items": [{"ingredient_id": i.ingredient_id, "name": i.ingredient.name, "quantity": float(i.quantity)} for i in r.items.all()],
        "images": [{"id": i.id, "url": i.image.url} for i in r.images.all()],
        "video": media_info(r)[1],
        "video_url": r.video_url,
        "has_video_file": bool(r.video_file),
        "updated_at": r.updated_at.isoformat(),
    }


@api_staff_required
@require_http_methods(["GET", "POST"])
def api_admin_recipes(request):
    if request.method == "POST":
        data = body(request)
        title = str(data.get("title", "")).strip()
        items = data.get("items") or []
        if not title:
            return JsonResponse({"error": "Title is required"}, status=400)
        if not items:
            return JsonResponse({"error": "Add at least one ingredient"}, status=400)

        clean = {}
        for row in items:
            qty = to_decimal(row.get("quantity"))
            if qty is None or qty <= 0 or not Ingredient.objects.filter(pk=row.get("ingredient_id")).exists():
                return JsonResponse({"error": "Every ingredient row needs a valid ingredient and quantity"}, status=400)
            clean[int(row["ingredient_id"])] = qty  # duplicates collapse (normalised)

        def num(key, default):
            try:
                return max(1, int(data.get(key) or default))
            except (TypeError, ValueError):
                return default

        with transaction.atomic():
            recipe = Recipe.objects.filter(pk=data.get("id")).first() or Recipe()
            recipe.title = title[:120]
            recipe.description = str(data.get("description", ""))
            recipe.instructions = str(data.get("instructions", ""))
            recipe.emoji = str(data.get("emoji") or "🍲")[:8]
            meal = data.get("meal_type")
            recipe.meal_type = meal if meal in dict(Recipe.MEAL_TYPES) else "lunch"
            recipe.prep_minutes = num("prep_minutes", 30)
            recipe.base_servings = num("base_servings", 2)
            recipe.calories_per_serving = num("calories_per_serving", 400)
            recipe.doctor_note = str(data.get("doctor_note", ""))[:240]
            recipe.is_published = bool(data.get("is_published", True))
            recipe.save()
            recipe.health_focuses.set(HealthFocus.objects.filter(slug__in=data.get("focuses", [])))
            recipe.items.all().delete()
            RecipeIngredient.objects.bulk_create(
                [RecipeIngredient(recipe=recipe, ingredient_id=i, quantity=q) for i, q in clean.items()]
            )
        recipe = Recipe.objects.prefetch_related("health_focuses", "items__ingredient", "images").get(pk=recipe.pk)
        return JsonResponse({"recipe": admin_recipe_dict(recipe)}, status=201)

    recipes = Recipe.objects.prefetch_related("health_focuses", "items__ingredient", "images").order_by("-updated_at")
    return JsonResponse({"recipes": [admin_recipe_dict(r) for r in recipes]})


@api_staff_required
@require_http_methods(["DELETE", "PATCH"])
def api_admin_recipe_detail(request, pk):
    recipe = Recipe.objects.filter(pk=pk).first()
    if not recipe:
        return JsonResponse({"error": "Not found"}, status=404)
    if request.method == "DELETE":
        recipe.delete()
        return JsonResponse({"ok": True})
    data = body(request)
    if "is_published" in data:
        recipe.is_published = bool(data["is_published"])
        recipe.save()
    return JsonResponse({"ok": True, "is_published": recipe.is_published})


# ---- recipe media (photos + demo video) -------------------------------------
def check_image(f):
    """Return an error message, or None if the upload is an acceptable photo."""
    if f.size > MAX_IMAGE_BYTES:
        return f"'{f.name}' is larger than 5 MB"
    fmt = None
    try:
        from PIL import Image

        img = Image.open(f)
        fmt = img.format
        img.verify()
    except Exception:
        return f"'{f.name}' is not a valid image"
    finally:
        f.seek(0)
    if fmt not in ("JPEG", "PNG", "WEBP"):
        return "Photos must be JPG, PNG or WebP"
    return None


def check_video(f):
    """Return an error message, or None if the upload looks like a real MP4/WebM under the size limit."""
    if f.size > MAX_VIDEO_BYTES:
        return "Video must be 50 MB or smaller. For longer videos, paste a YouTube or Vimeo link instead"
    name = f.name.lower()
    head = f.read(12)
    f.seek(0)
    if name.endswith(".mp4") and head[4:8] == b"ftyp":
        return None
    if name.endswith(".webm") and head[:4] == b"\x1a\x45\xdf\xa3":
        return None
    return "Video must be a valid MP4 or WebM file"


@api_staff_required
@require_http_methods(["POST"])
def api_admin_recipe_images(request, pk):
    recipe = Recipe.objects.filter(pk=pk).first()
    if not recipe:
        return JsonResponse({"error": "Not found"}, status=404)
    files = request.FILES.getlist("images")
    if not files:
        return JsonResponse({"error": "Choose at least one photo"}, status=400)
    if recipe.images.count() + len(files) > MAX_IMAGES_PER_RECIPE:
        return JsonResponse({"error": f"A recipe can have at most {MAX_IMAGES_PER_RECIPE} photos"}, status=400)
    for f in files:
        error = check_image(f)
        if error:
            return JsonResponse({"error": error}, status=400)
    position = recipe.images.aggregate(m=Max("position"))["m"] or 0
    for f in files:
        position += 1
        RecipeImage.objects.create(recipe=recipe, image=f, position=position)
    recipe.save()  # bumps updated_at so users' menus refresh
    return JsonResponse({"images": media_info(Recipe.objects.prefetch_related("images").get(pk=pk))[0]}, status=201)


@api_staff_required
@require_http_methods(["DELETE"])
def api_admin_recipe_image_detail(request, pk, image_id):
    image = RecipeImage.objects.filter(pk=image_id, recipe_id=pk).first()
    if not image:
        return JsonResponse({"error": "Not found"}, status=404)
    recipe = image.recipe
    image.delete()
    recipe.save()
    return JsonResponse({"ok": True})


@api_staff_required
@require_http_methods(["POST"])
def api_admin_recipe_video(request, pk):
    """Attach a demo video: an uploaded MP4/WebM file, a YouTube/Vimeo link, or clear=1 to remove it."""
    recipe = Recipe.objects.filter(pk=pk).first()
    if not recipe:
        return JsonResponse({"error": "Not found"}, status=404)
    upload = request.FILES.get("video")
    url = request.POST.get("video_url", "").strip()

    if upload:
        error = check_video(upload)
        if error:
            return JsonResponse({"error": error}, status=400)
        if recipe.video_file:
            recipe.video_file.delete(save=False)
        recipe.video_file = upload
        recipe.video_url = ""
    elif url:
        if not video_embed_url(url):
            return JsonResponse({"error": "Only YouTube or Vimeo links are supported"}, status=400)
        if recipe.video_file:
            recipe.video_file.delete(save=False)
            recipe.video_file = None
        recipe.video_url = url
    elif request.POST.get("clear"):
        if recipe.video_file:
            recipe.video_file.delete(save=False)
        recipe.video_file = None
        recipe.video_url = ""
    else:
        return JsonResponse({"error": "Upload a video file or paste a YouTube/Vimeo link"}, status=400)
    recipe.save()
    return JsonResponse({"video": media_info(recipe)[1]})


@api_staff_required
@require_http_methods(["POST"])
def api_admin_ingredients(request):
    data = body(request)
    name = str(data.get("name", "")).strip()
    price = to_decimal(data.get("price_per_unit_rwf"))
    if not name or price is None or price < 0:
        return JsonResponse({"error": "Name and a valid price are required"}, status=400)
    ing, _ = Ingredient.objects.update_or_create(
        name__iexact=name,
        defaults={
            "name": name,
            "kinyarwanda_name": str(data.get("kinyarwanda_name", ""))[:80],
            "category": data.get("category") if data.get("category") in dict(Ingredient.CATEGORIES) else "veg",
            "unit": data.get("unit") if data.get("unit") in dict(Ingredient.UNITS) else "g",
            "price_per_unit_rwf": price,
            "is_local": bool(data.get("is_local", True)),
        },
    )
    return JsonResponse({"ingredient": ingredient_to_dict(ing)}, status=201)


@api_staff_required
def api_admin_orders(request):
    if request.method == "POST":
        data = body(request)
        order = Order.objects.filter(pk=data.get("id")).first()
        if order and data.get("status") in dict(Order.STATUSES):
            order.status = data["status"]
            order.save()
    orders = Order.objects.select_related("user").prefetch_related("items")[:50]
    out = []
    for o in orders:
        d = order_to_dict(o)
        d["customer"] = o.user.username
        out.append(d)
    return JsonResponse({"orders": out, "statuses": [{"value": v, "label": l} for v, l in Order.STATUSES]})


@api_staff_required
def api_admin_stats(request):
    from django.db.models import Count, Sum

    delivered = Order.objects.exclude(status="cancelled")
    return JsonResponse(
        {
            "recipes": Recipe.objects.count(),
            "published": Recipe.objects.filter(is_published=True).count(),
            "ingredients": Ingredient.objects.count(),
            "orders": delivered.count(),
            "revenue_rwf": sum(o.total_rwf for o in delivered),
            "users": Profile.objects.count(),
        }
    )
