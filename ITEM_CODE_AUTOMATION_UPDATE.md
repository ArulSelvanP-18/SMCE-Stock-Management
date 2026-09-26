# SMCE Stock Management — Item Code Automation Update

## Generated format

`BLOCK-FLOOR-ROOM-SYSTEM_CONTROL_CODE-INSTANCE`

Examples:
- `ADMIN-GF-05-CMP-01`
- `ADMIN-GF-05-CMP-02`
- `ENG-FF-12-PTR-01`

## Backend rules

- Item Code is never accepted as the source of truth from the browser.
- `SystemItem` is resolved from Item Name.
- Block/Floor/Room are taken from the current `Room`.
- `instance_no` provides the stable physical-instance suffix.
- `StockItem.item_code` is globally unique at the database level.
- Insert, edit, System Control changes and transfers regenerate codes.
- Transfer operations use database transactions and row/master locking.
- Dead Stock is an immutable historical snapshot: later location moves, quantity edits, Item Name changes, and System Control code changes do not rewrite the recorded Item Code/location.
- Existing stock data is upgraded by migration `0005_item_code_automation`.
- Report and Dead Stock pages provide dedicated Item Code search plus reset.
- Old import files containing `item_code` remain accepted, but imported codes are not trusted.

## Verification

All Python source files pass `compileall`. The build environment used for this package
does not provide network access to install Django/PostgreSQL client wheels, so database-backed
Django tests cannot be executed here. Run the following inside the project's normal
Python 3.14 + Supabase (PostgreSQL) environment:

```powershell
python manage.py check
python manage.py makemigrations --check
python manage.py migrate
python manage.py test stock
```

For an existing Supabase/PostgreSQL database, take a backup before applying migration `0005`.
