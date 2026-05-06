from django.db import migrations, models


INITIAL_KINDS = [
    ("🚶", "移動"),
    ("🚃", "移動"),
    ("🚗", "移動"),
    ("✈️", "移動"),
    ("🚗", "送迎"),
    ("⛑️", "移動"),
    ("🍽️", "食事"),
    ("🍻", "食事"),
    ("🍙", "食事"),
    ("🤿", "海に入る"),
    ("🏄‍♀️", "体験"),
    ("🚶", "散歩"),
    ("💤", "休憩"),
    ("🛍️", "休憩"),
    ("⛑️", "準備"),
    ("⛑️", "手続き"),
    ("🏠", "到着"),
]


def seed_kinds(apps, schema_editor):
    Kind = apps.get_model("trips", "Kind")
    for idx, (emoji, label) in enumerate(INITIAL_KINDS):
        Kind.objects.get_or_create(
            emoji=emoji, label=label,
            defaults={"order": idx},
        )


def unseed_kinds(apps, schema_editor):
    Kind = apps.get_model("trips", "Kind")
    Kind.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("trips", "0004_trip_users"),
    ]

    operations = [
        migrations.CreateModel(
            name="Kind",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("emoji", models.CharField(blank=True, max_length=10, verbose_name="絵文字")),
                ("label", models.CharField(max_length=50, verbose_name="ラベル")),
                ("order", models.IntegerField(default=0, verbose_name="表示順")),
            ],
            options={
                "verbose_name": "種別",
                "verbose_name_plural": "種別",
                "db_table": "kind",
                "ordering": ["order", "id"],
                "unique_together": {("emoji", "label")},
            },
        ),
        migrations.RunPython(seed_kinds, unseed_kinds),
    ]
