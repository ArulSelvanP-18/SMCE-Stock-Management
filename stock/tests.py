from django.test import TestCase
from django.urls import reverse

from .item_codes import generate_item_code
from .models import Member, Block, Room, SystemItem, StockItem, DeadStock


class ItemCodeAutomationTests(TestCase):
    def setUp(self):
        self.block = Block.objects.create(
            name="Administrative Block",
            slug="test-admin",
            source_table=Block.SOURCE_ADMINISTRATIVE,
        )
        self.eng = Block.objects.create(
            name="Eng and Tech Block",
            slug="test-eng",
            source_table=Block.SOURCE_ENGTECH1,
        )
        self.room = Room.objects.create(
            block=self.block, floor=Room.FLOOR_GROUND,
            room_index=5, room_no="G-5", room_name="Test Room"
        )
        self.eng_room = Room.objects.create(
            block=self.eng, floor=Room.FLOOR_FIRST,
            room_index=12, room_no="FF-12", room_name="Engineering Room"
        )
        self.computer = SystemItem.objects.create(item_name="Computer", item_code="CMP")
        self.printer = SystemItem.objects.create(item_name="Printer", item_code="PTR")

    def test_new_codes_are_location_based_and_sequential(self):
        code1, n1 = generate_item_code(self.room, self.computer)
        self.assertEqual(code1, "ADMIN-GF-05-CMP-01")
        self.assertEqual(n1, 1)

        StockItem.objects.create(
            room=self.room, item=self.computer, source_table=self.block.source_table,
            item_code=code1, instance_no=n1, item_no="1", item_name="Computer",
            quantity=1, room_no=self.room.room_no,
        )
        code2, n2 = generate_item_code(self.room, self.computer)
        self.assertEqual(code2, "ADMIN-GF-05-CMP-02")
        self.assertEqual(n2, 2)

    def test_move_regenerates_location_but_preserves_instance_when_available(self):
        code, n = generate_item_code(self.room, self.computer)
        item = StockItem.objects.create(
            room=self.room, item=self.computer, source_table=self.block.source_table,
            item_code=code, instance_no=n, item_no="1", item_name="Computer",
            quantity=1, room_no=self.room.room_no,
        )
        item.room = self.eng_room
        code2, n2 = generate_item_code(self.eng_room, self.computer, n, item.pk)
        self.assertEqual(code2, "ENG-FF-12-CMP-01")
        self.assertEqual(n2, 1)

    def test_item_name_change_uses_new_system_control_code(self):
        code, n = generate_item_code(self.room, self.computer)
        item = StockItem.objects.create(
            room=self.room, item=self.computer, source_table=self.block.source_table,
            item_code=code, instance_no=n, item_no="1", item_name="Computer",
            quantity=1, room_no=self.room.room_no,
        )
        item.item = self.printer
        code2, n2 = generate_item_code(self.room, self.printer, item.instance_no, item.pk)
        self.assertEqual(code2, "ADMIN-GF-05-PTR-01")
        self.assertEqual(n2, 1)


class DeadStockHistoryTests(TestCase):
    def setUp(self):
        self.block = Block.objects.create(
            name="Administrative Block",
            slug="dead-admin",
            source_table=Block.SOURCE_ADMINISTRATIVE,
        )
        self.eng = Block.objects.create(
            name="Eng and Tech Block",
            slug="dead-eng",
            source_table=Block.SOURCE_ENGTECH1,
        )
        self.room = Room.objects.create(
            block=self.block, floor=Room.FLOOR_GROUND,
            room_index=5, room_no="G-5", room_name="Dead Source"
        )
        self.new_room = Room.objects.create(
            block=self.eng, floor=Room.FLOOR_FIRST,
            room_index=12, room_no="FF-12", room_name="Dead Destination"
        )
        self.computer = SystemItem.objects.create(item_name="Computer", item_code="CMP")

    def _create_dead(self):
        code, n = generate_item_code(self.room, self.computer)
        item = StockItem.objects.create(
            room=self.room, item=self.computer,
            source_table=self.block.source_table,
            item_code=code, instance_no=n, item_no="1",
            item_name="Computer", quantity=1, room_no=self.room.room_no,
            status=StockItem.STATUS_DEAD,
        )
        from .views import _sync_dead_stock
        _sync_dead_stock(item)
        return item

    def test_dead_snapshot_is_not_rewritten_when_stock_moves(self):
        item = self._create_dead()
        snapshot = DeadStock.objects.get(stock_item=item)
        original_code = snapshot.item_code
        original_room = snapshot.room_no

        item.room = self.new_room
        item.source_table = self.new_room.block.source_table
        item.room_no = self.new_room.room_no
        new_code, new_instance = generate_item_code(
            self.new_room, self.computer,
            preferred_instance=item.instance_no,
            exclude_pk=item.pk,
        )
        item.item_code = new_code
        item.instance_no = new_instance
        item.save()

        from .views import _sync_dead_stock
        _sync_dead_stock(item)
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.item_code, original_code)
        self.assertEqual(snapshot.room_no, original_room)
        self.assertEqual(item.item_code, "ENG-FF-12-CMP-01")

    def test_dead_snapshot_is_removed_when_item_becomes_alive(self):
        item = self._create_dead()
        self.assertTrue(DeadStock.objects.filter(stock_item=item).exists())
        item.status = StockItem.STATUS_ALIVE
        item.save(update_fields=["status", "updated_at"])
        from .views import _sync_dead_stock
        _sync_dead_stock(item)
        self.assertFalse(DeadStock.objects.filter(stock_item=item).exists())


class SearchTests(TestCase):
    def setUp(self):
        self.user = Member.objects.create_user(
            username="admin", password="AdminPass123!", full_name="Admin", role=Member.ROLE_ADMIN
        )
        self.block = Block.objects.create(
            name="Administrative Block", slug="search-admin",
            source_table=Block.SOURCE_ADMINISTRATIVE,
        )
        self.room = Room.objects.create(
            block=self.block, floor=Room.FLOOR_GROUND,
            room_index=5, room_no="G-5", room_name="Search Room"
        )
        self.master = SystemItem.objects.create(item_name="Computer", item_code="CMP")
        self.code, self.instance = generate_item_code(self.room, self.master)
        self.item = StockItem.objects.create(
            room=self.room, item=self.master, source_table=self.block.source_table,
            item_code=self.code, instance_no=self.instance, item_no="1",
            item_name="Computer", quantity=1, room_no=self.room.room_no,
        )
        self.client.force_login(self.user)

    def test_report_item_code_search(self):
        response = self.client.get(reverse("reports"), {"item_code": self.item.item_code})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.item.item_code)

    def test_dead_stock_item_code_search(self):
        self.item.status = StockItem.STATUS_DEAD
        self.item.save(update_fields=["status", "updated_at"])
        from .views import _sync_dead_stock
        _sync_dead_stock(self.item)
        response = self.client.get(reverse("dead_stock"), {"item_code": self.item.item_code})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.item.item_code)
