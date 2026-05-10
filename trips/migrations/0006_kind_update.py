from django.db import migrations


# (id, emoji, label, order)
# id が None の行は新規作成（自動採番）
KIND_UPDATES = [
    (1,  "🚶",       "徒歩移動",  1),
    (2,  "🚃",       "電車バス",  2),
    (3,  "🚗",       "車",       3),
    (4,  "✈️",      "飛行機",   4),
    (None, "🏨",     "宿泊",     5),
    (17, "🏠",       "帰宅",     6),
    (15, "🎒",       "準備",     7),
    (7,  "🍽️",     "外食",     8),
    (9,  "🍙",       "軽食",     9),
    (None, "☕",      "カフェ",   10),
    (14, "🛍️",     "買物",     11),
    (None, "🖼️",   "絶景",     12),
    (None, "🏮",     "催事",     13),
    (None, "🎬",     "映画",     14),
    (12, "🚶‍♀️", "街歩き",   15),
    (None, "🌳",     "自然",     16),
    (None, "⛰️",    "登山",     17),
    (10, "🌊",       "海遊び",   18),
    (11, "🧑‍🍳", "体験",     19),
    (None, "♨️",    "温泉",     20),
    (13, "💤",       "休息",     21),
    (5,  "🧑‍🤝‍🧑", "合流", 22),
    (None, "📝",     "その他",   23),
]

# 削除対象ID（既存だが新リストに含まれないもの）
DELETE_IDS = [6, 8, 16]


def apply_updates(apps, schema_editor):
    Kind = apps.get_model("trips", "Kind")

    # unique_together (emoji, label) 衝突を避けるため、まず対象行の値を一旦退避する
    # 既存行は emoji/label を一意なダミーへ書き換え、その後で本来の値を設定する
    update_targets = [(kid, e, l, o) for (kid, e, l, o) in KIND_UPDATES if kid is not None]
    existing_ids = [kid for (kid, _, _, _) in update_targets] + DELETE_IDS

    # ダミー値で逃がす
    for i, kid in enumerate(existing_ids):
        Kind.objects.filter(pk=kid).update(emoji=f"_t{i}", label=f"_tmp_{kid}")

    # 削除
    Kind.objects.filter(pk__in=DELETE_IDS).delete()

    # 既存IDを更新
    for (kid, emoji, label, order) in update_targets:
        Kind.objects.filter(pk=kid).update(emoji=emoji, label=label, order=order)

    # 新規行を作成（指定IDなし＝自動採番）
    for (kid, emoji, label, order) in KIND_UPDATES:
        if kid is None:
            Kind.objects.update_or_create(
                emoji=emoji, label=label,
                defaults={"order": order},
            )


def reverse_noop(apps, schema_editor):
    # 元の状態に厳密には戻せないため何もしない
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("trips", "0005_kind"),
    ]

    operations = [
        migrations.RunPython(apply_updates, reverse_noop),
    ]
