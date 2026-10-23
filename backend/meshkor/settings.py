"""Django settings for the MeshKor Step 1 backend.

Decisions (Oct 17, 2026): PostgreSQL holds Django's own records (load runs,
source files, verify runs); the reference data lives in Parquet + DuckDB
tables; no web API in Step 1 (admin site only).

All settings come from environment variables (see ../.env.example).
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))  # so `import pipeline` works


def _load_env(path: Path) -> None:
    """Minimal .env reader (KEY=VALUE lines). Real env vars win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env(PROJECT_ROOT / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "refdata",
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

ROOT_URLCONF = "meshkor.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

WSGI_APPLICATION = "meshkor.wsgi.application"

def _env(*names: str, default: str = "") -> str:
    """First variable that is set (POSTGRES_* or the DB_* aliases)."""
    for n in names:
        if os.environ.get(n):
            return os.environ[n]
    return default


if _env("DB_ENGINE", default="postgresql").lower() == "sqlite":
    # Quick start without a database server. Set DB_ENGINE=sqlite in .env.
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3",
                             "NAME": PROJECT_ROOT / "data" / "django.sqlite3"}}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _env("POSTGRES_DB", "DB_NAME", default="meshkor"),
            "USER": _env("POSTGRES_USER", "DB_USER", default="meshkor"),
            "PASSWORD": _env("POSTGRES_PASSWORD", "DB_PASSWORD"),
            "HOST": _env("POSTGRES_HOST", "DB_HOST", default="localhost"),
            "PORT": _env("POSTGRES_PORT", "DB_PORT", default="5432"),
            "CONN_MAX_AGE": 60,
        }
    }

# Reference data (Parquet, DuckDB, raw downloads). Default: <repo>/data
MESHKOR_DATA_ROOT = os.environ.get("MESHKOR_DATA_ROOT", str(PROJECT_ROOT / "data"))
os.environ.setdefault("MESHKOR_DATA_ROOT", MESHKOR_DATA_ROOT)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/New_York"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = PROJECT_ROOT / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {"meshkor": {"handlers": ["console"], "level": "INFO"}},
}
