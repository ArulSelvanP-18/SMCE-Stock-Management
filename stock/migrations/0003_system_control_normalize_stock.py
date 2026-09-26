from django.db import migrations, models
import django.db.models.deletion


def forwards(apps, schema_editor):
    SystemItem = apps.get_model("stock", "SystemItem")
    StockItem = apps.get_model("stock", "StockItem")
    DeadStock = apps.get_model("stock", "DeadStock")
    db = schema_editor.connection.alias

    masters = {}
    for row in StockItem.objects.using(db).all().order_by("id"):
        name = (row.item_name or "Unnamed Item").strip() or "Unnamed Item"
        code = (row.item_code or "").strip().upper()
        if not code:
            code = f"LEGACY-{row.pk}"
        master = masters.get(code)
        if master is None:
            master, _ = SystemItem.objects.using(db).get_or_create(
                item_code=code, defaults={"item_name": name}
            )
            masters[code] = master
        elif master.item_name.strip().casefold() != name.casefold():
            # The normalized master requires Item Code to be unique. If legacy
            # rows reused one code for different names, do not silently merge
            # the names. Preserve the stock row with a deterministic legacy
            # code so no stock record is lost during normalization.
            legacy_code = f"LEGACY-{row.pk}"
            master = SystemItem.objects.using(db).create(
                item_name=name,
                item_code=legacy_code,
            )
            masters[legacy_code] = master
        row.item_id = master.pk
        if row.status in ("Alive", "alive"):
            row.status = "ALIVE"
        elif row.status in ("Dead", "dead"):
            row.status = "DEAD"
        elif row.status not in ("ALIVE", "REPAIR", "DEAD"):
            row.status = "ALIVE"
        row.item_code = master.item_code
        row.item_name = master.item_name
        row.save(using=db, update_fields=["item", "item_code", "item_name", "status"])

    for row in DeadStock.objects.using(db).all():
        if row.status in ("Dead", "dead"):
            row.status = "DEAD"
            row.save(using=db, update_fields=["status"])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("stock", "0002_stockitem_deadstock_last_updated"),
    ]

    operations = [
        migrations.CreateModel(
            name="SystemItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("item_name", models.CharField(max_length=200)),
                ("item_code", models.CharField(db_index=True, max_length=50, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "SystemItem", "ordering": ["item_name", "item_code"]},
        ),
        migrations.CreateModel(
            name="TransferHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_block", models.CharField(max_length=150)),
                ("source_floor", models.CharField(max_length=50)),
                ("source_room", models.CharField(max_length=50)),
                ("destination_block", models.CharField(max_length=150)),
                ("destination_floor", models.CharField(max_length=50)),
                ("destination_room", models.CharField(max_length=50)),
                ("quantity", models.PositiveIntegerField()),
                ("transferred_at", models.DateTimeField(auto_now_add=True)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transfers", to="stock.systemitem")),
                ("transferred_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="stock_transfers", to="stock.member")),
            ],
            options={"db_table": "TransferHistory", "ordering": ["-transferred_at"]},
        ),
        migrations.AddField(
            model_name="stockitem",
            name="item",
            field=models.ForeignKey(blank=True, db_index=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="stock_records", to="stock.systemitem"),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name="stockitem",
            name="item",
            field=models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name="stock_records", to="stock.systemitem"),
        ),
        migrations.AlterField(
            model_name="stockitem",
            name="status",
            field=models.CharField(choices=[("ALIVE", "ALIVE"), ("REPAIR", "REPAIR"), ("DEAD", "DEAD")], db_index=True, default="ALIVE", max_length=10),
        ),
        migrations.AlterField(
            model_name="deadstock",
            name="status",
            field=models.CharField(default="DEAD", max_length=10),
        ),
        migrations.AddConstraint(
            model_name="systemitem",
            constraint=models.UniqueConstraint(fields=("item_name", "item_code"), name="systemitem_name_code_unique"),
        ),
    ]
