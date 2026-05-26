# Generated manually for Survey model + SurveyResponse FK migration

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def _dedupe_survey_responses(apps):
    SurveyResponse = apps.get_model("medic", "SurveyResponse")
    from django.db.models import Count

    dupes = (
        SurveyResponse.objects.filter(survey_id__isnull=False)
        .values("user_id", "survey_id")
        .annotate(c=Count("id"))
        .filter(c__gt=1)
    )
    for d in dupes:
        rows = list(
            SurveyResponse.objects.filter(user_id=d["user_id"], survey_id=d["survey_id"]).order_by("-created_at", "-id")
        )
        for row in rows[1:]:
            row.delete()


def forwards_migrate_survey_responses(apps, schema_editor):
    Survey = apps.get_model("medic", "Survey")
    SurveyResponse = apps.get_model("medic", "SurveyResponse")

    slug_to_defaults = {
        "had_covid": {
            "title": "COVID-19",
            "question_text": "Болели Covid-19?",
            "answer_type": "yes_no",
            "profile_field": "had_covid",
            "sort_order": 1,
        },
        "onboarding": {
            "title": "Онбординг",
            "question_text": "Насколько понятно приложение?",
            "answer_type": "choice",
            "choices": ["1", "2", "3", "4", "5"],
            "sort_order": 2,
        },
    }

    for row in SurveyResponse.objects.all().iterator():
        slug = (getattr(row, "slug", None) or "").strip()
        if not slug:
            slug = "legacy"
        defaults = slug_to_defaults.get(
            slug,
            {
                "title": slug,
                "question_text": slug.replace("_", " ").capitalize(),
                "answer_type": "text",
                "sort_order": 99,
            },
        )
        survey, _ = Survey.objects.get_or_create(slug=slug, defaults=defaults)
        row.survey_id = survey.id
        row.save(update_fields=["survey_id"])

    _dedupe_survey_responses(apps)


def backwards_migrate_survey_responses(apps, schema_editor):
    SurveyResponse = apps.get_model("medic", "SurveyResponse")
    for row in SurveyResponse.objects.select_related("survey").iterator():
        if row.survey_id:
            row.slug = row.survey.slug
            row.save(update_fields=["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("medic", "0005_facility_coords_precision"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Survey",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=64, unique=True, verbose_name="Код")),
                ("title", models.CharField(blank=True, default="", max_length=255, verbose_name="Название (админка)")),
                ("question_text", models.CharField(max_length=512, verbose_name="Вопрос")),
                (
                    "answer_type",
                    models.CharField(
                        choices=[("yes_no", "Да / Нет"), ("text", "Текст"), ("choice", "Выбор из списка")],
                        default="yes_no",
                        max_length=16,
                        verbose_name="Тип ответа",
                    ),
                ),
                (
                    "choices",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text='Например: ["Да", "Нет"]',
                        verbose_name="Варианты (для choice)",
                    ),
                ),
                (
                    "profile_field",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="При ответе синхронизировать с профилем, напр. had_covid",
                        max_length=64,
                        verbose_name="Поле профиля",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="Активен")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Порядок")),
            ],
            options={
                "verbose_name": "Опрос",
                "verbose_name_plural": "Опросы",
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.AddField(
            model_name="surveyresponse",
            name="survey",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="responses",
                to="medic.survey",
                verbose_name="Опрос",
            ),
        ),
        migrations.RunPython(forwards_migrate_survey_responses, backwards_migrate_survey_responses),
        migrations.RemoveField(
            model_name="surveyresponse",
            name="slug",
        ),
        migrations.AlterField(
            model_name="surveyresponse",
            name="survey",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="responses",
                to="medic.survey",
                verbose_name="Опрос",
            ),
        ),
        migrations.AddConstraint(
            model_name="surveyresponse",
            constraint=models.UniqueConstraint(fields=("user", "survey"), name="uniq_survey_response_per_user"),
        ),
    ]
