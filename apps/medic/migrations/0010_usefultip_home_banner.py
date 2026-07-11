from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("medic", "0009_city_geo_level"),
    ]

    operations = [
        migrations.AddField(
            model_name="usefultip",
            name="image",
            field=models.ImageField(
                blank=True,
                help_text="Иллюстрация для карусели на главной странице (ТЗ §7.6).",
                null=True,
                upload_to="useful_tips/",
                verbose_name="Картинка (баннер на главной)",
            ),
        ),
        migrations.AddField(
            model_name="usefultip",
            name="show_on_home",
            field=models.BooleanField(
                default=True,
                help_text="Баннер «полезные советы» вверху главной страницы ЛК.",
                verbose_name="Показывать на главной",
            ),
        ),
        migrations.AddField(
            model_name="usertipsettings",
            name="home_tips_hidden",
            field=models.BooleanField(
                default=False,
                help_text="ТЗ §7.6: пользователь скрыл баннер; снова показать — знак вопроса.",
                verbose_name="Скрыть блок советов на главной",
            ),
        ),
    ]
