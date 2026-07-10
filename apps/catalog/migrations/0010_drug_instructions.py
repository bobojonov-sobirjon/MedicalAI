from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0009_alter_bodypart_sort_order"),
    ]

    operations = [
        migrations.AddField(
            model_name="drug",
            name="instructions",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Полная инструкция: показания, способ применения, дозы.",
                verbose_name="Инструкция по применению",
            ),
        ),
    ]
