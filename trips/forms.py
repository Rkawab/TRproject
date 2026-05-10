from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory

from .models import (
    MemoryEntry,
    MemoryNote,
    Theme,
    Trip,
)


User = get_user_model()


class UserChoiceField(forms.ModelMultipleChoiceField):
    """参加者選択用。username だけを表示する。"""
    def label_from_instance(self, obj):
        return obj.username


class ThemeChoiceField(forms.ModelMultipleChoiceField):
    """テーマ選択用。絵文字+ラベル表示。"""
    def label_from_instance(self, obj):
        return f"{obj.emoji}{obj.label}"


class TripShioriForm(forms.ModelForm):
    """旅のしおり（旅行前情報）: 基本情報 + 旅行計画"""

    users = UserChoiceField(
        queryset=User.objects.filter(is_superuser=False, is_active=True).order_by("username"),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        required=True,
        label="参加者",
    )

    themes = ThemeChoiceField(
        queryset=Theme.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        required=True,
        label="テーマ",
    )

    class Meta:
        model = Trip
        fields = [
            "name", "destination", "start_date", "end_date",
            "themes", "is_cancelled", "summary", "md_plan", "md_packing", "users",
        ]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "例: 2026年春の京都旅行",
            }),
            "destination": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "例: 京都市・嵐山",
            }),
            "start_date": forms.DateInput(attrs={
                "class": "form-control", "type": "date",
            }),
            "end_date": forms.DateInput(attrs={
                "class": "form-control", "type": "date",
            }),
            "is_cancelled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "summary": forms.Textarea(attrs={
                "class": "form-control", "rows": 3,
                "placeholder": "自由メモ",
            }),
            "md_plan": forms.Textarea(attrs={
                "class": "form-control font-monospace",
                "rows": 20,
                "placeholder": "# 旅行計画\n\n## 1日目\n- 10:00 那覇空港着\n- ...",
            }),
            "md_packing": forms.Textarea(attrs={
                "class": "form-control font-monospace",
                "rows": 14,
                "placeholder": "## 🎒 持ち物\n- [ ] パスポート\n- [x] 充電器\n\n## ✅ 予約確認\n- [ ] 航空券",
            }),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "終了日は開始日以降にしてください")
        return cleaned


class TripAlbumForm(forms.ModelForm):
    """旅のアルバム（旅行後情報）: ベストショット部分"""
    class Meta:
        model = Trip
        fields = ["best_shot", "best_shot_caption"]
        widgets = {
            "best_shot": forms.ClearableFileInput(attrs={
                "class": "form-control",
                "accept": "image/*",
            }),
            "best_shot_caption": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "例: 真栄田岬で撮った夕日",
                "maxlength": 200,
            }),
        }


MemoryNoteFormSet = inlineformset_factory(
    Trip, MemoryNote,
    fields=["body"],
    widgets={
        "body": forms.Textarea(attrs={
            "class": "form-control",
            "rows": 2,
            "placeholder": "例: 奥武島のタコス最高だった / 次は那覇も1泊したい",
        }),
    },
    extra=3,
    can_delete=True,
)


class MemoryJournalForm(forms.ModelForm):
    """旅行記本文のみのフォーム"""
    class Meta:
        model = MemoryEntry
        fields = ["journal"]
        widgets = {
            "journal": forms.Textarea(attrs={
                "class": "form-control", "rows": 12,
                "placeholder": "AIで生成、または自分で書き起こしたい本文",
            }),
        }
