# Connecting SMCE Stock Management to Supabase — Exact Steps

This project now uses **Supabase's PostgreSQL database** instead of MySQL.
Supabase does not require any special SDK for this app — Django talks to it
exactly like any other Postgres database, over a normal connection string.
Follow these steps in order.

---

## Step 1 — Create a free Supabase account and project

1. Go to https://supabase.com and sign up (GitHub or email login).
2. Click **New project**.
3. Fill in:
   - **Name**: e.g. `smce-stock-management`
   - **Database Password**: choose a strong password and **save it somewhere safe** — you will need it in Step 3 and Supabase will not show it again.
   - **Region**: pick the one closest to you/your users (e.g. Mumbai/`ap-south-1` if you're in India).
4. Click **Create new project** and wait 1–2 minutes while Supabase provisions it.

## Step 2 — Get your connection string

1. In your new project, go to **Project Settings** (gear icon, bottom of the left sidebar) → **Database**.
2. Scroll to **Connection string** and select the **URI** tab.
3. Choose **Session pooler** (recommended for most free hosts) — you'll see something like:

   ```
   postgresql://postgres.abcdefghijklmno:[YOUR-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:5432/postgres
   ```

   > Use the **pooler** host (contains `pooler.supabase.com`), not the direct `db.<project-ref>.supabase.co` host. The direct host is IPv6-only and is unreachable from many free hosting platforms and some home networks; the pooler works everywhere.
   > If your host requires it, use the **Transaction pooler** string instead (port `6543`) — it's the same format, just a different port, and works with this project either way since it doesn't use long-lived transactions across requests.

4. Copy the full string and replace `[YOUR-PASSWORD]` with the real database password from Step 1.

## Step 3 — Configure the project

1. In the project folder, copy the example env file:

   ```bash
   cp .env.example .env
   ```

2. Open `.env` and set:

   ```env
   SECRET_KEY=generate-a-long-random-string-here
   DEBUG=True
   ALLOWED_HOSTS=127.0.0.1,localhost

   DATABASE_URL=postgresql://postgres.abcdefghijklmno:YOUR_REAL_PASSWORD@aws-0-ap-south-1.pooler.supabase.com:5432/postgres
   ```

   (Generate a `SECRET_KEY` with, e.g., `python -c "import secrets; print(secrets.token_urlsafe(50))"`.)

## Step 4 — Install dependencies

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

This installs `psycopg2-binary` (the PostgreSQL driver) and `dj-database-url`
(parses `DATABASE_URL` into Django's `DATABASES` setting) in place of the old
`mysqlclient`.

## Step 5 — Create the tables in Supabase

Run Django's normal migration commands — these create every table
(`Member`, `BlockNode`, `Rooms`, `SystemItem`, `StockItem`, `DeadStock`,
`TransferHistory`, plus Django's built-in auth/session tables) directly
inside your Supabase Postgres database:

```bash
python manage.py migrate
python manage.py initstock --admin-username admin --admin-password "ChangeMe123!" --admin-fullname "System Administrator"
```

You can open **Table Editor** in the Supabase dashboard afterward and see
all the tables listed there.

## Step 6 — Run the app

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` — the app now reads and writes through
Supabase instead of MySQL. Everything else (login, dashboard, stock
management, reports, dead stock, transfers) works exactly as before; only
the database engine changed.

---

## Migrating existing data from MySQL (optional)

If you already have real stock data in the old MySQL database and want to
carry it over instead of starting fresh in Supabase:

1. With the project still pointed at MySQL (old `.env`), export your data:
   ```bash
   python manage.py dumpdata stock auth --natural-foreign --natural-primary -o old_data.json
   ```
2. Switch `.env` to your Supabase `DATABASE_URL` (Step 3 above).
3. Create the empty schema in Supabase:
   ```bash
   python manage.py migrate
   ```
4. Load the exported data into Supabase:
   ```bash
   python manage.py loaddata old_data.json
   ```

If you don't need the old data, just skip this section and run Step 5 above
on a fresh Supabase database.

## Deploying for free (optional)

Since Supabase only hosts the database, you still need somewhere to run the
Django app itself. Free options that work well with this setup:
- **Render** (free web service tier) — set `DATABASE_URL` and `SECRET_KEY` as environment variables in the Render dashboard.
- **Railway** — same idea, environment variables in the project settings.
- **PythonAnywhere** (free tier) — set the same environment variables, or edit `.env` directly on the server.

In all cases: set `DEBUG=False`, put your real domain in `ALLOWED_HOSTS`,
and use the same Supabase `DATABASE_URL` — Supabase is reachable from the
public internet, so no extra networking setup is needed on the database
side.

## Common issues

| Problem | Fix |
|---|---|
| `password authentication failed` | Re-check the password you pasted into `DATABASE_URL` — it's the database password from Step 1, not your Supabase login. |
| Connection times out | You're likely using the direct `db.<ref>.supabase.co` host instead of the pooler host — switch to the pooler string from Step 2. |
| Works locally, fails on host | Free Supabase projects **pause after a week of no activity** — open the Supabase dashboard once to resume it, then redeploy/restart your app. |
| `django.db.utils.OperationalError: FATAL: too many connections` | Use the pooler connection string (Step 2), which is designed for exactly this — many short-lived Django connections. |
