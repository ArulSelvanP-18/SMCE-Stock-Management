from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Count, Sum
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .catalog import seed_catalog, floors_for_block, ROOMS_PER_FLOOR
from .forms import (
    LoginForm, RegistrationForm, RoomForm, StockItemForm,
    StockSearchForm, ReportFilterForm, DeadStockFilterForm, ImportFileForm,
    AnalysisFilterForm,
)
from .models import Block, Room, StockItem, DeadStock, SystemItem, TransferHistory
from .item_codes import generate_item_code, regenerate_all_for_system_item
from .utils import (
    dataframe_from_upload, validate_import_dataframe,
    export_queryset_csv, export_queryset_excel,
    sample_room_import_csv,
)

RESULTS_PAGE_SIZE = 50


# ---------------------------------------------------------------------------
# Public landing page
# ---------------------------------------------------------------------------
def landing_view(request):
    """Public project landing page matching the supplied front-page design."""
    return render(request, "stock/landing.html")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password"],
        )
        if user is not None:
            login(request, user)
            return redirect("dashboard")
        messages.error(request, "Invalid username or password.")
    return render(request, "stock/login.html", {"form": form})


def registration_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Account created successfully. Please log in.")
        return redirect("login")
    return render(request, "stock/registration.html", {"form": form})


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")


# ---------------------------------------------------------------------------
# System Control / Central Item Master
# ---------------------------------------------------------------------------
@login_required
def _system_control_guard(request):
    if not request.user.is_admin_role:
        messages.error(request, "Only Admin users can manage System Control items.")
        return False
    return True


@login_required
def system_control_view(request):
    if not _system_control_guard(request):
        return redirect("dashboard")
    query = (request.GET.get("q") or "").strip()
    items = SystemItem.objects.all()
    if query:
        items = items.filter(Q(item_name__icontains=query) | Q(item_code__icontains=query))
    return render(request, "stock/system_control.html", {"items": items, "query": query})


@login_required
@require_POST
def system_item_create_view(request):
    if not _system_control_guard(request):
        return redirect("dashboard")
    name = " ".join((request.POST.get("item_name") or "").split())
    code = " ".join((request.POST.get("item_code") or "").split()).upper()
    if not name or not code:
        messages.error(request, "Item Name and Item Code are required.")
        return redirect("system_control")
    if SystemItem.objects.filter(item_code__iexact=code).exists():
        messages.error(request, f"Item Code '{code}' already exists.")
        return redirect("system_control")
    if SystemItem.objects.filter(item_name__iexact=name).exists():
        messages.error(request, f"Item Name '{name}' is already configured. Edit the existing System Control entry instead of creating a second mapping.")
        return redirect("system_control")
    SystemItem.objects.create(item_name=name, item_code=code)
    messages.success(request, f"'{name}' ({code}) added to System Control.")
    return redirect("system_control")


@login_required
@require_POST
def system_item_update_view(request, item_id):
    if not _system_control_guard(request):
        return redirect("dashboard")
    obj = get_object_or_404(SystemItem, pk=item_id)
    name = " ".join((request.POST.get("item_name") or "").split())
    code = " ".join((request.POST.get("item_code") or "").split()).upper()
    if not name or not code:
        messages.error(request, "Item Name and Item Code are required.")
        return redirect("system_control")
    if SystemItem.objects.filter(item_code__iexact=code).exclude(pk=obj.pk).exists():
        messages.error(request, f"Item Code '{code}' already exists.")
        return redirect("system_control")
    if SystemItem.objects.filter(item_name__iexact=name).exclude(pk=obj.pk).exists():
        messages.error(request, f"Item Name '{name}' is already mapped to another System Control entry.")
        return redirect("system_control")
    with transaction.atomic():
        obj = SystemItem.objects.select_for_update().get(pk=obj.pk)
        obj.item_name, obj.item_code = name, code
        obj.save(update_fields=["item_name", "item_code", "updated_at"])
        # Rebuild every LIVE stock code from the new System Control mapping.
        # Dead Stock remains a historical snapshot and is intentionally not
        # rewritten when the live master code changes.
        regenerate_all_for_system_item(obj)
        StockItem.objects.filter(item=obj).update(item_name=name)
    messages.success(request, "System Control item updated. Current stock Item Codes were regenerated.")
    return redirect("system_control")


@login_required
@require_POST
def system_item_delete_view(request, item_id):
    if not _system_control_guard(request):
        return redirect("dashboard")
    obj = get_object_or_404(SystemItem, pk=item_id)
    if StockItem.objects.filter(item=obj).exists():
        messages.error(request, "This master item is in use by stock records and cannot be deleted.")
        return redirect("system_control")
    if TransferHistory.objects.filter(item=obj).exists():
        messages.error(request, "This master item is referenced by transfer history and cannot be deleted.")
        return redirect("system_control")
    obj.delete()
    messages.success(request, "System Control item deleted.")
    return redirect("system_control")


@login_required
def system_items_api(request):
    query = (request.GET.get("q") or "").strip()
    items = SystemItem.objects.all()
    if query:
        items = items.filter(Q(item_name__icontains=query) | Q(item_code__icontains=query))
    return JsonResponse({
        "items": [{"id": x.id, "item_name": x.item_name, "item_code": x.item_code} for x in items[:50]]
    })


@login_required
def item_code_preview_api(request):
    """Return the server-generated preview for a room + Item Name."""
    item_name = " ".join((request.GET.get("item_name") or "").split())
    room_id = request.GET.get("room_id")
    stock_id = request.GET.get("stock_id")
    if not item_name or not room_id:
        return JsonResponse({"error": "Item Name and Room are required."}, status=400)
    try:
        room = Room.objects.select_related("block").get(pk=int(room_id))
    except (TypeError, ValueError, Room.DoesNotExist):
        return JsonResponse({"error": "Invalid room."}, status=400)

    master = SystemItem.objects.filter(item_name__iexact=item_name).first()
    if not master:
        return JsonResponse({
            "error": "Item Code is not configured for this Item Name. Add it in System Control first."
        }, status=400)

    preferred = None
    exclude_pk = None
    if stock_id:
        try:
            stock = StockItem.objects.get(pk=int(stock_id))
            if stock.item_id == master.id:
                preferred = stock.instance_no
                exclude_pk = stock.pk
        except (TypeError, ValueError, StockItem.DoesNotExist):
            pass

    code, instance_no = generate_item_code(
        room, master, preferred_instance=preferred, exclude_pk=exclude_pk
    )
    return JsonResponse({
        "item_name": master.item_name,
        "system_control_code": master.item_code,
        "item_code": code,
        "instance_no": instance_no,
    })


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@login_required
def dashboard_view(request):
    seed_catalog()
    stats = {
        "total_items": StockItem.objects.count(),
        "alive_items": StockItem.objects.filter(status=StockItem.STATUS_ALIVE).count(),
        "dead_items": StockItem.objects.filter(status=StockItem.STATUS_DEAD).count(),
        "repair_items": StockItem.objects.filter(status=StockItem.STATUS_REPAIR).count(),
        "total_rooms": Room.objects.count(),
    }
    return render(request, "stock/dashboard.html", {"stats": stats})


# ---------------------------------------------------------------------------
# Navigation: Block -> (Department) -> Floor -> Rooms
# Shared between MODIFY (editable) and VIEW (read-only) via `mode` kwarg.
# ---------------------------------------------------------------------------
@login_required
def block_list_view(request, mode):
    seed_catalog()
    top_blocks = Block.objects.filter(parent__isnull=True).order_by("id")
    return render(request, "stock/block_list.html", {"mode": mode, "blocks": top_blocks})


@login_required
def block_detail_view(request, mode, slug):
    """Shows either departments (for Eng & Tech Block 2) or floors directly."""
    block = get_object_or_404(Block, slug=slug)
    children = block.children.all().order_by("id")
    if children.exists():
        return render(request, "stock/department_list.html", {"mode": mode, "block_obj": block, "children": children})
    floors = floors_for_block(block)
    floor_display = dict(Room.FLOOR_CHOICES)
    floor_data = [{"code": f, "label": floor_display[f]} for f in floors]
    return render(request, "stock/floor_list.html", {"mode": mode, "block_obj": block, "floors": floor_data})


@login_required
def floor_room_list_view(request, mode, slug, floor):
    block = get_object_or_404(Block, slug=slug)
    valid_floors = [f[0] for f in Room.FLOOR_CHOICES]
    if floor not in valid_floors:
        messages.error(request, "Invalid floor selected.")
        return redirect("block_detail", mode=mode, slug=slug)

    rooms = list(range(1, ROOMS_PER_FLOOR + 1))
    existing = {
        r.room_index: r for r in Room.objects.filter(block=block, floor=floor)
    }
    room_rows = []
    for idx in rooms:
        room_rows.append({"index": idx, "room": existing.get(idx)})

    return render(
        request,
        "stock/room_list.html",
        {
            "mode": mode,
            "block_obj": block,
            "floor_code": floor,
            "floor_label": dict(Room.FLOOR_CHOICES)[floor],
            "room_rows": room_rows,
        },
    )


@login_required
def room_mini_window_view(request, mode, slug, floor, index):
    block = get_object_or_404(Block, slug=slug)
    room, created = Room.objects.get_or_create(
        block=block, floor=floor, room_index=index,
        defaults={"room_no": f"{floor}-{index}"},
    )

    if mode == "modify" and not request.user.is_admin_role:
        messages.error(request, "Only Admin users can modify room details.")
        return redirect("room_list", mode="view", slug=slug, floor=floor)

    read_only = mode == "view"
    form = RoomForm(request.POST or None, instance=room)
    if request.method == "POST" and not read_only:
        if "save_changes" in request.POST:
            if form.is_valid():
                room = form.save(commit=False)
                if room.auto_update_db:
                    room.save()
                    messages.success(request, "Room details saved.")
                else:
                    messages.info(request, "Auto-update is off — changes were not written to the database.")
                return redirect(
                    "room_mini_window", mode=mode, slug=slug, floor=floor, index=index
                )
        elif "open_room" in request.POST:
            return redirect("room_stock", mode=mode, slug=slug, floor=floor, index=index)

    return render(
        request,
        "stock/room_mini_window.html",
        {
            "mode": mode, "block_obj": block, "floor_label": dict(Room.FLOOR_CHOICES)[floor],
            "floor": floor, "index": index, "room": room, "form": form, "read_only": read_only,
        },
    )


# ---------------------------------------------------------------------------
# Room Stock Management page (Treeview-equivalent table)
# ---------------------------------------------------------------------------
@login_required
def room_stock_view(request, mode, slug, floor, index):
    block = get_object_or_404(Block, slug=slug)
    room = get_object_or_404(Room, block=block, floor=floor, room_index=index)
    read_only = mode == "view"

    search_form = StockSearchForm(request.GET or None)
    items = room.stock_items.all().order_by("item_code")
    query = ""
    if search_form.is_valid():
        query = (search_form.cleaned_data.get("query") or "").strip()
        status = search_form.cleaned_data.get("status")
        if query:
            items = items.filter(
                Q(item_name__icontains=query)
                | Q(item_code__icontains=query)
                | Q(item_no__icontains=query)
                | Q(room_no__icontains=query)
                | Q(status__icontains=query)
            )
        if status:
            items = items.filter(status=status)

    import_form = ImportFileForm()

    return render(
        request,
        "stock/room_stock.html",
        {
            "mode": mode, "block_obj": block, "room": room, "items": items,
            "search_form": search_form, "query": query, "read_only": read_only,
            "new_item_form": StockItemForm() if not read_only else None,
            "import_form": import_form,
        },
    )


@login_required
@require_POST
def stock_insert_view(request, mode, slug, floor, index):
    block = get_object_or_404(Block, slug=slug)
    room = get_object_or_404(Room, block=block, floor=floor, room_index=index)
    if not request.user.is_admin_role:
        messages.error(request, "Only Admin users can insert stock.")
        return redirect("room_stock", mode="view", slug=slug, floor=floor, index=index)

    form = StockItemForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            master = SystemItem.objects.select_for_update().get(pk=form._system_item.pk)
            item = form.save(commit=False)
            item.room = room
            item.item = master
            item.item_name = master.item_name
            # Lock the master row so concurrent inserts for this System
            # Control mapping allocate instance suffixes serially.
            code, instance_no = generate_item_code(room, master)
            item.item_code = code
            item.instance_no = instance_no
            item.source_table = block.source_table
            item.room_no = room.room_no
            # Existing Item No behaviour is preserved.
            nums = []
            for value in StockItem.objects.filter(item=master).values_list("item_no", flat=True):
                try:
                    nums.append(int(str(value)))
                except (TypeError, ValueError):
                    pass
            item.item_no = str(max(nums, default=0) + 1)
            item.last_updated = form.cleaned_data.get("last_updated") or timezone.now()
            try:
                item.save()
            except Exception as exc:
                # A database-level unique constraint is the final protection.
                messages.error(request, f"Item Code could not be created safely: {exc}")
                return redirect("room_stock", mode=mode, slug=slug, floor=floor, index=index)
            _sync_dead_stock(item)
        messages.success(request, f"Item inserted successfully with Item Code {item.item_code}.")
    else:
        messages.error(request, "Please correct the errors: " + "; ".join(
            f"{k}: {', '.join(v)}" for k, v in form.errors.items()
        ))
    return redirect("room_stock", mode=mode, slug=slug, floor=floor, index=index)


@login_required
@require_POST
def stock_update_view(request, mode, slug, floor, index, item_id):
    block = get_object_or_404(Block, slug=slug)
    room = get_object_or_404(Room, block=block, floor=floor, room_index=index)
    item = get_object_or_404(
        StockItem.objects.select_related("item", "room", "room__block"),
        pk=item_id, room=room
    )
    if not request.user.is_admin_role:
        messages.error(request, "Only Admin users can update stock.")
        return redirect("room_stock", mode="view", slug=slug, floor=floor, index=index)

    form = StockItemForm(request.POST, instance=item)
    if form.is_valid():
        with transaction.atomic():
            locked = StockItem.objects.select_for_update().select_related(
                "item", "room", "room__block"
            ).get(pk=item.pk)
            master = SystemItem.objects.select_for_update().get(pk=form._system_item.pk)
            preferred = locked.instance_no
            updated_item = form.save(commit=False)
            updated_item.pk = locked.pk
            updated_item.room = room
            updated_item.item = master
            updated_item.item_name = master.item_name
            updated_item.source_table = block.source_table
            updated_item.room_no = room.room_no
            # Always regenerate from current location + current System Control
            # mapping. Preserve the physical instance suffix where possible.
            code, instance_no = generate_item_code(
                room, master, preferred_instance=preferred, exclude_pk=locked.pk
            )
            updated_item.item_code = code
            updated_item.instance_no = instance_no
            if not updated_item.item_no:
                updated_item.item_no = locked.item_no
            updated_item.last_updated = form.cleaned_data.get("last_updated") or timezone.now()
            updated_item.save()
            _sync_dead_stock(updated_item)
        messages.success(request, f"Item updated successfully. Item Code: {updated_item.item_code}.")
    else:
        messages.error(request, "Please correct the errors: " + "; ".join(
            f"{k}: {', '.join(v)}" for k, v in form.errors.items()
        ))
    return redirect("room_stock", mode=mode, slug=slug, floor=floor, index=index)


@login_required
@require_POST
def stock_delete_view(request, mode, slug, floor, index, item_id):
    block = get_object_or_404(Block, slug=slug)
    room = get_object_or_404(Room, block=block, floor=floor, room_index=index)
    item = get_object_or_404(StockItem, pk=item_id, room=room)
    if not request.user.is_admin_role:
        messages.error(request, "Only Admin users can delete stock.")
        return redirect("room_stock", mode="view", slug=slug, floor=floor, index=index)

    item.delete()
    messages.success(request, "Item deleted.")
    return redirect("room_stock", mode=mode, slug=slug, floor=floor, index=index)


def _sync_dead_stock(item: StockItem):
    """Create/remove Dead Stock snapshots without rewriting historical data.

    A DeadStock row is a historical snapshot of the moment a StockItem was
    recorded as DEAD. Once it exists, later location moves, Item Name changes,
    quantity edits, or System Control code changes must not rewrite that
    historical Item Code/location. If the live StockItem becomes non-dead, its
    active DeadStock snapshot is removed because it is no longer dead.
    """
    if item.status == StockItem.STATUS_DEAD:
        # get_or_create is intentional: unlike update_or_create, it preserves
        # the original historical Item Code and location after a later move.
        DeadStock.objects.get_or_create(
            stock_item=item,
            defaults={
                "item_code": item.item_code,
                "item_no": item.item_no,
                "item_name": item.item_name,
                "quantity": item.quantity,
                "room_no": item.room_no,
                "source_table": item.source_table,
                "last_updated": item.last_updated,
                "status": StockItem.STATUS_DEAD,
            },
        )
    else:
        DeadStock.objects.filter(stock_item=item).delete()



# ---------------------------------------------------------------------------
# Transfer Data
# ---------------------------------------------------------------------------
@login_required
def transfer_view(request):
    """Interactive source -> selected records -> destination transfer page."""
    seed_catalog()
    # Leaf Block nodes are the actual locations that can own rooms/stock.
    # This includes the departments under Eng & Tech Block 2.
    blocks = (
        Block.objects.filter(children__isnull=True)
        .order_by("parent_id", "name")
    )
    return render(request, "stock/transfer.html", {"blocks": blocks})


def _transfer_allowed_floor(block, floor):
    return floor in floors_for_block(block)


@login_required
def transfer_floors_api(request):
    """Return floors that belong to the selected block."""
    try:
        block_id = int(request.GET.get("block_id", "0"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid block."}, status=400)

    block = get_object_or_404(Block, pk=block_id)
    floors = floors_for_block(block)
    labels = dict(Room.FLOOR_CHOICES)
    return JsonResponse({
        "floors": [{"code": code, "label": labels.get(code, code)} for code in floors]
    })


@login_required
def transfer_rooms_api(request):
    """Return the ten logical rooms for a block/floor, including existing DB rows."""
    try:
        block_id = int(request.GET.get("block_id", "0"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid block."}, status=400)

    floor = (request.GET.get("floor") or "").strip()
    block = get_object_or_404(Block, pk=block_id)
    if not _transfer_allowed_floor(block, floor):
        return JsonResponse({"error": "That floor does not belong to the selected block."}, status=400)

    existing = {
        room.room_index: room
        for room in Room.objects.filter(block=block, floor=floor).order_by("room_index")
    }
    rooms = []
    for index in range(1, ROOMS_PER_FLOOR + 1):
        room = existing.get(index)
        rooms.append({
            "id": room.id if room else None,
            "index": index,
            "room_no": room.room_no if room else f"{floor}-{index}",
            "room_name": room.room_name if room else "",
            "has_stock": bool(room and room.stock_items.exists()),
        })
    return JsonResponse({"rooms": rooms})


@login_required
def transfer_stock_api(request):
    """Return stock rows for one selected source room."""
    try:
        room_id = int(request.GET.get("room_id", "0"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid room."}, status=400)

    room = get_object_or_404(Room.objects.select_related("block"), pk=room_id)
    items = room.stock_items.all().order_by("item_code")
    rows = [{
        "id": item.id,
        "item_code": item.item_code,
        "item_no": item.item_no,
        "item_name": item.item_name,
        "quantity": item.quantity,
        "room_no": item.room_no,
        "status": item.status,
        "last_updated": item.last_updated.strftime("%Y-%m-%d") if item.last_updated else "",
    } for item in items]
    return JsonResponse({
        "room": {
            "id": room.id,
            "room_no": room.room_no,
            "block": room.block.name,
            "floor": room.get_floor_display(),
        },
        "items": rows,
    })


@login_required
@require_POST
def transfer_execute_view(request):
    """Atomically move selected StockItem rows to the destination room."""
    if not request.user.is_admin_role:
        messages.error(request, "Only Admin users can transfer stock.")
        return redirect("transfer")

    try:
        source_block_id = int(request.POST.get("source_block_id", "0") or 0)
        source_floor = (request.POST.get("source_floor") or "").strip()
        source_room_id = int(request.POST.get("source_room_id", "0") or 0)
        destination_block_id = int(request.POST.get("destination_block_id", "0") or 0)
        destination_floor = (request.POST.get("destination_floor") or "").strip()
        destination_room_id = int(request.POST.get("destination_room_id", "0") or 0)
        destination_room_index = int(request.POST.get("destination_room_index", "0") or 0)
    except (TypeError, ValueError):
        messages.error(request, "Invalid transfer selection.")
        return redirect("transfer")

    raw_ids = request.POST.getlist("item_ids")
    try:
        item_ids = sorted({int(value) for value in raw_ids})
    except (TypeError, ValueError):
        messages.error(request, "Invalid stock record selection.")
        return redirect("transfer")

    if not source_block_id or not source_floor or not source_room_id:
        messages.error(request, "Please select a source block, floor and room.")
        return redirect("transfer")
    if not item_ids:
        messages.error(request, "Please select at least one stock record.")
        return redirect("transfer")
    if not destination_block_id or not destination_floor or not destination_room_index:
        messages.error(request, "Please select a complete destination.")
        return redirect("transfer")

    source_block = get_object_or_404(Block, pk=source_block_id)
    if not _transfer_allowed_floor(source_block, source_floor):
        messages.error(request, "The selected source floor does not belong to that block.")
        return redirect("transfer")

    source_room = get_object_or_404(
        Room.objects.select_related("block"),
        pk=source_room_id,
        block=source_block,
        floor=source_floor,
    )
    destination_block = get_object_or_404(Block, pk=destination_block_id)

    if not _transfer_allowed_floor(destination_block, destination_floor):
        messages.error(request, "The selected destination floor does not belong to that block.")
        return redirect("transfer")

    # If the room already exists, require that it matches the chosen block/floor.
    destination_room = None
    if destination_room_id:
        destination_room = get_object_or_404(Room.objects.select_related("block"), pk=destination_room_id)
        if (
            destination_room.block_id != destination_block.id
            or destination_room.floor != destination_floor
            or destination_room.room_index != destination_room_index
        ):
            messages.error(request, "Invalid destination block, floor and room combination.")
            return redirect("transfer")
    else:
        if not (1 <= destination_room_index <= ROOMS_PER_FLOOR):
            messages.error(request, "Invalid destination room.")
            return redirect("transfer")

    if destination_room and destination_room.pk == source_room.pk:
        messages.error(request, "Source and destination rooms must be different.")
        return redirect("transfer")

    transfer_date_raw = (request.POST.get("transfer_date") or "").strip()
    try:
        if transfer_date_raw:
            naive_dt = timezone.datetime.combine(
                timezone.datetime.strptime(transfer_date_raw, "%Y-%m-%d").date(),
                timezone.datetime.min.time(),
            )
            # last_updated is a DateTimeField; storing a naive datetime while
            # USE_TZ=True raises RuntimeWarning and lets Django guess the
            # timezone, so make it explicitly timezone-aware here instead.
            transfer_date = timezone.make_aware(naive_dt) if timezone.is_naive(naive_dt) else naive_dt
        else:
            transfer_date = timezone.now()
    except ValueError:
        messages.error(request, "Please choose a valid transfer date.")
        return redirect("transfer")

    with transaction.atomic():
        # Lock selected rows to prevent two browser clicks/users moving the same
        # records at the same time.
        items = list(
            StockItem.objects.select_for_update()
            .filter(pk__in=item_ids, room=source_room)
            .order_by("id")
        )
        if len(items) != len(item_ids):
            messages.error(request, "One or more selected records are no longer in the source room.")
            return redirect("transfer")

        if destination_room is None:
            destination_room, _ = Room.objects.get_or_create(
                block=destination_block,
                floor=destination_floor,
                room_index=destination_room_index,
                defaults={
                    "room_no": f"{destination_floor}-{destination_room_index}",
                },
            )
        else:
            destination_room = (
                Room.objects.select_for_update()
                .select_related("block")
                .get(pk=destination_room.pk)
            )

        if destination_room.pk == source_room.pk:
            messages.error(request, "Source and destination rooms must be different.")
            return redirect("transfer")

        # Quantity-aware transfer. A partial move reduces the source row and
        # creates/updates the same master item in the destination.
        transfer_rows = []
        for item in items:
            try:
                qty = int(request.POST.get(f"qty_{item.pk}", "0") or 0)
            except (TypeError, ValueError):
                messages.error(request, f"Invalid transfer quantity for {item.item_name}.")
                return redirect("transfer")
            if qty <= 0 or qty > item.quantity:
                messages.error(
                    request,
                    f"Transfer quantity for {item.item_name} must be between 1 and {item.quantity}.",
                )
                return redirect("transfer")
            transfer_rows.append((item, qty))

        for item, qty in transfer_rows:
            # Serialize Item Code allocation for this System Control mapping.
            master = SystemItem.objects.select_for_update().get(pk=item.item_id)
            item.item = master
            # Never merge rows during a location transfer: each StockItem row
            # owns one stable physical-instance suffix. This preserves unique
            # Item Codes and makes partial moves safe.
            old_instance = item.instance_no

            if qty == item.quantity:
                destination = item
                destination.room = destination_room
                destination.item = item.item
                destination.item_name = item.item.item_name
                destination.source_table = destination_block.source_table
                destination.room_no = destination_room.room_no
                destination.last_updated = transfer_date
                code, instance_no = generate_item_code(
                    destination_room, destination.item,
                    preferred_instance=old_instance,
                    exclude_pk=destination.pk,
                )
                destination.item_code = code
                destination.instance_no = instance_no
                destination.save(update_fields=[
                    "room", "item", "item_name", "source_table", "room_no",
                    "item_code", "instance_no", "last_updated", "updated_at"
                ])
            else:
                # Partial transfer creates a distinct physical stock row in
                # the destination and leaves the source row/code untouched.
                destination = StockItem(
                    room=destination_room,
                    item=item.item,
                    item_name=item.item.item_name,
                    source_table=destination_block.source_table,
                    room_no=destination_room.room_no,
                    item_no="",
                    quantity=qty,
                    status=item.status,
                    last_updated=transfer_date,
                    instance_no=1,
                )
                code, instance_no = generate_item_code(
                    destination_room, destination.item
                )
                destination.item_code = code
                destination.instance_no = instance_no
                nums = []
                for value in StockItem.objects.filter(item=item.item).values_list("item_no", flat=True):
                    try:
                        nums.append(int(str(value)))
                    except (TypeError, ValueError):
                        pass
                destination.item_no = str(max(nums, default=0) + 1)
                destination.save()

                item.quantity -= qty
                item.last_updated = transfer_date
                item.save(update_fields=["quantity", "last_updated", "updated_at"])
                _sync_dead_stock(item)

            _sync_dead_stock(destination)
            TransferHistory.objects.create(
                item=destination.item,
                source_block=source_block.name,
                source_floor=source_floor,
                source_room=source_room.room_no,
                destination_block=destination_block.name,
                destination_floor=destination_floor,
                destination_room=destination_room.room_no,
                quantity=qty,
                transferred_by=request.user,
            )


    source_label = source_room.room_no
    destination_label = destination_room.room_no
    messages.success(
        request,
        f"{len(item_ids)} record(s) transferred successfully from {source_label} to {destination_label}.",
    )
    return redirect("transfer")


# ---------------------------------------------------------------------------
# Import / Export (per room)
# ---------------------------------------------------------------------------
@login_required
@require_POST
def stock_import_view(request, mode, slug, floor, index):
    block = get_object_or_404(Block, slug=slug)
    room = get_object_or_404(Room, block=block, floor=floor, room_index=index)
    if not request.user.is_admin_role:
        messages.error(request, "Only Admin users can import stock.")
        return redirect("room_stock", mode="view", slug=slug, floor=floor, index=index)

    form = ImportFileForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            df = dataframe_from_upload(form.cleaned_data["file"])
        except Exception as exc:
            messages.error(request, f"Could not read the file: {exc}")
            return redirect("room_stock", mode=mode, slug=slug, floor=floor, index=index)

        errors = validate_import_dataframe(df)
        if errors:
            for e in errors[:10]:
                messages.error(request, e)
            if len(errors) > 10:
                messages.error(request, f"...and {len(errors) - 10} more error(s).")
            return redirect("room_stock", mode=mode, slug=slug, floor=floor, index=index)

        created, updated = 0, 0
        for _, row in df.iterrows():
            name = str(row.get("item_name", "")).strip()
            master = SystemItem.objects.filter(item_name__iexact=name).first()
            if not master:
                legacy_code = str(row.get("item_code", "")).strip().upper()
                master = SystemItem.objects.filter(item_code__iexact=legacy_code).first()
            if not master:
                messages.error(request, f"Item Name '{name}' is not configured in System Control.")
                continue

            with transaction.atomic():
                master = SystemItem.objects.select_for_update().get(pk=master.pk)
                existing = StockItem.objects.filter(room=room, item=master).order_by("id").first()
                status = str(row.get("status", "ALIVE")).strip().upper()
                if existing:
                    existing.quantity = int(row["quantity"])
                    existing.item_name = master.item_name
                    existing.source_table = block.source_table
                    existing.room_no = room.room_no
                    existing.status = status
                    existing.last_updated = timezone.now()
                    code, instance_no = generate_item_code(
                        room, master, preferred_instance=existing.instance_no, exclude_pk=existing.pk
                    )
                    existing.item_code = code
                    existing.instance_no = instance_no
                    existing.item_no = str(row.get("item_no", "")).strip() or existing.item_no
                    existing.save()
                    obj = existing
                    updated += 1
                else:
                    obj = StockItem(
                        room=room,
                        item=master,
                        item_name=master.item_name,
                        quantity=int(row["quantity"]),
                        room_no=room.room_no,
                        source_table=block.source_table,
                        status=status,
                        last_updated=timezone.now(),
                        item_no=str(row.get("item_no", "")).strip(),
                    )
                    nums = []
                    for value in StockItem.objects.filter(item=master).values_list("item_no", flat=True):
                        try:
                            nums.append(int(str(value)))
                        except (TypeError, ValueError):
                            pass
                    if not obj.item_no:
                        obj.item_no = str(max(nums, default=0) + 1)
                    code, instance_no = generate_item_code(room, master)
                    obj.item_code = code
                    obj.instance_no = instance_no
                    obj.save()
                    created += 1
                _sync_dead_stock(obj)

        messages.success(request, f"Import complete: {created} inserted, {updated} updated.")
    else:
        messages.error(request, "Please choose a valid CSV or Excel file.")
    return redirect("room_stock", mode=mode, slug=slug, floor=floor, index=index)


@login_required
def stock_export_view(request, mode, slug, floor, index, fmt):
    block = get_object_or_404(Block, slug=slug)
    room = get_object_or_404(Room, block=block, floor=floor, room_index=index)
    items = room.stock_items.all().order_by("item_code")
    fields = ["item_name", "item_code", "item_no", "quantity", "room_no", "status", "__actions__"]
    headers = ["Item Name", "Item Code", "Item No", "Quantity", "Room No", "Status", "Actions"]
    filename = f"{block.slug}_{room.room_no}_stock"
    if fmt == "excel":
        return export_queryset_excel(items, filename, fields, headers)
    return export_queryset_csv(items, filename, fields, headers)


@login_required
def stock_import_template_view(request, mode, slug, floor, index):
    """Downloadable sample CSV showing the columns a per-room import expects."""
    response = HttpResponse(sample_room_import_csv(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="room_import_template.csv"'
    return response


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
@login_required
def reports_view(request):
    form = ReportFilterForm(request.GET or None)
    items = StockItem.objects.select_related("room").all().order_by("source_table", "room_no", "item_code")

    block_value = form.data.get("block") if form.is_bound else None
    status_value = form.data.get("status") if form.is_bound else None
    item_code_query = (request.GET.get("item_code") or "").strip()

    if block_value and block_value != ReportFilterForm.ALL_BLOCKS:
        items = items.filter(source_table=block_value)
    if status_value and status_value != ReportFilterForm.ALL_STATUS:
        items = items.filter(status=status_value)
    if item_code_query:
        items = items.filter(item_code__icontains=item_code_query)

    return render(request, "stock/reports.html", {
        "form": form, "items": items, "item_code_query": item_code_query
    })


@login_required
def reports_export_view(request, fmt):
    items = StockItem.objects.all().order_by("source_table", "room_no", "item_code")

    block_value = request.GET.get("block")
    status_value = request.GET.get("status")
    item_code_query = (request.GET.get("item_code") or "").strip()
    if block_value and block_value != ReportFilterForm.ALL_BLOCKS:
        items = items.filter(source_table=block_value)
    if status_value and status_value != ReportFilterForm.ALL_STATUS:
        items = items.filter(status=status_value)
    if item_code_query:
        items = items.filter(item_code__icontains=item_code_query)

    fields = ["item_name", "item_code", "item_no", "quantity", "room_no", "status", "__actions__"]
    headers = ["Item Name", "Item Code", "Item No", "Quantity", "Room No", "Status", "Actions"]
    if fmt == "excel":
        return export_queryset_excel(items, "smce_stock_report", fields, headers)
    return export_queryset_csv(items, "smce_stock_report", fields, headers)


# ---------------------------------------------------------------------------
# ANALYSIS — pick a Block, (optionally) a Room within it and a Status, search
# by item name/code/no, and see the matching records plus a cumulative
# (total quantity / alive / dead) summary for whatever scope is selected:
#   - a single Room                      -> cumulative for that room
#   - a Block with no Room chosen        -> cumulative for the whole block,
#                                            with a per-room breakdown
#   - "All Blocks" with nothing chosen   -> cumulative across everything,
#                                            with a per-block breakdown
# ---------------------------------------------------------------------------
def _analysis_queryset(get):
    """Shared filter logic for the Analysis page and its CSV/Excel export."""
    block_value = get.get("block") or AnalysisFilterForm.ALL_BLOCKS
    floor_value = get.get("floor") or AnalysisFilterForm.ALL_FLOORS
    room_value = (get.get("room") or "").strip()
    status_value = get.get("status") or AnalysisFilterForm.ALL_STATUS
    query = (get.get("query") or "").strip()

    items = StockItem.objects.select_related("room", "room__block").all()
    room_obj = None

    if block_value and block_value != AnalysisFilterForm.ALL_BLOCKS:
        items = items.filter(source_table=block_value)
    if floor_value and floor_value != AnalysisFilterForm.ALL_FLOORS:
        items = items.filter(room__floor=floor_value)
    if room_value:
        room_obj = Room.objects.filter(pk=room_value).select_related("block").first()
        if room_obj:
            items = items.filter(room=room_obj)
    if status_value and status_value != AnalysisFilterForm.ALL_STATUS:
        items = items.filter(status=status_value)
    if query:
        items = items.filter(
            Q(item_name__icontains=query) | Q(item_code__icontains=query) | Q(item_no__icontains=query)
        )

    items = items.order_by("source_table", "room_no", "item_code")
    return items, block_value, floor_value, room_obj, status_value, query


@login_required
def analysis_view(request):
    seed_catalog()
    form = AnalysisFilterForm(request.GET or None)
    items, block_value, floor_value, room_obj, status_value, query = _analysis_queryset(request.GET)

    summary = items.aggregate(total_items=Count("id"), total_quantity=Sum("quantity"))
    alive_quantity = items.filter(status=StockItem.STATUS_ALIVE).aggregate(q=Sum("quantity"))["q"] or 0
    dead_quantity = items.filter(status=StockItem.STATUS_DEAD).aggregate(q=Sum("quantity"))["q"] or 0

    source_labels = dict(Block.SOURCE_CHOICES)
    block_breakdown = None
    room_breakdown = None

    if block_value == AnalysisFilterForm.ALL_BLOCKS:
        block_breakdown = list(
            items.values("source_table")
            .annotate(total_quantity=Sum("quantity"), total_items=Count("id"))
            .order_by("source_table")
        )
        for row in block_breakdown:
            row["label"] = source_labels.get(row["source_table"], row["source_table"])
    elif not room_obj:
        room_breakdown = list(
            items.values("room__id", "room__room_no", "room__block__name")
            .annotate(total_quantity=Sum("quantity"), total_items=Count("id"))
            .order_by("room__block__name", "room__room_no")
        )

    paginator = Paginator(items, RESULTS_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    all_rooms = Room.objects.select_related("block").order_by(
        "block__source_table", "block__name", "floor", "room_index"
    )

    # --- Chart data for the graphical dashboard (Excel/Power BI style
    # column + donut charts) — mirrors whichever breakdown is currently on
    # screen so the graphs always match the selected filters.
    chart_labels, chart_values, chart_items = [], [], []
    if block_breakdown:
        chart_labels = [row["label"] for row in block_breakdown]
        chart_values = [row["total_quantity"] or 0 for row in block_breakdown]
        chart_items = [row["total_items"] or 0 for row in block_breakdown]
    elif room_breakdown:
        chart_labels = [row["room__room_no"] for row in room_breakdown]
        chart_values = [row["total_quantity"] or 0 for row in room_breakdown]
        chart_items = [row["total_items"] or 0 for row in room_breakdown]
    elif room_obj:
        chart_labels = [room_obj.room_no]
        chart_values = [summary["total_quantity"] or 0]
        chart_items = [summary["total_items"] or 0]

    return render(request, "stock/analysis.html", {
        "form": form,
        "block_value": block_value,
        "floor_value": floor_value,
        "room_value": request.GET.get("room", ""),
        "status_value": status_value,
        "query": query,
        "page_obj": page_obj,
        "summary": summary,
        "alive_quantity": alive_quantity,
        "dead_quantity": dead_quantity,
        "block_breakdown": block_breakdown,
        "room_breakdown": room_breakdown,
        "all_rooms": all_rooms,
        "room_obj": room_obj,
        "chart_labels": chart_labels,
        "chart_values": chart_values,
        "chart_items": chart_items,
    })


@login_required
def analysis_export_view(request, fmt):
    items, *_ = _analysis_queryset(request.GET)
    fields = ["item_name", "item_code", "item_no", "quantity", "room_no", "status", "__actions__"]
    headers = ["Item Name", "Item Code", "Item No", "Quantity", "Room No", "Status", "Actions"]
    if fmt == "excel":
        return export_queryset_excel(items, "smce_analysis_export", fields, headers)
    return export_queryset_csv(items, "smce_analysis_export", fields, headers)


# ---------------------------------------------------------------------------
# Dead Stock
# ---------------------------------------------------------------------------
@login_required
def dead_stock_view(request):
    form = DeadStockFilterForm(request.GET or None)
    records = DeadStock.objects.all().order_by("-recorded_at")

    source_value = request.GET.get("source_table")
    query = request.GET.get("query", "").strip()
    item_code_query = request.GET.get("item_code", "").strip()

    if source_value and source_value != DeadStockFilterForm.ALL_BLOCKS:
        records = records.filter(source_table=source_value)
    if query:
        records = records.filter(
            Q(item_name__icontains=query) | Q(item_code__icontains=query)
            | Q(item_no__icontains=query) | Q(room_no__icontains=query)
        )
    if item_code_query:
        records = records.filter(item_code__icontains=item_code_query)

    return render(request, "stock/dead_stock.html", {
        "form": form, "records": records, "item_code_query": item_code_query
    })


@login_required
def dead_stock_export_view(request, fmt):
    records = DeadStock.objects.all().order_by("-recorded_at")
    source_value = request.GET.get("source_table")
    query = request.GET.get("query", "").strip()
    item_code_query = request.GET.get("item_code", "").strip()
    if source_value and source_value != DeadStockFilterForm.ALL_BLOCKS:
        records = records.filter(source_table=source_value)
    if query:
        records = records.filter(
            Q(item_name__icontains=query) | Q(item_code__icontains=query)
            | Q(item_no__icontains=query) | Q(room_no__icontains=query)
        )
    if item_code_query:
        records = records.filter(item_code__icontains=item_code_query)

    fields = ["item_name", "item_code", "item_no", "quantity", "room_no", "status", "__actions__"]
    headers = ["Item Name", "Item Code", "Item No", "Quantity", "Room No", "Status", "Actions"]
    if fmt == "excel":
        return export_queryset_excel(records, "smce_dead_stock", fields, headers)
    return export_queryset_csv(records, "smce_dead_stock", fields, headers)
