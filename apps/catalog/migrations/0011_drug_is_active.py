from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0010_drug_instructions"),
    ]

    operations = [
        migrations.AddField(
            model_name="drug",
            name="is_active",
            field=models.BooleanField(
                default=True,
                help_text="Снимите галочку, чтобы скрыть препарат (напр. мусорные импортированные записи).",
                verbose_name="Показывать в приложении",
            ),
        ),
    ]
