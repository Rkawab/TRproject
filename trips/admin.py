from django.contrib import admin

from .models import (
    Trip,
    TripDay,
    ItineraryItem,
    PackingItem,
    TravelMemo,
    MemoryEntry,
    AISuggestionLog,
)


class TripDayInline(admin.TabularInline):
    model = TripDay
    extra = 0


class ItineraryItemInline(admin.TabularInline):
    model = ItineraryItem
    extra = 0
    fields = ("date", "time", "title", "place", "reservation_number")


class PackingItemInline(admin.TabularInline):
    model = PackingItem
    extra = 0
    fields = ("category", "name", "is_done", "note")


class TravelMemoInline(admin.TabularInline):
    model = TravelMemo
    extra = 0
    fields = ("category", "body", "recorded_at")
    readonly_fields = ("recorded_at",)


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = (
        "name", "destination", "start_date", "end_date", "status", "created_at",
    )
    list_filter = ("status",)
    search_fields = ("name", "destination", "theme")
    inlines = [TripDayInline, ItineraryItemInline, PackingItemInline, TravelMemoInline]


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
