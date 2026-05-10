from django.contrib import admin

from .models import (
    Trip,
    MemoryEntry,
    MemoryNote,
    AISuggestionLog,
    Kind,
    Theme,
)


@admin.register(Kind)
class KindAdmin(admin.ModelAdmin):
    list_display = ("order", "emoji", "label")
    list_editable = ("emoji", "label")
    ordering = ("order", "id")
    search_fields = ("label",)


@admin.register(Theme)
class ThemeAdmin(admin.ModelAdmin):
    list_display = ("order", "key", "emoji", "label")
    list_editable = ("emoji", "label")
    ordering = ("order", "id")
    search_fields = ("key", "label")


class MemoryNoteInline(admin.TabularInline):
    model = MemoryNote
    extra = 0
    fields = ("body", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = (
        "name", "destination", "start_date", "end_date", "status", "created_at",
    )
    list_filter = ("status", "users", "themes")
    search_fields = ("name", "destination")
    fields = (
        "name", "destination", "start_date", "end_date",
        "themes", "status", "summary", "md_plan", "md_packing",
        "best_shot", "best_shot_caption", "users",
    )
    filter_horizontal = ("users", "themes")
    inlines = [MemoryNoteInline]


@admin.register(MemoryEntry)
class MemoryEntryAdmin(admin.ModelAdmin):
    list_display = ("trip", "journal_generated_at", "updated_at")
    search_fields = ("trip__name",)


@admin.register(AISuggestionLog)
class AISuggestionLogAdmin(admin.ModelAdmin):
    list_display = ("trip", "kind", "model", "created_at")
    list_filter = ("kind", "model")
    search_fields = ("trip__name",)
    readonly_fields = ("trip", "kind", "model", "prompt", "response", "created_at")
