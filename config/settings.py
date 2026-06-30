from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "silk",
    "ninja_simple_jwt",
    "courses",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "silk.middleware.SilkyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB", default="lmsdb"),
        "USER": config("POSTGRES_USER", default="lmsuser"),
        "PASSWORD": config("POSTGRES_PASSWORD", default="lmspassword"),
        "HOST": config("POSTGRES_HOST", default="db"),
        "PORT": config("POSTGRES_PORT", default="5432"),
    }
}

AUTH_USER_MODEL = "courses.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "id"
TIME_ZONE = "Asia/Jakarta"
USE_I18N = True
USE_TZ = True

STATIC_URL = config("STATIC_URL", default="/static/")
STATIC_ROOT = config("STATIC_ROOT", default=BASE_DIR / "staticfiles")
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ══════════════════════════════════════════════════════════════
# REDIS — Cache & Rate Limiting
# ══════════════════════════════════════════════════════════════

REDIS_HOST = config("REDIS_HOST", default="redis")
REDIS_PORT = config("REDIS_PORT", default=6379, cast=int)
REDIS_CACHE_DB = config("REDIS_CACHE_DB", default=0, cast=int)
REDIS_RATELIMIT_DB = config("REDIS_RATELIMIT_DB", default=1, cast=int)

# Catatan: caching course list/detail TIDAK memakai Django CACHES framework,
# melainkan raw redis-py client langsung (lihat courses/cache.py). Ini
# supaya key di Redis mudah diperiksa manual lewat redis-cli tanpa
# prefix/versioning tambahan dari Django, dan supaya pattern-based
# invalidation (SCAN course:list:*) konsisten lintas versi backend.

# TTL (detik) untuk masing-masing jenis cache — dipakai di courses/cache.py
CACHE_TTL_COURSE_LIST = 60 * 5     # 5 menit
CACHE_TTL_COURSE_DETAIL = 60 * 10  # 10 menit

# Rate limiting: 60 request / 60 detik per user atau IP
RATE_LIMIT_MAX_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60


# ══════════════════════════════════════════════════════════════
# MONGODB — Activity Logs & Learning Analytics
# ══════════════════════════════════════════════════════════════

MONGO_USER = config("MONGO_USER", default="admin")
MONGO_PASSWORD = config("MONGO_PASSWORD", default="password123")
MONGO_HOST = config("MONGO_HOST", default="mongodb")
MONGO_PORT = config("MONGO_PORT", default=27017, cast=int)
MONGO_DB_NAME = config("MONGO_DB", default="lms_analytics")
MONGO_URI = f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/"


# ══════════════════════════════════════════════════════════════
# CELERY — Async Tasks via RabbitMQ, Result Backend via Redis
# ══════════════════════════════════════════════════════════════

CELERY_BROKER_URL = config(
    "CELERY_BROKER_URL", default="amqp://admin:password123@rabbitmq:5672//"
)
CELERY_RESULT_BACKEND = config(
    "CELERY_RESULT_BACKEND", default=f"redis://{REDIS_HOST}:{REDIS_PORT}/2"
)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "update-course-statistics": {
        "task": "courses.tasks.update_course_statistics",
        # Setiap 10 menit untuk kebutuhan demo. Untuk production ganti
        # ke crontab(hour=0, minute=0) supaya berjalan sekali sehari.
        "schedule": crontab(minute="*/10"),
    },
}