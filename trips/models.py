from django.conf import settings
from django.db import models


STATUS_CHOICES = [
    ("planning", "計画中"),
    ("preparing", "準備中"),
    ("ongoing", "旅行中"),
    ("organizing", "思い出整理中"),
    ("done", "完了"),
]


PACKING_CATEGORY_CHOICES = [
    ("belongings", "持ち物"),
    ("reservation", "予約確認"),
    ("purchase", "事前購入"),
    ("research", "調べること"),
    ("before_leaving", "家を出る前にやること"),
]


AI_KIND_CHOICES = [
    ("packing", "準備リスト提案"),
    ("question", "思い出整理の質問"),
    ("journal", "旅行記本文生成"),
    ("title", "タイトル案"),
]


class Trip(models.Model):
    """旅行本体"""
    name = models.CharField(max_length=200, verbose_name="旅行名")
    destination = models.CharField(max_length=200, blank=True, verbose_name="行き先")
    start_date = models.DateField(null=True, blank=True, verbose_name="開始日")
    end_date = models.DateField(null=True, blank=True, verbose_name="終了日")
    theme = models.CharField(max_length=100, blank=True, verbose_name="テーマ")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="planning", verbose_name="ステータス"
    )
    summary = models.TextField(blank=True, verbose_name="概要メモ")
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="trips",
        blank=True,
        verbose_name="参加者",
    )
    md_plan = models.TextField(blank=True, verbose_name="旅行計画（Markdown）")
    best_shot = models.ImageField(
        upload_to="best_shots/", blank=True, null=True, verbose_name="ベストショット"
    )
    best_shot_caption = models.CharField(
        max_length=200, blank=True, verbose_name="ベストショットの一言"
    )
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
    def status_label(self):
        return dict(STATUS_CHOICES).get(self.status, self.status)


class PackingItem(models.Model):
    """準備リスト（持ち物・予約確認・事前購入・調べること・家を出る前にやること）"""
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="packing_items")
    category = models.CharField(
        max_length=20, choices=PACKING_CATEGORY_CHOICES, default="belongings",
        verbose_name="分類",
    )
    name = models.CharField(max_length=200, verbose_name="項目名")
    is_done = models.BooleanField(default=False, verbose_name="完了")
    note = models.CharField(max_length=200, blank=True, verbose_name="備考")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "packing_item"
        ordering = ["category", "is_done", "id"]

    def __str__(self):
        return f"{self.get_category_display()}: {self.name}"


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
