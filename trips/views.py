import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

User = get_user_model()

from .ai_service import (
    AIServiceError,
    generate_journal,
    generate_questions,
    suggest_packing,
    suggest_titles,
)
from .forms import (
    MemoryJournalForm,
    MemoryNoteFormSet,
    PackingItemFormSet,
    TripAlbumForm,
    TripShioriForm,
)
from .models import (
    PACKING_CATEGORY_CHOICES,
    STATUS_CHOICES,
    MemoryEntry,
    PackingItem,
    Trip,
)

logger = logging.getLogger(__name__)


@login_required
def trip_list(request):
    trips = Trip.objects.all().prefetch_related("users")

    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    user_id = request.GET.get("user", "")

    if query:
        trips = trips.filter(Q(name__icontains=query) | Q(destination__icontains=query))
    if status:
        trips = trips.filter(status=status)
    if user_id:
        trips = trips.filter(users__id=user_id).distinct()

    user_choices = User.objects.filter(is_superuser=False, is_active=True).order_by("username")

    return render(request, "trips/list.html", {
        "trips": trips,
        "query": query,
        "status": status,
        "status_choices": STATUS_CHOICES,
        "user_choices": user_choices,
        "selected_user": user_id,
    })


@login_required
def trip_create(request):
    """新規作成も「旅のしおり」フォーム（基本情報 + 計画 + 準備リスト）で行う。"""
    if request.method == "POST":
        form = TripShioriForm(request.POST)
        # formset は保存前は instance=Trip() で受けて検証する
        packing_formset = PackingItemFormSet(request.POST, instance=Trip())
        if form.is_valid() and packing_formset.is_valid():
            with transaction.atomic():
                trip = form.save()
                packing_formset.instance = trip
                packing_formset.save()
            messages.success(request, f"「{trip.name}」を登録しました。")
            return redirect("trips:detail", pk=trip.pk)
        messages.error(request, "入力内容にエラーがあります。赤字部分をご確認ください。")
    else:
        initial = {}
        if request.user.is_authenticated and not request.user.is_superuser:
            initial["users"] = [request.user.pk]
        form = TripShioriForm(initial=initial)
        packing_formset = PackingItemFormSet(instance=Trip())
    return render(request, "trips/shiori_form.html", {
        "form": form,
        "packing_formset": packing_formset,
        "title": "旅行を新規作成",
    })


@login_required
def trip_detail(request, pk):
    trip = get_object_or_404(
        Trip.objects.prefetch_related("packing_items", "memory_notes", "users"),
        pk=pk,
    )
    memory = getattr(trip, "memory", None)

    packing_by_cat = {}
    for item in trip.packing_items.all():
        packing_by_cat.setdefault(item.category, []).append(item)
    packing_groups = []
    for code, label in PACKING_CATEGORY_CHOICES:
        if code in packing_by_cat:
            packing_groups.append((label, packing_by_cat[code]))

    memory_notes = list(trip.memory_notes.all())

    return render(request, "trips/detail.html", {
        "trip": trip,
        "memory": memory,
        "packing_groups": packing_groups,
        "memory_notes": memory_notes,
    })


@login_required
def trip_delete(request, pk):
    trip = get_object_or_404(Trip, pk=pk)
    if request.method == "POST":
        name = trip.name
        trip.delete()
        messages.success(request, f"「{name}」を削除しました。")
        return redirect("trips:list")
    return render(request, "trips/confirm_delete.html", {"trip": trip})


@login_required
def shiori_edit(request, pk):
    """旅のしおり（旅行前情報）: 基本情報 + 旅行計画 + 準備リストを1画面で編集。"""
    trip = get_object_or_404(Trip, pk=pk)
    if request.method == "POST":
        form = TripShioriForm(request.POST, instance=trip)
        packing_formset = PackingItemFormSet(request.POST, instance=trip)
        if form.is_valid() and packing_formset.is_valid():
            with transaction.atomic():
                form.save()
                packing_formset.save()
            messages.success(request, "旅のしおりを保存しました。")
            return redirect("trips:detail", pk=trip.pk)
        messages.error(request, "入力内容にエラーがあります。")
    else:
        form = TripShioriForm(instance=trip)
        packing_formset = PackingItemFormSet(instance=trip)
    return render(request, "trips/shiori_form.html", {
        "form": form,
        "packing_formset": packing_formset,
        "trip": trip,
        "title": "旅のしおりを編集",
    })


@login_required
def album_edit(request, pk):
    """旅のアルバム（旅行後情報）: ベストショット + 思い出メモ + 旅行記本文を1画面で編集。"""
    trip = get_object_or_404(Trip, pk=pk)
    memory, _ = MemoryEntry.objects.get_or_create(trip=trip)

    if request.method == "POST":
        form = TripAlbumForm(request.POST, request.FILES, instance=trip)
        memory_formset = MemoryNoteFormSet(request.POST, instance=trip)
        journal_form = MemoryJournalForm(request.POST, instance=memory)
        if form.is_valid() and memory_formset.is_valid() and journal_form.is_valid():
            with transaction.atomic():
                form.save()
                memory_formset.save()
                journal_form.save()
            messages.success(request, "旅のアルバムを保存しました。")
            return redirect("trips:detail", pk=trip.pk)
        messages.error(request, "入力内容にエラーがあります。")
    else:
        form = TripAlbumForm(instance=trip)
        memory_formset = MemoryNoteFormSet(instance=trip)
        journal_form = MemoryJournalForm(instance=memory)

    return render(request, "trips/album_form.html", {
        "form": form,
        "memory_formset": memory_formset,
        "journal_form": journal_form,
        "trip": trip,
        "title": "旅のアルバムを編集",
    })


# ----- AI エンドポイント（POSTのみ・ボタン押下時の手動実行） -----

@login_required
def ai_packing(request, pk):
    if request.method != "POST":
        return JsonResponse({"error": "POSTのみ対応しています。"}, status=405)
    trip = get_object_or_404(Trip, pk=pk)
    try:
        suggestions = suggest_packing(trip)
    except AIServiceError as e:
        return JsonResponse({"error": str(e)}, status=500)
    except Exception as e:
        logger.exception("ai_packing 予期せぬエラー")
        return JsonResponse({"error": f"予期せぬエラー: {e}"}, status=500)

    created = []
    for s in suggestions:
        item = PackingItem.objects.create(
            trip=trip,
            category=s["category"],
            name=s["name"],
            note=s.get("note", ""),
        )
        created.append({
            "id": item.id,
            "category": item.category,
            "category_label": item.get_category_display(),
            "name": item.name,
            "note": item.note,
        })
    return JsonResponse({"created": created, "count": len(created)})


@login_required
def ai_questions(request, pk):
    if request.method != "POST":
        return JsonResponse({"error": "POSTのみ対応しています。"}, status=405)
    trip = get_object_or_404(Trip, pk=pk)
    try:
        questions = generate_questions(trip)
    except AIServiceError as e:
        return JsonResponse({"error": str(e)}, status=500)
    except Exception as e:
        logger.exception("ai_questions 予期せぬエラー")
        return JsonResponse({"error": f"予期せぬエラー: {e}"}, status=500)
    return JsonResponse({"questions": questions})


@login_required
def ai_journal(request, pk):
    if request.method != "POST":
        return JsonResponse({"error": "POSTのみ対応しています。"}, status=405)
    trip = get_object_or_404(Trip, pk=pk)
    try:
        journal = generate_journal(trip)
    except AIServiceError as e:
        return JsonResponse({"error": str(e)}, status=500)
    except Exception as e:
        logger.exception("ai_journal 予期せぬエラー")
        return JsonResponse({"error": f"予期せぬエラー: {e}"}, status=500)

    memory, _ = MemoryEntry.objects.get_or_create(trip=trip)
    memory.journal = journal
    memory.journal_generated_at = timezone.now()
    memory.save()

    return JsonResponse({
        "journal": journal,
        "redirect": reverse("trips:album_edit", args=[trip.pk]),
    })


@login_required
def ai_titles(request, pk):
    if request.method != "POST":
        return JsonResponse({"error": "POSTのみ対応しています。"}, status=405)
    trip = get_object_or_404(Trip, pk=pk)
    try:
        titles = suggest_titles(trip)
    except AIServiceError as e:
        return JsonResponse({"error": str(e)}, status=500)
    except Exception as e:
        logger.exception("ai_titles 予期せぬエラー")
        return JsonResponse({"error": f"予期せぬエラー: {e}"}, status=500)
    return JsonResponse({"titles": titles})
