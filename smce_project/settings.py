"""
Django settings for SMCE Stock Management project.
All sensitive/environment-specific values are read from a `.env` file
via python-decouple, so nothing secret is hard-coded here.
"""

from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY", default="dev-only-insecure-secret-key")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="127.0.0.1,localhost", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "stock.apps.StockConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "smce_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "smce_project.wsgi.application"

# ---------------------------------------------------------------------------
# Database — Supabase (PostgreSQL).
#
# Supabase gives you a standard Postgres connection string. We support two
# ways of configuring it:
#   1. Set DATABASE_URL to the full connection string Supabase shows you
#      (Project Settings -> Database -> Connection string -> URI). This is
#      the simplest option and is what the .env.example file uses.
#   2. Or set the individual DB_* variables below if you prefer that style.
#
# Use the "Session pooler" (port 5432) or "Transaction pooler" (port 6543)
# connection string from Supabase rather than the direct "db.<ref>.supabase.co"
# host — the pooler works reliably from serverless/free hosts (Render,
# Railway, PythonAnywhere, etc.) where the direct connection is often
# IPv6-only and unreachable.
# ---------------------------------------------------------------------------
import dj_database_url

DATABASE_URL = config("DATABASE_URL", default="")

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("DB_NAME", default="postgres"),
            "USER": config("DB_USER", default="postgres"),
            "PASSWORD": config("DB_PASSWORD", default=""),
            "HOST": config("DB_HOST", default="127.0.0.1"),
            "PORT": config("DB_PORT", default="5432"),
            "OPTIONS": {
                "sslmode": config("DB_SSLMODE", default="require"),
            },
            "CONN_MAX_AGE": 600,
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 6}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom user model (adds Role: Admin / Staff)
AUTH_USER_MODEL = "stock.Member"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# Max upload size guard for CSV/Excel imports (5 MB)
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
