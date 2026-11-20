from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from kits.models import (
    DeliveryZone,
    HealthFocus,
    Ingredient,
    PantryItem,
    Profile,
    Recipe,
    RecipeIngredient,
)

FOCUSES = [
    ("Diabetes-friendly", "diabetes", "🩸", "Low glycaemic, high fibre meals"),
    ("Hypertension", "hypertension", "❤️", "Low sodium, potassium-rich meals"),
    ("Anaemia / Iron boost", "anaemia", "💪", "Iron and vitamin C rich meals"),
    ("Maternal & Pregnancy", "maternal", "🤰", "Folate, calcium and protein for mothers"),
    ("Child nutrition", "child", "🧒", "Growth-supporting meals for children"),
    ("Weight management", "weight", "⚖️", "Filling meals with controlled calories"),
    ("Heart health", "heart", "🫀", "Healthy fats, low saturated fat"),
]

# name, kinyarwanda, category, unit, price per unit (RWF), local
INGREDIENTS = [
    ("Sweet potato", "Ibijumba", "grain", "g", "0.5", True),
    ("Irish potato", "Ibirayi", "grain", "g", "0.6", True),
    ("Cassava flour", "Ifu y'imyumbati", "grain", "g", "1.2", True),
    ("Sorghum flour", "Ifu y'amasaka", "grain", "g", "1.5", True),
    ("Maize flour", "Ifu y'ibigori", "grain", "g", "1.0", True),
    ("Rice", "Umuceri", "grain", "g", "1.4", False),
    ("Red kidney beans", "Ibishyimbo", "legume", "g", "1.3", True),
    ("Peas", "Amashaza", "legume", "g", "1.5", True),
    ("Groundnuts", "Ubunyobwa", "legume", "g", "2.8", True),
    ("Cassava leaves", "Isombe", "veg", "g", "1.0", True),
    ("Amaranth leaves", "Dodo", "veg", "g", "0.8", True),
    ("Spinach", "Epinari", "veg", "g", "0.9", True),
    ("Carrot", "Karoti", "veg", "g", "0.8", True),
    ("Tomato", "Inyanya", "veg", "g", "1.0", True),
    ("Onion", "Igitunguru", "veg", "g", "1.1", True),
    ("Garlic", "Tungurusumu", "veg", "g", "4.0", True),
    ("Green banana (matoke)", "Igitoki", "grain", "g", "0.7", True),
    ("Pumpkin", "Igihaza", "veg", "g", "0.6", True),
    ("Eggplant", "Intoryi", "veg", "g", "1.0", True),
    ("Cabbage", "Amashu", "veg", "g", "0.6", True),
    ("Avocado", "Avoka", "fruit", "pc", "350", True),
    ("Banana (ripe)", "Igitoki cyeze", "fruit", "pc", "100", True),
    ("Passion fruit", "Marakuja", "fruit", "pc", "120", True),
    ("Tilapia (Lake Kivu)", "Tilapiya", "protein", "g", "4.5", True),
    ("Chicken breast", "Inkoko", "protein", "g", "5.5", False),
    ("Eggs", "Amagi", "protein", "pc", "200", True),
    ("Small dried fish (isambaza)", "Isambaza", "protein", "g", "6.0", True),
    ("Goat meat", "Ihene", "protein", "g", "7.0", True),
    ("Milk", "Amata", "dairy", "ml", "0.9", True),
    ("Yoghurt (ikivuguto)", "Ikivuguto", "dairy", "ml", "1.1", True),
    ("Cooking oil", "Amavuta", "pantry", "ml", "2.4", False),
    ("Salt", "Umunyu", "pantry", "g", "0.8", False),
    ("Ginger", "Tangawizi", "pantry", "g", "5.0", True),
    ("Rwandan tea leaves", "Icyayi", "pantry", "g", "6.0", True),
    ("Honey", "Ubuki", "pantry", "ml", "6.5", True),
]

ZONES = [
    ("Nyarugenge (City centre)", 1000, 45),
    ("Kiyovu / Kimihurura", 1500, 50),
    ("Kacyiru / Gisozi", 1500, 55),
    ("Remera / Kisimenti", 2000, 60),
    ("Kicukiro / Gikondo", 2000, 65),
    ("Kanombe / Airport", 2500, 75),
    ("Nyamirambo", 1500, 55),
    ("Kimironko / Bumbogo", 2500, 70),
]

# title, emoji, meal, prep, servings, kcal, note, focuses, [ (ingredient, qty) ], description, steps
RECIPES = [
    (
        "Isombe with Sweet Potato", "🍠", "lunch", 45, 2, 420,
        "Cassava leaves and sweet potato give slow-release carbohydrate and plenty of fibre, helping steady blood sugar.",
        ["diabetes", "weight", "heart"],
        [("Cassava leaves", 400), ("Sweet potato", 400), ("Groundnuts", 40), ("Onion", 60), ("Garlic", 8), ("Cooking oil", 15), ("Salt", 3)],
        "A Rwandan classic: slow-cooked pounded cassava leaves in a groundnut sauce, served with boiled sweet potato.",
        "Boil the sweet potato until tender.\nSimmer the cassava leaves with onion and garlic for 30 minutes.\nStir in ground groundnuts and oil, season lightly.\nServe the isombe beside the sweet potato.",
    ),
    (
        "Beans & Amaranth Iron Plate", "🫘", "dinner", 40, 2, 480,
        "Beans plus dodo are an excellent plant iron source; the tomato's vitamin C improves absorption.",
        ["anaemia", "maternal", "child"],
        [("Red kidney beans", 250), ("Amaranth leaves", 300), ("Tomato", 150), ("Onion", 80), ("Garlic", 6), ("Cooking oil", 20), ("Salt", 3), ("Maize flour", 200)],
        "Hearty kidney beans with dodo greens and tomato, served with ugali.",
        "Boil beans until soft.\nFry onion, garlic and tomato, add the beans.\nAdd dodo and simmer for 10 minutes.\nCook the maize flour into ugali and serve together.",
    ),
    (
        "Grilled Lake Kivu Tilapia", "🐟", "dinner", 35, 2, 390,
        "Lean fish protein with omega-3 fats supports heart and blood pressure health. Cooked with minimal salt.",
        ["hypertension", "heart", "weight", "diabetes"],
        [("Tilapia (Lake Kivu)", 500), ("Tomato", 200), ("Onion", 80), ("Ginger", 15), ("Garlic", 8), ("Cooking oil", 15), ("Irish potato", 400), ("Salt", 2)],
        "Whole tilapia grilled with ginger and garlic, with a fresh tomato salsa and boiled potatoes.",
        "Rub the fish with ginger, garlic and a pinch of salt.\nGrill 8 minutes each side.\nBoil the potatoes.\nMix tomato and onion as a salsa and serve.",
    ),
    (
        "Umutsima Cassava-Sorghum Bowl", "🥣", "breakfast", 25, 2, 340,
        "Sorghum is a low-glycaemic whole grain, a good choice for people managing diabetes.",
        ["diabetes", "weight"],
        [("Sorghum flour", 120), ("Cassava flour", 80), ("Milk", 200), ("Honey", 10), ("Banana (ripe)", 1)],
        "A warm porridge-style bowl of sorghum and cassava, topped with banana and a touch of honey.",
        "Whisk the flours into hot water to make a smooth paste.\nSimmer 10 minutes stirring often.\nPour in warm milk.\nTop with sliced banana and a drizzle of honey.",
    ),
    (
        "Avocado & Egg Breakfast Plate", "🥑", "breakfast", 15, 2, 410,
        "Monounsaturated fats from avocado and complete protein from eggs support heart health and keep you full.",
        ["heart", "weight", "maternal"],
        [("Avocado", 1), ("Eggs", 4), ("Tomato", 100), ("Cooking oil", 10), ("Salt", 1)],
        "Soft-scrambled eggs with ripe avocado and tomato.",
        "Slice the avocado and tomato.\nScramble the eggs gently in a little oil.\nPlate together and season lightly.",
    ),
    (
        "Pumpkin & Carrot Child Mash", "🎃", "lunch", 30, 2, 260,
        "Soft, vitamin A rich vegetables with added protein to support healthy growth in young children.",
        ["child", "maternal"],
        [("Pumpkin", 300), ("Carrot", 150), ("Irish potato", 200), ("Eggs", 2), ("Milk", 100), ("Salt", 1)],
        "A smooth, mild mash of pumpkin, carrot and potato with a boiled egg on the side.",
        "Boil pumpkin, carrot and potato until very soft.\nMash with warm milk.\nHard-boil the eggs and serve alongside.",
    ),
    (
        "Spinach & Chicken Iron Stew", "🍲", "dinner", 45, 3, 450,
        "Chicken and spinach combine haem and non-haem iron; a squeeze of passion fruit adds vitamin C.",
        ["anaemia", "maternal"],
        [("Chicken breast", 450), ("Spinach", 300), ("Tomato", 200), ("Onion", 100), ("Garlic", 10), ("Rice", 300), ("Cooking oil", 20), ("Passion fruit", 2), ("Salt", 3)],
        "Tender chicken simmered with spinach and tomato, served with steamed rice.",
        "Brown the chicken pieces in oil.\nAdd onion, garlic and tomato and simmer 20 minutes.\nFold in the spinach for the last 5 minutes.\nServe with rice and fresh passion fruit juice.",
    ),
    (
        "Matoke with Groundnut Sauce", "🍌", "lunch", 50, 3, 470,
        "Matoke is rich in potassium, which helps counter the effect of sodium on blood pressure.",
        ["hypertension", "heart"],
        [("Green banana (matoke)", 700), ("Groundnuts", 60), ("Tomato", 200), ("Onion", 80), ("Carrot", 100), ("Cooking oil", 15), ("Salt", 2)],
        "Steamed green banana with a creamy groundnut and vegetable sauce, very light on salt.",
        "Peel and steam the matoke 30 minutes.\nSauté onion, carrot and tomato.\nStir in ground groundnuts and simmer.\nServe the sauce over the matoke.",
    ),
    (
        "Isambaza & Cabbage Skillet", "🐠", "dinner", 30, 2, 380,
        "Small whole fish provide calcium and omega-3; a nutrient-dense choice for mothers and children.",
        ["maternal", "child", "anaemia"],
        [("Small dried fish (isambaza)", 150), ("Cabbage", 300), ("Tomato", 150), ("Onion", 70), ("Cooking oil", 15), ("Sweet potato", 400)],
        "Crispy isambaza tossed with cabbage and tomato, with boiled sweet potato.",
        "Boil the sweet potato.\nFry the isambaza until crisp.\nSauté cabbage, onion and tomato.\nCombine and serve.",
    ),
    (
        "Ikivuguto & Fruit Snack Cup", "🥛", "snack", 5, 1, 220,
        "Fermented milk offers probiotics and calcium, and the fruit provides vitamin C and fibre.",
        ["child", "maternal", "weight"],
        [("Yoghurt (ikivuguto)", 250), ("Banana (ripe)", 1), ("Passion fruit", 1), ("Honey", 5)],
        "Chilled ikivuguto layered with banana and passion fruit.",
        "Slice the banana.\nLayer yoghurt, banana and passion fruit pulp in a cup.\nFinish with a little honey.",
    ),
    (
        "Ginger Tea & Sweet Potato Snack", "🍵", "snack", 20, 2, 190,
        "A low-sodium, fibre-rich snack with warming ginger; pairs well with a hypertension-friendly diet.",
        ["hypertension", "weight", "diabetes"],
        [("Rwandan tea leaves", 6), ("Ginger", 10), ("Sweet potato", 300), ("Milk", 150)],
        "Rwandan tea brewed with fresh ginger and milk, served with baked sweet potato.",
        "Bake or boil the sweet potato.\nSimmer tea leaves with ginger.\nAdd warm milk and serve.",
    ),
    (
        "Eggplant & Bean Lunch Bowl", "🍆", "lunch", 35, 2, 430,
        "High fibre and plant protein with no added sugar, supporting steady blood glucose.",
        ["diabetes", "heart", "weight"],
        [("Eggplant", 300), ("Red kidney beans", 200), ("Tomato", 150), ("Onion", 70), ("Garlic", 6), ("Cooking oil", 15), ("Rice", 150)],
        "Roasted eggplant with a bean and tomato stew over a small portion of rice.",
        "Roast the eggplant slices.\nSimmer cooked beans with onion, garlic and tomato.\nServe over a modest portion of rice.",
    ),
]


class Command(BaseCommand):
    help = "Seed NutriKits Rwanda with Rwandan ingredients, health focuses, delivery zones and sample recipes."

    def handle(self, *args, **opts):
        for name, slug, icon, desc in FOCUSES:
            HealthFocus.objects.update_or_create(slug=slug, defaults={"name": name, "icon": icon, "description": desc})

        for name, kiny, cat, unit, price, local in INGREDIENTS:
            Ingredient.objects.update_or_create(
                name=name,
                defaults={"kinyarwanda_name": kiny, "category": cat, "unit": unit, "price_per_unit_rwf": Decimal(price), "is_local": local},
            )

        for name, fee, eta in ZONES:
            DeliveryZone.objects.update_or_create(name=name, defaults={"fee_rwf": fee, "eta_minutes": eta})

        for title, emoji, meal, prep, serv, kcal, note, focuses, items, desc, steps in RECIPES:
            recipe, _ = Recipe.objects.update_or_create(
                title=title,
                defaults={
                    "emoji": emoji, "meal_type": meal, "prep_minutes": prep, "base_servings": serv,
                    "calories_per_serving": kcal, "doctor_note": note, "description": desc,
                    "instructions": steps, "is_published": True,
                },
            )
            recipe.health_focuses.set(HealthFocus.objects.filter(slug__in=focuses))
            recipe.items.all().delete()
            RecipeIngredient.objects.bulk_create(
                [RecipeIngredient(recipe=recipe, ingredient=Ingredient.objects.get(name=n), quantity=Decimal(str(q))) for n, q in items]
            )

        User = get_user_model()
        admin, created = User.objects.get_or_create(username="admin", defaults={"is_staff": True, "is_superuser": True})
        if created:
            admin.set_password("admin12345")
            admin.save()
        Profile.objects.get_or_create(user=admin)

        demo, created = User.objects.get_or_create(username="demo")
        if created:
            demo.set_password("demo12345")
            demo.save()
        profile, _ = Profile.objects.get_or_create(user=demo)
        profile.delivery_zone = DeliveryZone.objects.first()
        profile.save()
        profile.health_focuses.set(HealthFocus.objects.filter(slug__in=["diabetes"]))
        for n, q in [("Sweet potato", 500), ("Onion", 100), ("Salt", 50), ("Cooking oil", 200), ("Tomato", 150)]:
            PantryItem.objects.update_or_create(user=demo, ingredient=Ingredient.objects.get(name=n), defaults={"quantity": Decimal(q)})

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {HealthFocus.objects.count()} focuses, {Ingredient.objects.count()} ingredients, "
            f"{DeliveryZone.objects.count()} zones, {Recipe.objects.count()} recipes. "
            "Logins -> admin/admin12345 (staff), demo/demo12345 (customer)."
        ))
