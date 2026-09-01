from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_alter_familylink_created_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="active_profile_id",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="id пользователя, от имени которого сейчас ведётся главная/история. Пусто = владелец.",
                null=True,
                verbose_name="Активный семейный профиль",
            ),
        ),
    ]
