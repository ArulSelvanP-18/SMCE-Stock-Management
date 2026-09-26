"""
Django settings for SMCE Stock Management project.

Production-ready configuration for:
- Local development
- Render deployment
- Supabase PostgreSQL
- WhiteNoise static files
- Environment variables using python-decouple
"""

from pathlib import Path
import os

from decouple import config, Csv
import dj_database_url


# ============================================================
# BASE DIRECTORY
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent


# ============================================================
# SECURITY
# ============================================================

SECRET_KEY = config(
    "SECRET_KEY",
    default="dev-only-insecure-secret-key"
)

DEBUG = config(
    "DEBUG",
    default=True,
    cast=bool
)


# ============================================================
# ALLOWED HOSTS
# ============================================================

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="127.0.0.1,localhost",
    cast=Csv()
)

# Render automatically provides RENDER_EXTERNAL_HOSTNAME.
# This allows the deployed Render URL automatically.

RENDER_EXTERNAL_HOSTNAME = os.environ.get(
    "RENDER_EXTERNAL_HOSTNAME"
)

if (
    RENDER_EXTERNAL_HOSTNAME
    and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS
):
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)


# ============================================================
# INSTALLED APPS
# ============================================================

INSTALLED_APPS = [

    # Django built-in applications
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # SMCE Stock Management application
    "stock.apps.StockConfig",
]


# ============================================================
# MIDDLEWARE
# ============================================================

MIDDLEWARE = [

    "django.middleware.security.SecurityMiddleware",

    # WhiteNoise serves CSS, JavaScript and other static files
    # directly from the Render application.
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",

    "django.middleware.common.CommonMiddleware",

    "django.middleware.csrf.CsrfViewMiddleware",

    "django.contrib.auth.middleware.AuthenticationMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",

    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ============================================================
# URL CONFIGURATION
# ============================================================

ROOT_URLCONF = "smce_project.urls"


# ============================================================
# TEMPLATES
# ============================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",

        "DIRS": [
            BASE_DIR / "templates"
        ],

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


# ============================================================
# WSGI
# ============================================================

WSGI_APPLICATION = "smce_project.wsgi.application"


# ============================================================
# DATABASE
# SUPABASE POSTGRESQL
# ============================================================

DATABASE_URL = config(
    "DATABASE_URL",
    default=""
)


if DATABASE_URL:

    # Render + Supabase
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }

else:

    # Local / alternative environment
    DATABASES = {
        "default": {

            "ENGINE": "django.db.backends.postgresql",

            "NAME": config(
                "DB_NAME",
                default="postgres"
            ),

            "USER": config(
                "DB_USER",
                default="postgres"
            ),

            "PASSWORD": config(
                "DB_PASSWORD",
                default=""
            ),

            "HOST": config(
                "DB_HOST",
                default="127.0.0.1"
            ),

            "PORT": config(
                "DB_PORT",
                default="5432"
            ),

            "OPTIONS": {
                "sslmode": config(
                    "DB_SSLMODE",
                    default="require"
                ),
            },

            "CONN_MAX_AGE": 600,
        }
    }


# ============================================================
# PASSWORD VALIDATION
# ============================================================

AUTH_PASSWORD_VALIDATORS = [

    {
        "NAME":
        "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },

    {
        "NAME":
        "django.contrib.auth.password_validation.MinimumLengthValidator",

        "OPTIONS": {
            "min_length": 6
        }
    },

    {
        "NAME":
        "django.contrib.auth.password_validation.CommonPasswordValidator"
    },

    {
        "NAME":
        "django.contrib.auth.password_validation.NumericPasswordValidator"
    },
]


# ============================================================
# LANGUAGE / TIMEZONE
# ============================================================

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Kolkata"

USE_I18N = True

USE_TZ = True


# ============================================================
# STATIC FILES
# ============================================================

# Browser URL for static files
STATIC_URL = "/static/"


# Source static folder
STATICFILES_DIRS = [
    BASE_DIR / "static",
]


# Destination created by collectstatic
STATIC_ROOT = BASE_DIR / "staticfiles"


# WhiteNoise compressed static file storage
STORAGES = {

    "default": {
        "BACKEND":
        "django.core.files.storage.FileSystemStorage",
    },

    "staticfiles": {
        "BACKEND":
        "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


# ============================================================
# DEFAULT PRIMARY KEY
# ============================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ============================================================
# CUSTOM USER MODEL
# ============================================================

AUTH_USER_MODEL = "stock.Member"


# ============================================================
# LOGIN / LOGOUT
# ============================================================

LOGIN_URL = "login"

LOGIN_REDIRECT_URL = "dashboard"

LOGOUT_REDIRECT_URL = "login"


# ============================================================
# FILE UPLOAD LIMIT
# ============================================================

# Maximum upload size = 5 MB

DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024