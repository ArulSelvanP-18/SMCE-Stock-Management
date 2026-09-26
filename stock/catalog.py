"""
Static navigation catalog for the block -> (department) -> floor -> room
hierarchy. This drives auto-creation of Block rows (via the `initstock`
management command / migrations seed) and the Modify/View navigation
templates, keeping the tree definition in one readable place.
"""

from .models import Block, Room

FLOORS_STANDARD = [Room.FLOOR_GROUND, Room.FLOOR_FIRST, Room.FLOOR_SECOND]
FLOORS_WITH_UNDERGROUND = [Room.FLOOR_UNDERGROUND, Room.FLOOR_GROUND, Room.FLOOR_FIRST, Room.FLOOR_SECOND]
ROOMS_PER_FLOOR = 10

# Each top-level entry: (name, slug, source_table, floors, [child departments])
# A child department: (name, slug, floors)
CATALOG = [
    {
        "name": "Administrative Block",
        "slug": "administrative-block",
        "source_table": Block.SOURCE_ADMINISTRATIVE,
        "floors": FLOORS_STANDARD,
        "children": [],
    },
    {
        "name": "Eng and Tech Block 1 — Science and Humanities",
        "slug": "eng-tech-block-1",
        "source_table": Block.SOURCE_ENGTECH1,
        "floors": FLOORS_STANDARD,
        "children": [],
    },
    {
        "name": "Eng and Tech Block 2 — Major Engineering Block",
        "slug": "eng-tech-block-2",
        "source_table": Block.SOURCE_ENGTECH2,
        "floors": [],  # floors live under each department
        "children": [
            {"name": "Artificial Intelligence and Data Science", "slug": "aids", "floors": FLOORS_WITH_UNDERGROUND},
            {"name": "Computer Science Engineering", "slug": "cse", "floors": FLOORS_WITH_UNDERGROUND},
            {"name": "Electronics and Communication Engineering", "slug": "ece", "floors": FLOORS_WITH_UNDERGROUND},
            {"name": "Electrical and Electronics Engineering", "slug": "eee", "floors": FLOORS_WITH_UNDERGROUND},
            {"name": "Civil Engineering", "slug": "civil", "floors": FLOORS_WITH_UNDERGROUND},
        ],
    },
    {
        "name": "Eng and Tech Block 3 — Mechanical Block",
        "slug": "eng-tech-block-3",
        "source_table": Block.SOURCE_ENGTECH3,
        "floors": FLOORS_STANDARD,
        "children": [],
    },
    {
        "name": "Boys Hostel",
        "slug": "boys-hostel",
        "source_table": Block.SOURCE_BOYS_HOSTEL,
        "floors": FLOORS_STANDARD,
        "children": [],
    },
    {
        "name": "Girls Hostel",
        "slug": "girls-hostel",
        "source_table": Block.SOURCE_GIRLS_HOSTEL,
        "floors": FLOORS_STANDARD,
        "children": [],
    },
    {
        "name": "Auditorium",
        "slug": "auditorium",
        "source_table": Block.SOURCE_AUDITORIUM,
        "floors": FLOORS_STANDARD,
        "children": [],
    },
]


def seed_catalog():
    """Idempotently create Block rows (and their departments) from CATALOG."""
    for entry in CATALOG:
        top, _ = Block.objects.get_or_create(
            slug=entry["slug"],
            defaults={
                "name": entry["name"],
                "source_table": entry["source_table"],
                "parent": None,
            },
        )
        for child in entry.get("children", []):
            Block.objects.get_or_create(
                slug=f"{entry['slug']}-{child['slug']}",
                defaults={
                    "name": child["name"],
                    "source_table": entry["source_table"],
                    "parent": top,
                },
            )


def floors_for_block(block: Block):
    """Return the ordered list of floor codes available for this block node."""
    for entry in CATALOG:
        if entry["slug"] == block.slug:
            return entry["floors"]
        for child in entry.get("children", []):
            if f"{entry['slug']}-{child['slug']}" == block.slug:
                return child["floors"]
    # Fallback: standard 3 floors
    return FLOORS_STANDARD
