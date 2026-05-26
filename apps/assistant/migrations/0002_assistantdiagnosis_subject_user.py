import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assistant", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="assistantdiagnosis",
            name="subject_user",
            field=models.ForeignKey(
                blank=True,
                help_text="Член семьи или сам владелец (ТЗ §8.2.3).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assistant_diagnoses_as_subject",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Для кого диагностика",
            ),
        ),
    ]
