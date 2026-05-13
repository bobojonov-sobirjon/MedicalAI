from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("medic", "0004_medicalfacility_description"),
    ]

    operations = [
        migrations.AlterField(
            model_name="medicalfacility",
            name="latitude",
            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True),
        ),
        migrations.AlterField(
            model_name="medicalfacility",
            name="longitude",
            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True),
        ),
    ]
