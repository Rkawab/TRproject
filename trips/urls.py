from django.urls import path
from . import views

app_name = "trips"

urlpatterns = [
    path("", views.trip_list, name="list"),
    path("new/", views.trip_create, name="create"),
    path("<int:pk>/", views.trip_detail, name="detail"),
    path("<int:pk>/delete/", views.trip_delete, name="delete"),
    path("<int:pk>/shiori/edit/", views.shiori_edit, name="shiori_edit"),
    path("<int:pk>/album/edit/", views.album_edit, name="album_edit"),
    # AI 機能（POSTのみ・JSON応答）
    path("<int:pk>/ai/packing/", views.ai_packing, name="ai_packing"),
    path("<int:pk>/ai/questions/", views.ai_questions, name="ai_questions"),
    path("<int:pk>/ai/journal/", views.ai_journal, name="ai_journal"),
    path("<int:pk>/ai/titles/", views.ai_titles, name="ai_titles"),
]
