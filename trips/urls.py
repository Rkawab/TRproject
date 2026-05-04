from django.urls import path
from . import views

app_name = "trips"

urlpatterns = [
    path("", views.trip_list, name="list"),
    path("new/", views.trip_create, name="create"),
    path("<int:pk>/", views.trip_detail, name="detail"),
    path("<int:pk>/edit/", views.trip_edit, name="edit"),
    path("<int:pk>/delete/", views.trip_delete, name="delete"),
    path("<int:pk>/packing/edit/", views.packing_edit, name="packing_edit"),
    path("<int:pk>/memory/edit/", views.memory_edit, name="memory_edit"),
    path("<int:pk>/plan/edit/", views.trip_plan_edit, name="plan_edit"),
    # AI 機能（POSTのみ・JSON応答）
    path("<int:pk>/ai/packing/", views.ai_packing, name="ai_packing"),
    path("<int:pk>/ai/questions/", views.ai_questions, name="ai_questions"),
    path("<int:pk>/ai/journal/", views.ai_journal, name="ai_journal"),
    path("<int:pk>/ai/titles/", views.ai_titles, name="ai_titles"),
]
