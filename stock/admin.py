from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db import transaction

from .item_codes import generate_item_code, regenerate_all_for_system_item
from .models import Member, Block, Room, SystemItem, StockItem, DeadStock, TransferHistory
from .views import _sync_dead_stock


@admin.register(Member)
class MemberAdmin(UserAdmin):
    list_display = ("username", "full_name", "role", "is_staff", "is_superuser")
    fieldsets = UserAdmin.fieldsets + (
        ("SMCE Profile", {"fields": ("full_name", "role", "contact_number")}),
    )


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "source_table", "parent")
    list_filter = ("source_table",)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("room_no", "block", "floor", "room_name", "auto_update_db")
    list_filter = ("block", "floor")
    search_fields = ("room_no", "room_name", "room_id")


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ("item_code", "item_name", "room_no", "status", "source_table", "quantity")
    list_filter = ("source_table", "status")
    search_fields = ("item_code", "item_no", "item_name", "room_no")
    readonly_fields = ("item_code", "instance_no", "item_name", "source_table", "room_no")

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        """Keep Django Admin on the same Item Code rules as the main UI."""
        if not obj.room_id or not obj.item_id:
            raise ValueError("Stock Item requires both a Room and a System Control item.")
        master = SystemItem.objects.select_for_update().get(pk=obj.item_id)
        preferred = obj.instance_no if change and obj.instance_no else None
        code, instance_no = generate_item_code(
            obj.room, master,
            preferred_instance=preferred,
            exclude_pk=obj.pk if change else None,
        )
        obj.item = master
        obj.item_name = master.item_name
        obj.item_code = code
        obj.instance_no = instance_no
        obj.source_table = obj.room.block.source_table
        obj.room_no = obj.room.room_no
        super().save_model(request, obj, form, change)
        _sync_dead_stock(obj)


@admin.register(DeadStock)
class DeadStockAdmin(admin.ModelAdmin):
    list_display = ("item_code", "item_name", "room_no", "source_table", "recorded_at")
    list_filter = ("source_table",)
    search_fields = ("item_code", "item_name", "room_no")
    readonly_fields = tuple(field.name for field in DeadStock._meta.fields)


@admin.register(SystemItem)
class SystemItemAdmin(admin.ModelAdmin):
    list_display = ("item_name", "item_code", "created_at", "updated_at")
    search_fields = ("item_name", "item_code")

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        """Regenerate current stock codes after a System Control edit."""
        super().save_model(request, obj, form, change)
        regenerate_all_for_system_item(
            SystemItem.objects.select_for_update().get(pk=obj.pk)
        )


@admin.register(TransferHistory)
class TransferHistoryAdmin(admin.ModelAdmin):
    list_display = ("item", "quantity", "source_block", "source_room", "destination_block", "destination_room", "transferred_at", "transferred_by")
    list_filter = ("source_block", "destination_block", "transferred_at")
    search_fields = ("item__item_name", "item__item_code", "source_room", "destination_room")
    readonly_fields = ("transferred_at",)
