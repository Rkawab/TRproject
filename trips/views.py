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
    generate_shiori,
    generate_slug,
    suggest_titles,
)
from .forms import (
    MemoryJournalForm,
    MemoryNoteFormSet,
    TripAlbumForm,
    TripShioriForm,
)
from .models import (
    STATUS_CHOICES,
    Kind,
    MemoryEntry,
    Theme,
    Trip,
)


def _kind_choices():
    """ビジュアル編集の <select> 用に種別を並べたリスト。"""
    return [k.display for k in Kind.objects.all()]

logger = logging.getLogger(__name__)


def _generate_unique_slug(trip: Trip) -> str:
    """AIでスラグを生成し、重複時は末尾に -2, -3 ... を付けて一意にする。"""
    base_slug = generate_slug(
        trip.name,
        destination=trip.destination or "",
        start_date=trip.start_date,
        fallback_pk=trip.pk,
    )
    slug = base_slug
    counter = 2
    while Trip.objects.filter(slug=slug).exclude(pk=trip.pk).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


@login_required
def trip_list(request):
    trips = Trip.objects.all().prefetch_related("users", "themes")

    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    user_id = request.GET.get("user", "")

    if query:
        trips = trips.filter(Q(name__icontains=query) | Q(destination__icontains=query))
    if status:
        today = timezone.localdate()
        if status == "cancelled":
            trips = trips.filter(is_cancelled=True)
        elif status == "preparing":
            trips = trips.filter(is_cancelled=False).filter(
                Q(start_date__isnull=True) | Q(start_date__gt=today)
            )
        elif status == "ongoing":
            trips = trips.filter(is_cancelled=False, start_date__lte=today).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=today)
            )
        elif status == "done":
            trips = trips.filter(is_cancelled=False, end_date__lt=today)
    if user_id:
        trips = trips.filter(users__id=user_id).distinct()

    user_choices = User.objects.filter(is_superuser=False, is_active=True).exclude(username__icontains="ゲスト").order_by("username")

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
        if form.is_valid():
            with transaction.atomic():
                trip = form.save()
                try:
                    trip.slug = _generate_unique_slug(trip)
                except Exception:
                    trip.slug = f"trip-{trip.pk}"
                trip.save(update_fields=["slug"])
            messages.success(request, f"「{trip.name}」を登録しました。")
            return redirect("trips:detail", slug=trip.slug)
        messages.error(request, "入力内容にエラーがあります。赤字部分をご確認ください。")
    else:
        initial = {}
        if request.user.is_authenticated and not request.user.is_superuser:
            initial["users"] = [request.user.pk]
        form = TripShioriForm(initial=initial)
    return render(request, "trips/shiori_form.html", {
        "form": form,
        "title": "旅行を新規作成",
        "kind_choices": _kind_choices(),
    })


def trip_detail(request, slug):
    """旅行詳細はログイン不要で閲覧できる。編集・削除リンクや参加者名はテンプレ側で制御。"""
    trip = get_object_or_404(
        Trip.objects.prefetch_related("memory_notes", "users", "themes"),
        slug=slug,
    )
    memory = getattr(trip, "memory", None)
    memory_notes = list(trip.memory_notes.all())

    return render(request, "trips/detail.html", {
        "trip": trip,
        "memory": memory,
        "memory_notes": memory_notes,
    })


@login_required
def trip_delete(request, slug):
    trip = get_object_or_404(Trip, slug=slug)
    if request.method == "POST":
        name = trip.name
        trip.delete()
        messages.success(request, f"「{name}」を削除しました。")
        return redirect("trips:list")
    return render(request, "trips/confirm_delete.html", {"trip": trip})


@login_required
def shiori_edit(request, slug):
    """旅のしおり（旅行前情報）: 基本情報 + 旅行計画 + 準備リストを1画面で編集。"""
    trip = get_object_or_404(Trip, slug=slug)
    if request.method == "POST":
        form = TripShioriForm(request.POST, instance=trip)
        if form.is_valid():
            with transaction.atomic():
                form.save()
            messages.success(request, "旅のしおりを保存しました。")
            return redirect("trips:detail", slug=trip.slug)
        messages.error(request, "入力内容にエラーがあります。")
    else:
        form = TripShioriForm(instance=trip)
    return render(request, "trips/shiori_form.html", {
        "form": form,
        "trip": trip,
        "title": "旅のしおりを編集",
        "kind_choices": _kind_choices(),
    })


@login_required
def album_edit(request, slug):
    """旅のアルバム（旅行後情報）: ベストショット + 思い出メモ + 旅行記本文を1画面で編集。"""
    trip = get_object_or_404(Trip, slug=slug)
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
            return redirect("trips:detail", slug=trip.slug)
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
def ai_shiori(request, slug=None):
    """しおり編集／新規作成画面用に、旅行計画(md_plan)と準備リスト(md_packing)を一括生成。

    フォーム上の現在値（旅行名・行き先・日付・テーマ・概要）をリクエストから受け取る。
    レスポンスはフォームに反映するだけで、DBには保存しない（ユーザーが「保存」を押した時点で確定する）。
    旅行計画・準備リストとも、フォーム上に既に内容があれば「修正モード」で部分修正する。
    """
    if request.method != "POST":
        return JsonResponse({"error": "POSTのみ対応しています。"}, status=405)

    targets = [t for t in request.POST.getlist("targets") if t in ("plan", "packing")]
    if not targets:
        return JsonResponse({"error": "生成対象（旅行計画 / 準備リスト）を1つ以上選択してください。"}, status=400)

    instructions = request.POST.get("instructions", "").strip()
    current_md_plan = request.POST.get("current_md_plan", "")
    current_md_packing = request.POST.get("current_md_packing", "")

    theme_keys = [t for t in request.POST.getlist("themes") if t]
    theme_labels = []
    if theme_keys:
        theme_labels = [t.display for t in Theme.objects.filter(pk__in=theme_keys)]

    trip_meta = {
        "name": request.POST.get("name", "").strip(),
        "destination": request.POST.get("destination", "").strip(),
        "start_date": request.POST.get("start_date", "").strip(),
        "end_date": request.POST.get("end_date", "").strip(),
        "theme": "、".join(theme_labels),
        "summary": request.POST.get("summary", "").strip(),
    }
    if trip_meta["start_date"] and trip_meta["end_date"]:
        try:
            from datetime import date
            sd = date.fromisoformat(trip_meta["start_date"])
            ed = date.fromisoformat(trip_meta["end_date"])
            diff = (ed - sd).days + 1
            if 1 <= diff <= 60:
                trip_meta["duration_days"] = diff
        except ValueError:
            pass

    trip = None
    if slug is not None:
        trip = get_object_or_404(Trip, slug=slug)
        if not trip_meta["name"]:
            trip_meta["name"] = trip.name
        if not trip_meta["destination"]:
            trip_meta["destination"] = trip.destination
        if not trip_meta["theme"]:
            trip_meta["theme"] = "、".join(t.display for t in trip.themes.all())
        if not trip_meta["summary"]:
            trip_meta["summary"] = trip.summary
        # フォーム上の現在値が空なら、DBの現在値をフォールバックとして使う
        if not current_md_packing.strip() and trip.md_packing:
            current_md_packing = trip.md_packing

    kind_choices = [k.display for k in Kind.objects.all()]
    logger.info(
        "ai_shiori: targets=%s plan_refine=%s packing_refine=%s",
        targets,
        bool(current_md_plan.strip()),
        bool(current_md_packing.strip()),
    )

    try:
        result = generate_shiori(
            targets=targets,
            instructions=instructions,
            trip_meta=trip_meta,
            kind_choices=kind_choices,
            trip=trip,
            current_md_plan=current_md_plan,
            current_md_packing=current_md_packing,
        )
    except AIServiceError as e:
        return JsonResponse({"error": str(e)}, status=500)
    except Exception as e:
        logger.exception("ai_shiori 予期せぬエラー")
        return JsonResponse({"error": f"予期せぬエラー: {e}"}, status=500)

    return JsonResponse(result)


@login_required
def ai_questions(request, slug):
    if request.method != "POST":
        return JsonResponse({"error": "POSTのみ対応しています。"}, status=405)
    trip = get_object_or_404(Trip, slug=slug)
    try:
        questions = generate_questions(trip)
    except AIServiceError as e:
        return JsonResponse({"error": str(e)}, status=500)
    except Exception as e:
        logger.exception("ai_questions 予期せぬエラー")
        return JsonResponse({"error": f"予期せぬエラー: {e}"}, status=500)
    return JsonResponse({"questions": questions})


@login_required
def ai_journal(request, slug):
    if request.method != "POST":
        return JsonResponse({"error": "POSTのみ対応しています。"}, status=405)
    trip = get_object_or_404(Trip, slug=slug)
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
        "redirect": reverse("trips:album_edit", args=[trip.slug]),
    })


@login_required
def ai_titles(request, slug):
    if request.method != "POST":
        return JsonResponse({"error": "POSTのみ対応しています。"}, status=405)
    trip = get_object_or_404(Trip, slug=slug)
    try:
        titles = suggest_titles(trip)
    except AIServiceError as e:
        return JsonResponse({"error": str(e)}, status=500)
    except Exception as e:
        logger.exception("ai_titles 予期せぬエラー")
        return JsonResponse({"error": f"予期せぬエラー: {e}"}, status=500)
    return JsonResponse({"titles": titles})
