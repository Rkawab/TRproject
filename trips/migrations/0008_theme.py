from django.db import migrations, models


INITIAL_THEMES = [
    ("onsen", "♨️", "温泉"),
    ("sea", "🌊", "海遊び"),
    ("shopping", "🛍️", "買物"),
    ("mountain", "⛰️", "登山/山歩き"),
    ("experience", "🧑‍🍳", "体験/見学"),
    ("gourmet", "🍽️", "グルメ"),
    ("friend", "🧑‍🤝‍🧑", "友人に会う"),
]


def seed_themes(apps, schema_editor):
    Theme = apps.get_model("trips", "Theme")
    for idx, (key, emoji, label) in enumerate(INITIAL_THEMES):
        Theme.objects.update_or_create(
            key=key,
            defaults={"emoji": emoji, "label": label, "order": idx},
        )


def assign_default_theme_to_existing_trips(apps, schema_editor):
    """既存Tripはとりあえず全件「温泉」を紐付ける（あとでユーザーが手動編集）"""
    Trip = apps.get_model("trips", "Trip")
    Theme = apps.get_model("trips", "Theme")
    onsen = Theme.objects.filter(key="onsen").first()
    if onsen is None:
        return
    for trip in Trip.objects.all():
        trip.themes.add(onsen)


def unseed_themes(apps, schema_editor):
    Theme = apps.get_model("trips", "Theme")
    Theme.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("trips", "0007_drop_packing_item_add_md_packing"),
    ]

    operations = [
        migrations.CreateModel(
            name="Theme",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.SlugField(max_length=30, unique=True, verbose_name="識別子")),
                ("emoji", models.CharField(blank=True, max_length=10, verbose_name="絵文字")),
                ("label", models.CharField(max_length=50, verbose_name="ラベル")),
                ("order", models.IntegerField(default=0, verbose_name="表示順")),
            ],
            options={
                "verbose_name": "テーマ",
                "verbose_name_plural": "テーマ",
                "db_table": "theme",
                "ordering": ["order", "id"],
            },
        ),
        migrations.AddField(
            model_name="trip",
            name="themes",
            field=models.ManyToManyField(
                blank=True, related_name="trips", to="trips.theme", verbose_name="テーマ"
            ),
        ),
        migrations.RunPython(seed_themes, unseed_themes),
        migrations.RunPython(assign_default_theme_to_existing_trips, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="trip",
            name="theme",
        ),
    ]
