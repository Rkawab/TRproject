from django.db import migrations, models


def fill_fallback_slugs(apps, schema_editor):
    """既存の Trip に trip-{pk} のフォールバックスラグを付与する。"""
    Trip = apps.get_model("trips", "Trip")
    for trip in Trip.objects.filter(slug=""):
        trip.slug = f"trip-{trip.pk}"
        trip.save(update_fields=["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("trips", "0010_replace_status_with_is_cancelled"),
    ]

    operations = [
        # db_index=False: unique=True が unique インデックスを作るので、
        # SlugField デフォルトの db_index による余分なインデックス（_like 含む）は作らせない
        migrations.AddField(
            model_name="trip",
            name="slug",
            field=models.SlugField(
                blank=True, default="", max_length=100, db_index=False, verbose_name="スラグ"
            ),
            preserve_default=False,
        ),
        migrations.RunPython(fill_fallback_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="trip",
            name="slug",
            field=models.SlugField(
                max_length=100, unique=True, db_index=False, verbose_name="スラグ"
            ),
        ),
    ]
