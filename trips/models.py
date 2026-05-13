from django.conf import settings
from django.db import models
from django.utils import timezone


STATUS_CHOICES = [
    ("preparing", "準備中"),
    ("ongoing", "旅行中"),
    ("done", "完了"),
    ("cancelled", "中止"),
]


AI_KIND_CHOICES = [
    ("packing", "準備リスト提案"),
    ("question", "思い出整理の質問"),
    ("journal", "旅行記本文生成"),
    ("title", "タイトル案"),
    ("shiori", "しおり一括生成"),
]


class Trip(models.Model):
    """旅行本体"""
    name = models.CharField(max_length=200, verbose_name="旅行名")
    destination = models.CharField(max_length=200, blank=True, verbose_name="行き先")
    start_date = models.DateField(null=True, blank=True, verbose_name="開始日")
    end_date = models.DateField(null=True, blank=True, verbose_name="終了日")
    themes = models.ManyToManyField(
        "Theme",
        related_name="trips",
        blank=True,
        verbose_name="テーマ",
    )
    is_cancelled = models.BooleanField(default=False, verbose_name="中止")
    summary = models.TextField(blank=True, verbose_name="概要メモ")
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="trips",
        blank=True,
        verbose_name="参加者",
    )
    md_plan = models.TextField(blank=True, verbose_name="旅行計画（Markdown）")
    md_packing = models.TextField(blank=True, verbose_name="準備リスト（Markdown）")
    best_shot = models.ImageField(
        upload_to="best_shots/", blank=True, null=True, verbose_name="ベストショット"
    )
    best_shot_caption = models.CharField(
        max_length=200, blank=True, verbose_name="ベストショットの一言"
    )
    slug = models.SlugField(max_length=100, unique=True, blank=True, db_index=False, verbose_name="スラグ")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "trip"
        ordering = ["-start_date", "-created_at"]

    def __str__(self):
        return self.name

    @property
    def duration_days(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return None

    @property
    def status(self):
        if self.is_cancelled:
            return "cancelled"
        today = timezone.localdate()
        if self.start_date is None:
            return "preparing"
        if today < self.start_date:
            return "preparing"
        if self.end_date is None or today <= self.end_date:
            return "ongoing"
        return "done"

    @property
    def status_label(self):
        return dict(STATUS_CHOICES).get(self.status, self.status)


class Kind(models.Model):
    """行程表の「種別」マスタ。管理画面から自由に追加削除できる。"""
    emoji = models.CharField(max_length=10, blank=True, verbose_name="絵文字")
    label = models.CharField(max_length=50, verbose_name="ラベル")
    order = models.IntegerField(default=0, verbose_name="表示順")

    class Meta:
        db_table = "kind"
        ordering = ["order", "id"]
        unique_together = [("emoji", "label")]
        verbose_name = "種別"
        verbose_name_plural = "種別"

    def __str__(self):
        return f"{self.emoji}{self.label}"

    @property
    def display(self):
        return f"{self.emoji}{self.label}"


class Theme(models.Model):
    """旅行テーマのマスタ。Trip と多対多で紐付ける。"""
    key = models.SlugField(max_length=30, unique=True, verbose_name="識別子")
    emoji = models.CharField(max_length=10, blank=True, verbose_name="絵文字")
    label = models.CharField(max_length=50, verbose_name="ラベル")
    order = models.IntegerField(default=0, verbose_name="表示順")

    class Meta:
        db_table = "theme"
        ordering = ["order", "id"]
        verbose_name = "テーマ"
        verbose_name_plural = "テーマ"

    def __str__(self):
        return f"{self.emoji}{self.label}"

    @property
    def display(self):
        return f"{self.emoji}{self.label}"


class MemoryEntry(models.Model):
    """旅行後の思い出（1旅行につき1件）— journal のみ保持"""
    trip = models.OneToOneField(Trip, on_delete=models.CASCADE, related_name="memory")
    journal = models.TextField(blank=True, verbose_name="AI生成の旅行記本文")
    journal_generated_at = models.DateTimeField(
        null=True, blank=True, verbose_name="旅行記生成日時"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "memory_entry"

    def __str__(self):
        return f"思い出: {self.trip.name}"


class MemoryNote(models.Model):
    """思い出メモ（箇条書きで自由に追加）"""
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="memory_notes")
    body = models.TextField(verbose_name="メモ")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "memory_note"
        ordering = ["created_at"]

    def __str__(self):
        return self.body[:50]


class AISuggestionLog(models.Model):
    """AI 提案の履歴。費用や精度確認のために残す。"""
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="ai_logs")
    kind = models.CharField(max_length=20, choices=AI_KIND_CHOICES, verbose_name="種別")
    model = models.CharField(max_length=50, verbose_name="使用モデル")
    prompt = models.TextField(verbose_name="プロンプト")
    response = models.TextField(verbose_name="応答")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_suggestion_log"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} ({self.created_at:%Y-%m-%d %H:%M})"
