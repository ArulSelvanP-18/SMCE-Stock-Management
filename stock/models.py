"""
SMCE Stock Management — data models.

Design note on normalization:
The original spec calls for separate tables per block
(AdministrativeBlock, EngandTech1, EngandTech2, EngandTech3, BoysHostel,
GirlsHostel, plus Rooms and DeadStock). Because every one of those tables
shares an identical schema (Item_code, Item_no, Item_name, Quantity,
Room_no, Status), duplicating the table six times would violate normal
form and make search/report/dead-stock queries across blocks require
six-way UNIONs. Instead we keep ONE StockItem table with a `source_table`
field holding the literal historical table name (e.g. "AdministrativeBlock",
"EngandTech1", ...), which is exactly the value the spec's Report and
Dead Stock screens already expect to see in a `Source_table` column.
This preserves 100% of the required behaviour (per-block screens, per-block
counts, "Source_table" reporting) while avoiding duplicate schemas.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import RegexValidator
from django.utils import timezone


# ---------------------------------------------------------------------------
# Member / authentication
# ---------------------------------------------------------------------------
class Member(AbstractUser):
    """Custom user model backing the Member table (login/registration)."""

    ROLE_ADMIN = "Admin"
    ROLE_STAFF = "Staff"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_STAFF, "Staff"),
    ]

    full_name = models.CharField(max_length=150)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_STAFF)
    contact_number = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "Member"
        verbose_name = "Member"
        verbose_name_plural = "Members"

    def __str__(self):
        return f"{self.full_name} ({self.username})"

    @property
    def is_admin_role(self):
        return self.role == self.ROLE_ADMIN


# ---------------------------------------------------------------------------
# Block / floor / room hierarchy
# ---------------------------------------------------------------------------
class Block(models.Model):
    """
    Top-level and mid-level navigation nodes: Administrative Block,
    Eng & Tech Block 1/2/3 (and their departments), Boys/Girls Hostel,
    Auditorium. A department (e.g. "Computer Science Engineering") is
    modeled as a Block with parent=Eng and Tech Block 2, mirroring the
    spec's navigation: Block2 -> Department -> Floor -> Room.
    """

    SOURCE_ADMINISTRATIVE = "AdministrativeBlock"
    SOURCE_ENGTECH1 = "EngandTech1"
    SOURCE_ENGTECH2 = "EngandTech2"
    SOURCE_ENGTECH3 = "EngandTech3"
    SOURCE_BOYS_HOSTEL = "BoysHostel"
    SOURCE_GIRLS_HOSTEL = "GirlsHostel"
    SOURCE_AUDITORIUM = "Auditorium"
    SOURCE_CHOICES = [
        (SOURCE_ADMINISTRATIVE, "Administrative Block"),
        (SOURCE_ENGTECH1, "Eng and Tech Block 1 — Science and Humanities"),
        (SOURCE_ENGTECH2, "Eng and Tech Block 2 — Major Engineering Block"),
        (SOURCE_ENGTECH3, "Eng and Tech Block 3 — Mechanical Block"),
        (SOURCE_BOYS_HOSTEL, "Boys Hostel"),
        (SOURCE_GIRLS_HOSTEL, "Girls Hostel"),
        (SOURCE_AUDITORIUM, "Auditorium"),
    ]

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True)
    source_table = models.CharField(max_length=40, choices=SOURCE_CHOICES)
    parent = models.ForeignKey(
        "self", null=True, blank=True, related_name="children", on_delete=models.CASCADE
    )
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "BlockNode"
        ordering = ["source_table", "name"]

    def __str__(self):
        return self.name

    @property
    def is_top_level(self):
        return self.parent_id is None


class Room(models.Model):
    """The Rooms table — room metadata within a block/department + floor."""

    FLOOR_UNDERGROUND = "UG"
    FLOOR_GROUND = "G"
    FLOOR_FIRST = "FF"
    FLOOR_SECOND = "SF"
    FLOOR_CHOICES = [
        (FLOOR_UNDERGROUND, "Underground Floor"),
        (FLOOR_GROUND, "Ground Floor"),
        (FLOOR_FIRST, "First Floor"),
        (FLOOR_SECOND, "Second Floor"),
    ]

    block = models.ForeignKey(Block, related_name="rooms", on_delete=models.CASCADE)
    floor = models.CharField(max_length=2, choices=FLOOR_CHOICES)
    room_index = models.PositiveSmallIntegerField(help_text="1 through 10")
    room_no = models.CharField(
        max_length=20,
        help_text="Format like UG-1, G-1, FF-1, SF-1",
        validators=[RegexValidator(r"^(UG|G|FF|SF)-\d+$", "Room number must look like UG-1, G-1, FF-1 or SF-1.")],
    )
    room_name = models.CharField(max_length=150, blank=True)
    room_id = models.CharField(max_length=50, blank=True, help_text="Optional custom room ID")
    auto_update_db = models.BooleanField(
        default=True, help_text="Update these changes in the database automatically"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "Rooms"
        unique_together = ("block", "floor", "room_index")
        ordering = ["block", "floor", "room_index"]
        indexes = [
            models.Index(fields=["room_no"]),
        ]

    def __str__(self):
        return f"{self.block.name} / {self.get_floor_display()} / {self.room_no}"

    def save(self, *args, **kwargs):
        if not self.room_no:
            self.room_no = f"{self.floor}-{self.room_index}"
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Central Item Master / System Control
# ---------------------------------------------------------------------------
class SystemItem(models.Model):
    """Central master/reference for the Item Name + Item Code pair."""

    item_name = models.CharField(max_length=200)
    item_code = models.CharField(max_length=50, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "SystemItem"
        ordering = ["item_name", "item_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["item_name", "item_code"],
                name="systemitem_name_code_unique",
            )
        ]

    def __str__(self):
        return f"{self.item_name} ({self.item_code})"


# ---------------------------------------------------------------------------
# Stock items (per-room stock rows) — one physical table, `source_table`
# preserves the "which original block table" concept the spec requires.
# ---------------------------------------------------------------------------
class StockItem(models.Model):
    STATUS_ALIVE = "ALIVE"
    STATUS_REPAIR = "REPAIR"
    STATUS_DEAD = "DEAD"
    STATUS_CHOICES = [
        (STATUS_ALIVE, "ALIVE"),
        (STATUS_REPAIR, "REPAIR"),
        (STATUS_DEAD, "DEAD"),
    ]

    room = models.ForeignKey(Room, related_name="stock_items", on_delete=models.CASCADE)
    item = models.ForeignKey(
        SystemItem, null=True, blank=True, related_name="stock_records",
        on_delete=models.PROTECT, db_index=True,
    )
    source_table = models.CharField(max_length=40, choices=Block.SOURCE_CHOICES)
    item_code = models.CharField(max_length=100, unique=True, db_index=True)
    # Stable physical-instance sequence used by the generated Item Code.
    # It is deliberately separate from Item No, which is an existing user-facing
    # stock sequence and must remain backward compatible.
    instance_no = models.PositiveIntegerField(default=1, db_index=True)
    item_no = models.CharField(max_length=50, db_index=True)
    item_name = models.CharField(max_length=200, db_index=True)
    quantity = models.PositiveIntegerField(default=0)
    room_no = models.CharField(max_length=20, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ALIVE, db_index=True)
    # User-visible date for insertion/update/transfer operations.
    # It is deliberately a DateField so the UI can provide a calendar picker.
    last_updated = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "StockItem"
        unique_together = ("room", "item_code")
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["source_table"]),
            models.Index(fields=["status"]),
            models.Index(fields=["item_code"]),
            models.Index(fields=["item_name"]),
            models.Index(fields=["room_no"]),
        ]

    def __str__(self):
        return f"{self.item_name} ({self.item_code}) — {self.room_no}"


class TransferHistory(models.Model):
    """Audit trail for every quantity transfer between stock locations."""

    item = models.ForeignKey(
        SystemItem, on_delete=models.PROTECT, related_name="transfers"
    )
    source_block = models.CharField(max_length=150)
    source_floor = models.CharField(max_length=50)
    source_room = models.CharField(max_length=50)
    destination_block = models.CharField(max_length=150)
    destination_floor = models.CharField(max_length=50)
    destination_room = models.CharField(max_length=50)
    quantity = models.PositiveIntegerField()
    transferred_at = models.DateTimeField(auto_now_add=True)
    transferred_by = models.ForeignKey(
        Member, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="stock_transfers"
    )

    class Meta:
        db_table = "TransferHistory"
        ordering = ["-transferred_at"]

    def __str__(self):
        return f"{self.item.item_name} — {self.quantity} transferred"


class DeadStock(models.Model):
    """Snapshot recorded automatically whenever a StockItem flips to Dead."""

    stock_item = models.ForeignKey(
        StockItem, null=True, blank=True, related_name="dead_records", on_delete=models.SET_NULL
    )
    item_code = models.CharField(max_length=100, db_index=True)
    item_no = models.CharField(max_length=50)
    item_name = models.CharField(max_length=200, db_index=True)
    quantity = models.PositiveIntegerField(default=0)
    room_no = models.CharField(max_length=20, db_index=True)
    status = models.CharField(max_length=10, default=StockItem.STATUS_DEAD)
    source_table = models.CharField(max_length=40, choices=Block.SOURCE_CHOICES, db_index=True)
    last_updated = models.DateTimeField(default=timezone.now)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "DeadStock"
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"[DEAD] {self.item_name} ({self.item_code})"
