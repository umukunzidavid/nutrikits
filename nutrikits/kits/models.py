import os
import uuid

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone


def recipe_image_path(instance, filename):
    return f"recipe_images/{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()}"


def recipe_video_path(instance, filename):
    return f"recipe_videos/{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()}"


class HealthFocus(models.Model):
    """A clinical dietary focus a recipe can be tagged with (e.g. Diabetes-friendly)."""

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(unique=True)
    description = models.CharField(max_length=200, blank=True)
    icon = models.CharField(max_length=8, default="🥗")

    class Meta:
        verbose_name_plural = "health focuses"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Ingredient(models.Model):
    """Normalised ingredient: one row per ingredient, reused by every recipe and pantry."""

    UNITS = [("g", "grams"), ("ml", "millilitres"), ("pc", "pieces")]
    CATEGORIES = [
        ("veg", "Vegetables"),
        ("fruit", "Fruits"),
        ("grain", "Grains & Tubers"),
        ("legume", "Legumes"),
        ("protein", "Protein"),
        ("dairy", "Dairy"),
        ("pantry", "Oils, Spices & Staples"),
    ]

    name = models.CharField(max_length=80, unique=True)
    kinyarwanda_name = models.CharField(max_length=80, blank=True)
    category = models.CharField(max_length=10, choices=CATEGORIES, default="veg")
    unit = models.CharField(max_length=3, choices=UNITS, default="g")
    price_per_unit_rwf = models.DecimalField(
        max_digits=8, decimal_places=2, help_text="Price in RWF for ONE unit (1 g, 1 ml or 1 piece)."
    )
    is_local = models.BooleanField(default=True, help_text="Traditionally Rwandan / locally grown")

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return self.name


class Recipe(models.Model):
    MEAL_TYPES = [
        ("breakfast", "Breakfast"),
        ("lunch", "Lunch"),
        ("dinner", "Dinner"),
        ("snack", "Snack"),
    ]

    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    instructions = models.TextField(blank=True, help_text="One step per line.")
    emoji = models.CharField(max_length=8, default="🍲")
    meal_type = models.CharField(max_length=10, choices=MEAL_TYPES, default="lunch")
    prep_minutes = models.PositiveIntegerField(default=30)
    base_servings = models.PositiveIntegerField(default=2)
    calories_per_serving = models.PositiveIntegerField(default=400)
    doctor_note = models.CharField(
        max_length=240, blank=True, help_text="Short clinical rationale shown to users."
    )
    health_focuses = models.ManyToManyField(HealthFocus, related_name="recipes", blank=True)
    is_published = models.BooleanField(default=True)
    video_file = models.FileField(upload_to=recipe_video_path, blank=True, null=True, help_text="MP4 or WebM, max 50 MB")
    video_url = models.URLField(blank=True, help_text="YouTube or Vimeo link (used if no video file)")
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class RecipeIngredient(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="items")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="recipe_items")
    quantity = models.DecimalField(
        max_digits=8, decimal_places=2, help_text="Amount for the recipe's base servings."
    )

    class Meta:
        unique_together = ("recipe", "ingredient")

    def __str__(self):
        return f"{self.quantity}{self.ingredient.unit} {self.ingredient.name}"


class RecipeImage(models.Model):
    """Gallery photo for a recipe. The first image (lowest position) is the cover."""

    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=recipe_image_path)
    caption = models.CharField(max_length=120, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"Image {self.pk} of {self.recipe}"


class DeliveryZone(models.Model):
    name = models.CharField(max_length=60, unique=True)
    fee_rwf = models.PositiveIntegerField()
    eta_minutes = models.PositiveIntegerField(default=60)

    class Meta:
        ordering = ["fee_rwf", "name"]

    def __str__(self):
        return f"{self.name} ({self.fee_rwf} RWF)"


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    health_focuses = models.ManyToManyField(HealthFocus, blank=True, related_name="profiles")
    allergies = models.CharField(max_length=200, blank=True, help_text="Comma separated ingredient names to avoid")
    delivery_zone = models.ForeignKey(DeliveryZone, null=True, blank=True, on_delete=models.SET_NULL)
    phone = models.CharField(max_length=20, blank=True)
    address_note = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"Profile of {self.user}"

    def avoided_names(self):
        return {a.strip().lower() for a in self.allergies.split(",") if a.strip()}


class PantryItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pantry")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        unique_together = ("user", "ingredient")

    def __str__(self):
        return f"{self.user}: {self.quantity}{self.ingredient.unit} {self.ingredient.name}"


class Order(models.Model):
    STATUSES = [
        ("placed", "Placed"),
        ("packing", "Packing"),
        ("out", "Out for delivery"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]
    PAYMENTS = [("momo", "MTN MoMo"), ("airtel", "Airtel Money"), ("cash", "Cash on delivery")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders")
    recipe = models.ForeignKey(Recipe, null=True, on_delete=models.SET_NULL)
    recipe_title = models.CharField(max_length=120)
    servings = models.PositiveIntegerField(default=2)
    zone = models.ForeignKey(DeliveryZone, null=True, on_delete=models.SET_NULL)
    zone_name = models.CharField(max_length=60)
    delivery_fee_rwf = models.PositiveIntegerField(default=0)
    subtotal_rwf = models.PositiveIntegerField(default=0)
    payment_method = models.CharField(max_length=10, choices=PAYMENTS, default="momo")
    status = models.CharField(max_length=10, choices=STATUSES, default="placed")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    @property
    def total_rwf(self):
        return self.subtotal_rwf + self.delivery_fee_rwf

    def __str__(self):
        return f"Order #{self.pk} – {self.recipe_title}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    ingredient_name = models.CharField(max_length=80)
    unit = models.CharField(max_length=3)
    quantity = models.DecimalField(max_digits=8, decimal_places=2)
    line_total_rwf = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.quantity}{self.unit} {self.ingredient_name}"


@receiver(post_delete, sender=RecipeImage)
def delete_image_file(sender, instance, **kwargs):
    if instance.image:
        instance.image.delete(save=False)


@receiver(post_delete, sender=Recipe)
def delete_video_file(sender, instance, **kwargs):
    if instance.video_file:
        instance.video_file.delete(save=False)
