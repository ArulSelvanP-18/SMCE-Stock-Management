# SMCE STOCK MANAGEMENT — Windows Setup & Execution

## Supported local stack

- Windows 10/11 64-bit
- Python 3.14.x
- A free Supabase project (PostgreSQL) — see SUPABASE_SETUP.md
- Django 5.2.17
- psycopg2-binary 2.9.10
- dj-database-url 2.3.0
- pandas 2.3.3
- openpyxl 3.1.5
- python-decouple 3.8

Django 5.2.17 is used because the 5.2 LTS line supports Python 3.14. The supplied `requirements.txt` pins every application dependency so the same versions are installed each time.

## 1. Open PowerShell in the project folder

```powershell
cd "C:\path\to\SMCE_STOCK_MANAGEMENT_MYSQL_FINAL"
```

## 2. Create the virtual environment with Python 3.14

```powershell
py -3.14 -m venv .venv
```

If `py -3.14` is not recognized, install Python 3.14.x first and then reopen PowerShell.

## 3. Activate the environment

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, you do **not** need to change the system policy. Run the project directly through the venv Python instead:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then use `\.venv\Scripts\python.exe` for all `manage.py` commands below.

## 4. Install the exact package versions

With the venv activated:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Verify:

```powershell
python -c "import django, psycopg2, pandas, openpyxl, decouple; print('Django', django.get_version()); print('psycopg2', psycopg2.__version__); print('pandas', pandas.__version__); print('openpyxl', openpyxl.__version__)"
```

## 5. Create your Supabase project and database

Follow **SUPABASE_SETUP.md** to create a free Supabase project and copy its
connection string. No manual `CREATE DATABASE` step is needed — Supabase
already gives you a ready `postgres` database; Django's `migrate` creates
all the tables inside it.

## 6. Create `.env`

Copy `.env.example` to `.env` in the project root and paste your real
Supabase connection string:

```text
SECRET_KEY=replace-with-a-long-random-secret
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

DATABASE_URL=postgresql://postgres.xxxxxxxxxxxx:YOUR_PASSWORD@aws-0-ap-south-1.pooler.supabase.com:5432/postgres
```

## 7. Run the safe Django checks

```powershell
python manage.py check
python manage.py makemigrations --check
python manage.py showmigrations
```

The project already contains the Item Code automation migration (`0005_item_code_automation`). Do **not** delete migration files.

## 8. Apply migrations

For a new database:

```powershell
python manage.py migrate
python manage.py initstock --admin-username admin --admin-password "ChangeMe123!" --admin-fullname "System Administrator"
```

For an existing database, back it up first and then run:

```powershell
python manage.py migrate
```

The migrations are designed to preserve existing stock records. Never run `flush`, never delete the database, and never delete migration files as a shortcut for migration errors.

## 9. Start the application

```powershell
python manage.py runserver
```

Open:

`http://127.0.0.1:8000/`

## 10. Test the Item Code workflow

In **SYSTEM CONTROL**, create for example:

```text
Item Name: Computer
Item Code: CMP
```

Then open a room and insert a Computer. Example result:

```text
ADMIN-GF-05-CMP-01
```

Insert a second Computer in the same room:

```text
ADMIN-GF-05-CMP-02
```

Move the first record to Engineering / First Floor / Room 12:

```text
ENG-FF-12-CMP-01
```

Change Computer to Printer (`PTR`):

```text
ENG-FF-12-PTR-01
```

## 11. Dead Stock history

When an item becomes DEAD, a DeadStock snapshot is created. If the current StockItem is later moved or its System Control code changes, the historical DeadStock Item Code/location is **not rewritten**.

## 12. Report / Dead Stock search

Both pages contain **Search by Item Code** and **CLEAR / RESET**. Exact complete codes work, and the backend query also permits partial matching.

## 13. Run automated tests

```powershell
python manage.py test stock
```

## 14. Common Windows problems

### `psycopg2` installation error

Use Python 3.14.x and this project's pinned `psycopg2-binary==2.9.10` (the "binary" build ships precompiled wheels, so it needs no local PostgreSQL headers/compiler on Windows).

### PowerShell says script execution is disabled

Skip activation and use:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py runserver
```

### `password authentication failed` / connection refused / timeout

- Double-check the password in `DATABASE_URL` (it's the *database* password you set when creating the Supabase project, not your Supabase account login password).
- Make sure you copied the **pooler** connection string (host contains `pooler.supabase.com`), not the direct `db.<ref>.supabase.co` host — the direct host is IPv6-only and often unreachable from home/office networks and free hosting providers.
- Confirm the project is not paused (free Supabase projects pause after a week of inactivity — open the Supabase dashboard to resume it).

### `No changes detected` from `makemigrations`

That is normal when the model definitions already match the migration files. Use:

```powershell
python manage.py makemigrations --check
```

and then:

```powershell
python manage.py migrate
```
