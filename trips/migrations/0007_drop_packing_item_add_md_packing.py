from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trips", "0006_kind_update"),
    ]

    operations = [
        migrations.DeleteModel(
            name="PackingItem",
        ),
        migrations.AddField(
            model_name="trip",
            name="md_packing",
            field=models.TextField(blank=True, verbose_name="準備リスト（Markdown）"),
        ),
    ]
