from django.db import migrations, models
import re


BLOCK_CODES = {
    "AdministrativeBlock": "ADMIN",
    "EngandTech1": "ENG",
    "EngandTech2": "ENG",
    "EngandTech3": "ENG",
    "BoysHostel": "HOSTEL-B",
    "GirlsHostel": "HOSTEL-G",
    "Auditorium": "AUD",
}
FLOOR_CODES = {"UG": "UG", "G": "GF", "FF": "FF", "SF": "SF"}


def token(value, fallback):
    value = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "").strip().upper()).strip("-")
    return value or fallback


def forwards(apps, schema_editor):
    StockItem = apps.get_model("stock", "StockItem")
    db = schema_editor.connection.alias

    used_by_base = {}
    rows = (
        StockItem.objects.using(db)
        .select_related("room", "room__block", "item")
        .all()
        .order_by("id")
    )

    for row in rows:
        block = BLOCK_CODES.get(
            row.room.block.source_table,
            token(row.room.block.source_table, "BLOCK"),
        )
        floor = FLOOR_CODES.get(
            row.room.floor,
            token(row.room.floor, "FL"),
        )
        try:
            room_no = f"{int(row.room.room_index):02d}" if int(row.room.room_index) < 100 else str(int(row.room.room_index))
        except (TypeError, ValueError):
            room_no = token(row.room.room_no, "ROOM")
        item_code = token(row.item.item_code if row.item_id else row.item_code, "ITEM")
        base = f"{block}-{floor}-{room_no}-{item_code}"

        used = used_by_base.setdefault(base, set())
        n = 1
        while n in used:
            n += 1
        used.add(n)

        row.instance_no = n
        row.item_code = f"{base}-{n:02d}"
        row.item_name = row.item.item_name if row.item_id else row.item_name
        row.source_table = row.room.block.source_table
        row.room_no = row.room.room_no
        row.save(
            using=db,
            update_fields=[
                "instance_no", "item_code", "item_name",
                "source_table", "room_no",
            ],
        )


def backwards(apps, schema_editor):
    # Codes are intentionally not reverted: the migration upgrades live stock
    # identifiers and reverting would recreate collisions/ambiguous legacy codes.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("stock", "0004_datetime_stock_dates"),
    ]

    operations = [
        migrations.AddField(
            model_name="stockitem",
            name="instance_no",
            field=models.PositiveIntegerField(db_index=True, default=1),
        ),
        migrations.AlterField(
            model_name="stockitem",
            name="item_code",
            field=models.CharField(db_index=True, max_length=100),
        ),
        migrations.AlterField(
            model_name="deadstock",
            name="item_code",
            field=models.CharField(db_index=True, max_length=100),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name="stockitem",
            name="item_code",
            field=models.CharField(db_index=True, max_length=100, unique=True),
        ),
    ]
