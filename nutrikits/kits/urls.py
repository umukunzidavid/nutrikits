from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    # pages
    path("", views.landing, name="landing"),
    path("app/", views.portal, name="portal"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("login/", auth_views.LoginView.as_view(template_name="kits/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", views.register, name="register"),
    # shared JSON API
    path("api/version/", views.api_version),
    path("api/meta/", views.api_meta),
    path("api/ingredients/", views.api_ingredients),
    path("api/recipes/", views.api_recipes),
    path("api/recipes/<int:pk>/", views.api_recipe_detail),
    path("api/pantry/", views.api_pantry),
    path("api/pantry/<int:ingredient_id>/", views.api_pantry_delete),
    path("api/profile/", views.api_profile),
    path("api/orders/", views.api_orders),
    # admin dashboard API (staff only)
    path("api/admin/recipes/", views.api_admin_recipes),
    path("api/admin/recipes/<int:pk>/", views.api_admin_recipe_detail),
    path("api/admin/recipes/<int:pk>/images/", views.api_admin_recipe_images),
    path("api/admin/recipes/<int:pk>/images/<int:image_id>/", views.api_admin_recipe_image_detail),
    path("api/admin/recipes/<int:pk>/video/", views.api_admin_recipe_video),
    path("api/admin/ingredients/", views.api_admin_ingredients),
    path("api/admin/orders/", views.api_admin_orders),
    path("api/admin/stats/", views.api_admin_stats),
]
