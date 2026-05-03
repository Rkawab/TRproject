from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("trips/", include("trips.urls")),
    path("analytics/", include("analytics.urls")),
    path("", views.home, name="home"),
]
