from django.db import migrations


DESIRED_BODY_PARTS = [
    ("head", "Голова", 10),
    ("neck", "Шея", 20),
    ("body", "Тело", 30),
    ("left_arm", "Левая рука", 40),
    ("right_arm", "Правая рука", 50),
    ("leg", "Нога", 60),
]

OLD_SEED_CODES = [
    "throat",
    "chest",
    "back",
    "abdomen",
    "pelvis",
    "left_hand",
    "right_hand",
    "left_leg",
    "right_leg",
    "left_foot",
    "right_foot",
    "skin",
]


def apply_body_parts(apps, schema_editor):
    BodyPart = apps.get_model("catalog", "BodyPart")

    for code, label, sort_order in DESIRED_BODY_PARTS:
        BodyPart.objects.update_or_create(
            code=code,
            defaults={"label": label, "sort_order": sort_order},
        )

    BodyPart.objects.filter(code__in=OLD_SEED_CODES).delete()


def reverse_body_parts(apps, schema_editor):
    BodyPart = apps.get_model("catalog", "BodyPart")
    BodyPart.objects.filter(code__in=[code for code, _, _ in DESIRED_BODY_PARTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0007_seed_helper_reference_data"),
    ]

    operations = [
        migrations.RunPython(apply_body_parts, reverse_code=reverse_body_parts),
    ]
