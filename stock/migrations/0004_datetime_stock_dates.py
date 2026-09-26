from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("stock", "0003_system_control_normalize_stock")]
    operations = [
        migrations.AlterField(
            model_name="stockitem",
            name="last_updated",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name="deadstock",
            name="last_updated",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
