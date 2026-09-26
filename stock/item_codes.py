"""
Central Item Code generation service for SMCE Stock Management.

Generated format:
    BLOCK-FLOOR-ROOM-SYSTEM_CONTROL_CODE-INSTANCE

The service is the backend source of truth. Frontend previews are only
informational; every insert, edit, System Control change and stock transfer
regenerates/validates the current StockItem code inside a database transaction.
Historical DeadStock snapshots are intentionally not rewritten.
"""
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

FLOOR_CODES = {
    "UG": "UG",
    "G": "GF",
    "GF": "GF",
    "FF": "FF",
    "SF": "SF",
}


def block_code(block_or_source):
    source = getattr(block_or_source, "source_table", block_or_source)
    return BLOCK_CODES.get(source, _safe_token(str(source), "BLOCK"))


def floor_code(floor):
    return FLOOR_CODES.get(str(floor).upper(), _safe_token(str(floor), "FL"))


def room_code(room):
    # The logical room number is the stable room_index. This avoids embedding
    # the floor twice when Room.room_no is "G-5", "FF-5", etc.
    try:
        number = int(room.room_index)
        return f"{number:02d}" if number < 100 else str(number)
    except (TypeError, ValueError):
        raw = str(getattr(room, "room_no", "")).strip()
        m = re.search(r"(\d+)$", raw)
        return f"{int(m.group(1)):02d}" if m else _safe_token(raw, "ROOM")


def system_item_code(system_item):
    return _safe_token(system_item.item_code, "ITEM")


def build_item_code_base(room, system_item):
    return "-".join([
        block_code(room.block),
        floor_code(room.floor),
        room_code(room),
        system_item_code(system_item),
    ])


def build_item_code(base, instance_no):
    return f"{base}-{int(instance_no):02d}"


def _safe_token(value, fallback):
    value = re.sub(r"[^A-Za-z0-9]+", "-", str(value).strip().upper()).strip("-")
    return value or fallback


def _used_instance_numbers(base, exclude_pk=None):
    from .models import StockItem
    qs = StockItem.objects.filter(item_code__startswith=base + "-").values_list(
        "item_code", flat=True
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    used = set()
    prefix = base + "-"
    for code in qs:
        code = str(code)
        suffix = code[len(prefix):]
        if suffix.isdigit():
            used.add(int(suffix))
    return used


def allocate_instance_no(base, preferred=None, exclude_pk=None):
    """Return a globally safe instance suffix for this location/item base."""
    used = _used_instance_numbers(base, exclude_pk=exclude_pk)
    if preferred and int(preferred) > 0 and int(preferred) not in used:
        return int(preferred)
    n = 1
    while n in used:
        n += 1
    return n


def generate_item_code(room, system_item, preferred_instance=None, exclude_pk=None):
    """Generate a unique code. Call from an atomic transaction."""
    base = build_item_code_base(room, system_item)
    instance = allocate_instance_no(base, preferred_instance, exclude_pk)
    return build_item_code(base, instance), instance


def regenerate_stock_item(stock_item, *, preferred_instance=None, save=True):
    """Regenerate a StockItem code from its current room + SystemItem."""
    if not stock_item.room_id or not stock_item.item_id:
        raise ValueError("Stock item requires both Room and System Control item.")
    code, instance = generate_item_code(
        stock_item.room, stock_item.item,
        preferred_instance=preferred_instance if preferred_instance is not None else stock_item.instance_no,
        exclude_pk=stock_item.pk,
    )
    stock_item.instance_no = instance
    stock_item.item_code = code
    stock_item.item_name = stock_item.item.item_name
    stock_item.source_table = stock_item.room.block.source_table
    stock_item.room_no = stock_item.room.room_no
    if save:
        stock_item.save(update_fields=[
            "item_code", "instance_no", "item_name", "source_table",
            "room_no", "updated_at"
        ])
    return stock_item


def regenerate_all_for_system_item(system_item):
    """Regenerate all current StockItem rows after a System Control change.

    This includes current StockItem rows whose status is DEAD because the live
    inventory row still represents the current location. Their separate
    DeadStock historical snapshots are never rewritten by this operation.
    """
    from .models import StockItem
    rows = list(
        StockItem.objects.select_for_update()
        .select_related("room", "room__block", "item")
        .filter(item=system_item)
        .order_by("id")
    )
    for row in rows:
        regenerate_stock_item(row, preferred_instance=row.instance_no, save=True)
    return rows
