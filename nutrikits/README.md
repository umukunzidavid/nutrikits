# NutriKits Rwanda

Web platform that matches a user's kitchen pantry with doctor-recommended meal kits, then
generates a shopping list of **only the missing ingredients**, priced in RWF with Kigali delivery zones.

**Stack:** HTML5 · CSS3 · modular vanilla JavaScript (ES modules) · **Django + SQLite** (no Firebase).

## Run it

```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed          # Rwandan ingredients, health focuses, zones, 12 recipes, demo users
python manage.py runserver
```

Open http://127.0.0.1:8000

| Role | Username | Password | Where |
|---|---|---|---|
| Customer | `demo` | `demo12345` | `/app/` (user portal; `/` is the public landing page) |
| Admin | `admin` | `admin12345` | `/dashboard/` (publishing) and `/admin/` (Django admin) |

Change these passwords before any real deployment.

## Features

**One design across every page** (landing, sign in / register, user portal, admin dashboard): green gradient banners, pastel panels, pill buttons, hover lifts, scroll-reveal and count-up animations, an animated modal, expandable accordions, and sliding card rows. On phones the portal and dashboard tabs become a bottom tab bar.

**Landing page (`/`)**: sticky nav with a "Meals for you" dropdown, auto-sliding "how it works" carousel, animated stats, a clickable health-focus meal finder, sliding meal rows by time of day, a budget section, comparison table, safety guide (not medical advice, doctor's advice first, allergies, extra care groups) and an FAQ accordion. Meals, prices and counts come from the database. Sign-up requires ticking a safety acknowledgement, and reminders appear inside the app.

**User portal (`/app/`)**
- Filter meals by clinical focus (diabetes, hypertension, anaemia, maternal, child, weight, heart), meal type, search, sort
- Pantry manager: the match % and cost update instantly from what you have at home
- Recipe modal: servings stepper, per-ingredient "in pantry / need X" list, savings, delivery zone, MoMo / Airtel / cash
- Health profile: saved focuses, ingredients to avoid (those recipes are hidden), delivery zone
- Order history with live status

**Admin dashboard (`/dashboard/`, staff only)**
- Publish / edit / unpublish / delete recipes with health tags, doctor's note, and ingredient rows
- Normalised ingredient catalogue (Kinyarwanda names, RWF price per unit)
- Orders list with status updates, plus revenue / recipe / customer stats

**Photos & demo videos**
- In the dashboard recipe form: up to 8 photos per recipe (JPG/PNG/WebP, 5 MB each; the first is the cover), and one demo video
- Video can be an uploaded MP4/WebM (max 50 MB) **or** a YouTube/Vimeo link (recommended for long videos and slow connections)
- Users see the cover on meal cards, a clickable gallery in the recipe pop-up, and a "Watch how to cook it" player
- Uploads are validated server-side (real image/video content, size, type, link host) and files are deleted when removed
- Files are stored in `media/`, served by Django only while `DEBUG=True`. For production serve `/media/` with your web server
  or move to object storage (e.g. S3 via `django-storages`). Uploaded `media/` is not included in the zip.

**Live sync (replaces Firestore listeners):** the portal polls `/api/version/` every 8 seconds and reloads the
menu with a toast when an admin publishes or edits a recipe. For true push, add Django Channels (WebSockets).

## Project layout

```
config/                  Django settings & root urls
kits/models.py           HealthFocus, Ingredient, Recipe, RecipeIngredient, DeliveryZone, Profile, PantryItem, Order
kits/services.py         pantry-vs-recipe matching + cost engine
kits/views.py            pages + JSON API (user and staff endpoints)
kits/templates/kits/     base, login, register, portal, dashboard
kits/static/kits/        css/{app,landing}.css · js/{api,ui,carousel,landing,portal,dashboard}.js
kits/management/commands/seed.py
kits/tests.py            35 tests (python manage.py test)
```

## Notes
- Fonts (Fraunces, Inter) load from Google Fonts, so you need internet for the exact look. Offline, the browser uses fallback fonts.
- Tests: `python manage.py test` (35 tests).
- Payments are recorded as the chosen method only. No MoMo/Airtel API is wired in; integrate a gateway before taking real money.
- Ingredient prices and delivery fees are illustrative seed data; edit them in the dashboard.
- Recipes and health notes are sample content, not medical advice. Have them reviewed by a qualified clinician or dietitian before launch.
- Production: set `DEBUG=False`, a real `SECRET_KEY`, `ALLOWED_HOSTS`, and move to PostgreSQL if needed (only `DATABASES` changes).
