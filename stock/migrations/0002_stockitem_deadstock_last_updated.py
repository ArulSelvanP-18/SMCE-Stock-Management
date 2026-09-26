# Generated manually for the SMCE Stock Management date-tracking upgrade.
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("stock", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="stockitem",
            name="last_updated",
            field=models.DateField(default=django.utils.timezone.localdate),
        ),
        migrations.AddField(
            model_name="deadstock",
            name="last_updated",
            field=models.DateField(default=django.utils.timezone.localdate),
        ),
    ]
