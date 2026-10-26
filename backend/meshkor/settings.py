"""Django settings for the MeshKor Step 1 backend.

Decisions (Oct 17, 2026): PostgreSQL holds Django's own records (load runs,
source files, verify runs, portal users, cases); the reference data lives in
Parquet + DuckDB tables. Oct 23, 2026: the lien portal API (DRF + JWT) was
added for the React frontend; see docs/API_CONTRACT.md.

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
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "refdata",
    "accounts",
    "cases",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
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

# ---- Lien portal API (Oct 23, 2026) -------------------------------------------
from datetime import timedelta  # noqa: E402

AUTHENTICATION_BACKENDS = ["accounts.backends.EmailBackend", "django.contrib.auth.backends.ModelBackend"]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]
        + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "COERCE_DECIMAL_TO_STRING": False,     # money as numbers
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get("JWT_ACCESS_MINUTES", "30"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(hours=int(os.environ.get("JWT_REFRESH_HOURS", "12"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# Frontend origins allowed to call the API (production). The Vite dev proxy needs none.
CORS_ALLOWED_ORIGINS = [o for o in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o]
CORS_ALLOW_HEADERS = ["accept", "authorization", "content-type", "x-requested-with"]
CORS_EXPOSE_HEADERS = ["Content-Disposition"]
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

# Behind HTTPS (production). DJANGO_SECURE=1 turns on the browser protections; the reverse proxy
# (nginx, IIS) terminates TLS and sends X-Forwarded-Proto.
if os.environ.get("DJANGO_SECURE", "0") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
if SECRET_KEY == "dev-only-change-me" and "test" not in sys.argv:
    if os.environ.get("DJANGO_SECURE", "0") == "1":
        raise RuntimeError("DJANGO_SECRET_KEY is not set. Put a 50+ character random value in .env.")
    import warnings
    warnings.warn("DJANGO_SECRET_KEY is not set: sign-in tokens are signed with a public default. Set it in .env.")

# Bills and EOBs (PHI): encrypted, outside the repo. Make a key once:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
MESHKOR_UPLOAD_DIR = os.environ.get("MESHKOR_UPLOAD_DIR", str(Path(MESHKOR_DATA_ROOT) / "uploads"))
MESHKOR_FILE_KEY = os.environ.get("MESHKOR_FILE_KEY", "")
if not MESHKOR_FILE_KEY and not DEBUG and "test" not in sys.argv:
    import warnings
    warnings.warn("MESHKOR_FILE_KEY is not set; bill uploads will fail until it is.")
# Who prices a new upload (see cases/processing.py): thread (default) | worker | inline. The tests use inline.
MESHKOR_PRICING = "inline" if "test" in sys.argv else os.environ.get("MESHKOR_PRICING", "thread")
MESHKOR_PRICING_THREADS = int(os.environ.get("MESHKOR_PRICING_THREADS", "2"))   # bills priced at the same time
MESHKOR_FOUR_EYES = os.environ.get("MESHKOR_FOUR_EYES", "0") == "1"    # a different reviewer must approve
MESHKOR_PORTAL_URL = os.environ.get("MESHKOR_PORTAL_URL", "http://localhost:5173")
DATA_UPLOAD_MAX_MEMORY_SIZE = 55 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 55 * 1024 * 1024

# "Report ready" mail. Default prints to the console; set EMAIL_HOST etc. for real mail.
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "reports@meshkor.local")

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
# -------------------------------------------------------------------------------

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
