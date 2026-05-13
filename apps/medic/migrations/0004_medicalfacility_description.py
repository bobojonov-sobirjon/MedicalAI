from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("medic", "0003_notificationevent_meta_notificationevent_notify_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="medicalfacility",
            name="description",
            field=models.TextField(blank=True, default="", verbose_name="Описание"),
        ),
    ]
