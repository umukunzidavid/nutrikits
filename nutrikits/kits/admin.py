from django.contrib import admin

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


@admin.register(HealthFocus)
class HealthFocusAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "icon")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ("name", "kinyarwanda_name", "category", "unit", "price_per_unit_rwf", "is_local")
    list_filter = ("category", "is_local")
    search_fields = ("name", "kinyarwanda_name")


class RecipeIngredientInline(admin.TabularInline):
    model = RecipeIngredient
    extra = 3


class RecipeImageInline(admin.TabularInline):
    model = RecipeImage
    extra = 1


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("title", "meal_type", "calories_per_serving", "is_published", "updated_at")
    list_filter = ("meal_type", "is_published", "health_focuses")
    search_fields = ("title",)
    filter_horizontal = ("health_focuses",)
    inlines = [RecipeIngredientInline, RecipeImageInline]


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "fee_rwf", "eta_minutes")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("ingredient_name", "unit", "quantity", "line_total_rwf")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "recipe_title", "zone_name", "subtotal_rwf", "delivery_fee_rwf", "status", "created_at")
    list_filter = ("status", "payment_method", "zone_name")
    list_editable = ("status",)
    inlines = [OrderItemInline]


admin.site.register(Profile)
admin.site.register(PantryItem)
