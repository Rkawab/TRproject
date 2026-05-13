from django.urls import path
from . import views

app_name = "trips"

urlpatterns = [
    path("", views.trip_list, name="list"),
    path("new/", views.trip_create, name="create"),
    path("<slug:slug>/", views.trip_detail, name="detail"),
    path("<slug:slug>/delete/", views.trip_delete, name="delete"),
    path("<slug:slug>/shiori/edit/", views.shiori_edit, name="shiori_edit"),
    path("<slug:slug>/album/edit/", views.album_edit, name="album_edit"),
    # AI 機能（POSTのみ・JSON応答）
    # しおり一括生成: 旅行計画(md_plan) と準備リスト(packing) を、ユーザー指示から生成
    path("ai/shiori/", views.ai_shiori, name="ai_shiori_new"),
    path("<slug:slug>/ai/shiori/", views.ai_shiori, name="ai_shiori"),
    # アルバム編集画面で使う AI（旅行記・タイトル案・振り返り質問）
    path("<slug:slug>/ai/questions/", views.ai_questions, name="ai_questions"),
    path("<slug:slug>/ai/journal/", views.ai_journal, name="ai_journal"),
    path("<slug:slug>/ai/titles/", views.ai_titles, name="ai_titles"),
]
