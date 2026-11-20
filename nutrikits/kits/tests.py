import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from .models import DeliveryZone, Ingredient, Order, PantryItem, Profile, Recipe
from .services import build_gap, pantry_map

User = get_user_model()


class NutriKitsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed", verbosity=0)

    def setUp(self):
        self.demo = User.objects.get(username="demo")
        self.admin = User.objects.get(username="admin")

    def post_json(self, url, data):
        return self.client.post(url, json.dumps(data), content_type="application/json")

    # ---- matching engine
    def test_gap_uses_pantry_and_scales_servings(self):
        recipe = Recipe.objects.get(title="Isombe with Sweet Potato")
        pantry = pantry_map(self.demo)  # demo has 500g sweet potato, onion, salt, oil
        gap = build_gap(recipe, pantry)
        sweet = next(l for l in gap["lines"] if l["name"] == "Sweet potato")
        self.assertTrue(sweet["in_pantry"])
        self.assertGreater(gap["match_percent"], 0)
        self.assertEqual(gap["full_cost_rwf"] - gap["missing_cost_rwf"], gap["savings_rwf"])
        # doubling servings needs 800g sweet potato; only 500g in pantry -> 300g missing
        gap4 = build_gap(recipe, pantry, servings=4)
        sweet4 = next(l for l in gap4["lines"] if l["name"] == "Sweet potato")
        self.assertEqual(sweet4["missing"], 300.0)

    def test_piece_ingredients_round_up(self):
        recipe = Recipe.objects.get(title="Avocado & Egg Breakfast Plate")
        gap = build_gap(recipe, {}, servings=3)  # 1.5 avocado -> buy 2
        avocado = next(l for l in gap["lines"] if l["name"] == "Avocado")
        self.assertEqual(avocado["missing"], 2.0)

    # ---- auth
    def test_api_requires_login(self):
        self.assertEqual(self.client.get("/api/recipes/").status_code, 401)

    def test_portal_redirects_when_anonymous(self):
        self.assertEqual(self.client.get("/app/").status_code, 302)

    def test_landing_is_public_and_has_safety_section(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'id="safety"')
        self.assertContains(r, "not a medical service")

    def test_register_creates_profile(self):
        r = self.client.post("/register/", {"username": "newuser", "password1": "Str0ng-pass-99", "password2": "Str0ng-pass-99", "accept_terms": "on"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Profile.objects.filter(user__username="newuser").exists())

    def test_register_requires_safety_acknowledgement(self):
        r = self.client.post("/register/", {"username": "nocheck", "password1": "Str0ng-pass-99", "password2": "Str0ng-pass-99"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "confirm you have read the safety notice")
        self.assertFalse(Profile.objects.filter(user__username="nocheck").exists())

    # ---- recipes + filters
    def test_focus_filter_and_sorting(self):
        self.client.force_login(self.demo)
        data = self.client.get("/api/recipes/?focus=hypertension&sort=match").json()["recipes"]
        self.assertTrue(data)
        for r in data:
            self.assertIn("hypertension", [f["slug"] for f in r["focuses"]])
        pct = [r["match_percent"] for r in data]
        self.assertEqual(pct, sorted(pct, reverse=True))

    def test_allergy_hides_recipes(self):
        self.client.force_login(self.demo)
        before = len(self.client.get("/api/recipes/").json()["recipes"])
        self.post_json("/api/profile/", {"allergies": "Groundnuts", "focuses": []})
        after = self.client.get("/api/recipes/").json()["recipes"]
        self.assertLess(len(after), before)
        self.assertNotIn("Isombe with Sweet Potato", [r["title"] for r in after])

    # ---- pantry
    def test_pantry_add_update_remove(self):
        self.client.force_login(self.demo)
        rice = Ingredient.objects.get(name="Rice")
        self.post_json("/api/pantry/", {"ingredient_id": rice.id, "quantity": 500})
        self.assertEqual(PantryItem.objects.get(user=self.demo, ingredient=rice).quantity, Decimal("500"))
        self.post_json("/api/pantry/", {"ingredient_id": rice.id, "quantity": 0})  # zero removes
        self.assertFalse(PantryItem.objects.filter(user=self.demo, ingredient=rice).exists())
        bad = self.post_json("/api/pantry/", {"ingredient_id": rice.id, "quantity": -5})
        self.assertEqual(bad.status_code, 400)

    # ---- orders
    def test_order_only_charges_missing_ingredients(self):
        self.client.force_login(self.demo)
        recipe = Recipe.objects.get(title="Isombe with Sweet Potato")
        zone = DeliveryZone.objects.first()
        gap = build_gap(recipe, pantry_map(self.demo))
        res = self.post_json("/api/orders/", {"recipe_id": recipe.id, "zone_id": zone.id, "payment_method": "momo"})
        self.assertEqual(res.status_code, 201)
        order = Order.objects.get()
        self.assertEqual(order.subtotal_rwf, gap["missing_cost_rwf"])
        self.assertEqual(order.total_rwf, gap["missing_cost_rwf"] + zone.fee_rwf)
        self.assertNotIn("Sweet potato", [i.ingredient_name for i in order.items.all()])

    def test_order_rejected_when_nothing_missing(self):
        self.client.force_login(self.demo)
        for ing in Ingredient.objects.all():
            PantryItem.objects.update_or_create(user=self.demo, ingredient=ing, defaults={"quantity": 100000})
        recipe = Recipe.objects.first()
        res = self.post_json("/api/orders/", {"recipe_id": recipe.id, "zone_id": DeliveryZone.objects.first().id})
        self.assertEqual(res.status_code, 400)

    # ---- admin dashboard
    def test_non_staff_blocked_from_admin_api(self):
        self.client.force_login(self.demo)
        self.assertEqual(self.client.get("/api/admin/recipes/").status_code, 403)
        self.assertEqual(self.client.get("/dashboard/").status_code, 302)

    def test_admin_publish_updates_version_for_live_sync(self):
        self.client.force_login(self.demo)
        v1 = self.client.get("/api/version/").json()
        self.client.force_login(self.admin)
        tomato = Ingredient.objects.get(name="Tomato")
        res = self.post_json("/api/admin/recipes/", {
            "title": "Test Kit", "focuses": ["diabetes"], "meal_type": "lunch",
            "items": [{"ingredient_id": tomato.id, "quantity": 100}, {"ingredient_id": tomato.id, "quantity": 250}],
        })
        self.assertEqual(res.status_code, 201)
        recipe = Recipe.objects.get(title="Test Kit")
        self.assertEqual(recipe.items.count(), 1)  # duplicate rows collapse
        self.assertEqual(recipe.items.get().quantity, Decimal("250"))
        self.client.force_login(self.demo)
        v2 = self.client.get("/api/version/").json()
        self.assertNotEqual(v1, v2)
        self.assertIn("Test Kit", [r["title"] for r in self.client.get("/api/recipes/").json()["recipes"]])

    def test_admin_validation_and_unpublish(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.post_json("/api/admin/recipes/", {"title": "", "items": []}).status_code, 400)
        self.assertEqual(self.post_json("/api/admin/recipes/", {"title": "x", "items": []}).status_code, 400)
        recipe = Recipe.objects.first()
        self.client.patch(f"/api/admin/recipes/{recipe.id}/", json.dumps({"is_published": False}), content_type="application/json")
        self.client.force_login(self.demo)
        self.assertNotIn(recipe.title, [r["title"] for r in self.client.get("/api/recipes/").json()["recipes"]])

    def test_pages_render(self):
        self.client.force_login(self.admin)
        for url in ["/", "/app/", "/dashboard/"]:
            self.assertEqual(self.client.get(url).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get("/login/").status_code, 200)
        self.assertEqual(self.client.get("/register/").status_code, 200)


# ======================================================================= media (photos + video)
import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image

from .services import video_embed_url

TMP_MEDIA = tempfile.mkdtemp(prefix="nutrikits-test-media-")


def make_png(name="photo.png", size=(40, 30)):
    buf = io.BytesIO()
    Image.new("RGB", size, "green").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def fake_mp4(name="demo.mp4", extra=1024):
    return SimpleUploadedFile(name, b"\x00\x00\x00\x18ftypmp42" + b"\x00" * extra, content_type="video/mp4")


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class MediaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed", verbosity=0)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.admin = User.objects.get(username="admin")
        self.demo = User.objects.get(username="demo")
        self.recipe = Recipe.objects.get(title="Isombe with Sweet Potato")
        self.client.force_login(self.admin)

    def upload_images(self, *files):
        return self.client.post(f"/api/admin/recipes/{self.recipe.id}/images/", {"images": list(files)})

    def post_video(self, **data):
        return self.client.post(f"/api/admin/recipes/{self.recipe.id}/video/", data)

    # ---- photos
    def test_upload_multiple_photos_and_cover_in_user_api(self):
        res = self.upload_images(make_png("a.png"), make_png("b.png"))
        self.assertEqual(res.status_code, 201)
        self.assertEqual(self.recipe.images.count(), 2)
        self.client.force_login(self.demo)
        data = self.client.get(f"/api/recipes/{self.recipe.id}/").json()
        self.assertEqual(len(data["images"]), 2)
        self.assertEqual(data["cover"], data["images"][0]["url"])
        listed = next(r for r in self.client.get("/api/recipes/").json()["recipes"] if r["id"] == self.recipe.id)
        self.assertTrue(listed["cover"])

    def test_fake_image_rejected(self):
        bad = SimpleUploadedFile("evil.png", b"not really an image", content_type="image/png")
        self.assertEqual(self.upload_images(bad).status_code, 400)
        self.assertEqual(self.recipe.images.count(), 0)

    def test_oversized_image_rejected(self):
        big = SimpleUploadedFile("big.png", make_png().read() + b"\x00" * (5 * 1024 * 1024), content_type="image/png")
        res = self.upload_images(big)
        self.assertEqual(res.status_code, 400)
        self.assertIn("5 MB", res.json()["error"])

    def test_max_eight_photos(self):
        for i in range(8):
            self.assertEqual(self.upload_images(make_png(f"{i}.png")).status_code, 201)
        res = self.upload_images(make_png("9.png"))
        self.assertEqual(res.status_code, 400)
        self.assertIn("at most 8", res.json()["error"])

    def test_delete_photo_removes_file(self):
        self.upload_images(make_png())
        img = self.recipe.images.get()
        path = img.image.path
        import os

        self.assertTrue(os.path.exists(path))
        self.assertEqual(self.client.delete(f"/api/admin/recipes/{self.recipe.id}/images/{img.id}/").status_code, 200)
        self.assertFalse(os.path.exists(path))

    # ---- video
    def test_upload_video_file(self):
        res = self.post_video(video=fake_mp4())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["video"]["type"], "file")
        self.recipe.refresh_from_db()
        self.assertTrue(self.recipe.video_file)

    def test_fake_or_oversized_video_rejected(self):
        bad = SimpleUploadedFile("x.mp4", b"this is not a video", content_type="video/mp4")
        self.assertEqual(self.post_video(video=bad).status_code, 400)
        big = fake_mp4(extra=50 * 1024 * 1024)
        res = self.post_video(video=big)
        self.assertEqual(res.status_code, 400)
        self.assertIn("50 MB", res.json()["error"])
        exe = SimpleUploadedFile("x.exe", b"\x00\x00\x00\x18ftypmp42", content_type="video/mp4")
        self.assertEqual(self.post_video(video=exe).status_code, 400)

    def test_youtube_link_becomes_embed_and_other_sites_rejected(self):
        res = self.post_video(video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["video"], {"type": "embed", "url": "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"})
        self.assertEqual(self.post_video(video_url="https://evil.example.com/watch?v=dQw4w9WgXcQ").status_code, 400)
        self.assertEqual(self.post_video(video_url="javascript:alert(1)").status_code, 400)

    def test_file_replaces_link_and_clear_removes_all(self):
        self.post_video(video_url="https://youtu.be/dQw4w9WgXcQ")
        self.post_video(video=fake_mp4())
        self.recipe.refresh_from_db()
        self.assertTrue(self.recipe.video_file)
        self.assertEqual(self.recipe.video_url, "")
        self.assertEqual(self.post_video(clear="1").status_code, 200)
        self.recipe.refresh_from_db()
        self.assertFalse(self.recipe.video_file)
        self.client.force_login(self.demo)
        self.assertIsNone(self.client.get(f"/api/recipes/{self.recipe.id}/").json()["video"])

    def test_video_embed_url_parsing(self):
        ok = {
            "https://youtu.be/dQw4w9WgXcQ": "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=5": "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ": "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
            "https://vimeo.com/123456789": "https://player.vimeo.com/video/123456789",
        }
        for src, expected in ok.items():
            self.assertEqual(video_embed_url(src), expected)
        for bad in ["", "ftp://youtu.be/dQw4w9WgXcQ", "https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ", "https://youtube.com/watch?v=short"]:
            self.assertIsNone(video_embed_url(bad))

    # ---- permissions + sync
    def test_non_staff_cannot_upload(self):
        self.client.force_login(self.demo)
        self.assertEqual(self.upload_images(make_png()).status_code, 403)
        self.assertEqual(self.post_video(clear="1").status_code, 403)

    def test_media_change_bumps_live_sync_version(self):
        self.client.force_login(self.demo)
        v1 = self.client.get("/api/version/").json()
        self.client.force_login(self.admin)
        self.upload_images(make_png())
        self.client.force_login(self.demo)
        self.assertNotEqual(v1, self.client.get("/api/version/").json())

    def test_deleting_recipe_removes_video_file(self):
        import os

        self.post_video(video=fake_mp4())
        self.recipe.refresh_from_db()
        path = self.recipe.video_file.path
        self.assertTrue(os.path.exists(path))
        self.client.delete(f"/api/admin/recipes/{self.recipe.id}/")
        self.assertFalse(os.path.exists(path))


# ======================================================================= landing page data + pages
class LandingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed", verbosity=0)

    @staticmethod
    def rwf(text):
        return int(text.replace(",", ""))

    def test_landing_uses_database_content(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Isombe with Sweet Potato")
        self.assertEqual(r.context["stats"]["meals"], Recipe.objects.filter(is_published=True).count())
        self.assertEqual(r.context["stats"]["ingredients"], Ingredient.objects.count())
        self.assertTrue(r.context["groups"])
        costs = [c["cost_pp"] for c in r.context["cheapest"]]
        self.assertEqual(costs, sorted(costs))

    def test_budget_example_arithmetic_is_consistent(self):
        ex = self.client.get("/").context["example"]
        full, saved, pay = (self.rwf(ex[k]) for k in ("full", "saved", "pay"))
        self.assertEqual(pay, full - saved)
        self.assertGreater(saved, 0)
        self.assertLess(saved, full)  # a realistic example never claims everything is already owned

    def test_unpublished_recipe_hidden_from_landing(self):
        # (The hero card is a static, labelled "Example", so check the database-driven parts of the page.)
        title = "Isombe with Sweet Potato"
        Recipe.objects.filter(title=title).update(is_published=False)
        r = self.client.get("/")
        shown = [x["title"] for g in r.context["groups"] for x in g["recipes"]]
        shown += [c["title"] for c in r.context["cheapest"]]
        shown += [x["title"] for x in r.context["landing_data"]["recipes"]]
        self.assertNotIn(title, shown)
        self.assertEqual(r.context["stats"]["meals"], Recipe.objects.filter(is_published=True).count())

    def test_landing_survives_empty_database(self):
        Recipe.objects.all().delete()
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.context["example"])
        self.assertEqual(r.context["groups"], [])

    def test_landing_cta_depends_on_login(self):
        self.assertEqual(self.client.get("/").context["cta_url"], "/register/")
        self.client.force_login(User.objects.get(username="demo"))
        self.assertEqual(self.client.get("/").context["cta_url"], "/app/")

    def test_all_pages_render_with_shared_theme(self):
        for url in ["/login/", "/register/"]:
            self.assertContains(self.client.get(url), "auth-split")
        self.client.force_login(User.objects.get(username="admin"))
        self.assertContains(self.client.get("/app/"), 'id="closest"')
        self.assertContains(self.client.get("/dashboard/"), "phero")
