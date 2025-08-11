# settings.py
from pathlib import Path
import os
from dotenv import load_dotenv
from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv()

def env(key, default=None, cast=str):
    val = os.getenv(key, default)
    return cast(val) if val is not None else None

ENV = env("DJANGO_ENV", "development")
DEBUG = env("DJANGO_DEBUG", "False").lower() == "true"

SECRET_KEY = env("DJANGO_SECRET_KEY") or (
    get_random_secret_key() if DEBUG else (_ for _ in ()).throw(
        RuntimeError("DJANGO_SECRET_KEY must be set in production")
    )
)

ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin","django.contrib.auth","django.contrib.contenttypes",
    "django.contrib.sessions","django.contrib.messages","django.contrib.staticfiles",
    "rest_framework","api",
    # "corsheaders",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
# ... templates unchanged ...
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "frontend" / "templates"],  # optional
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("DB_NAME", "FIT5120_OnBoarding"),
        "USER": env("DB_USER", "admin"),
        "PASSWORD": env("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", "127.0.0.1"),
        "PORT": env("DB_PORT", "3306"),
        "OPTIONS": {
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            **({"ssl": {"ca": env("RDS_CA_PATH")}} if ENV == "production" else {}),
        },
    }
}

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "frontend" / "static"]
print(STATICFILES_DIRS)

X_FRAME_OPTIONS = "SAMEORIGIN"




# -------- Security & cross-site settings --------
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env("DJANGO_CSRF_TRUSTED_ORIGINS","").split(",") if o.strip()]

# CORS
CORS_ALLOWED_ORIGINS = [o.strip() for o in env("CORS_ALLOWED_ORIGINS","").split(",") if o.strip()]
CORS_ALLOW_CREDENTIALS = env("CORS_ALLOW_CREDENTIALS","False").lower() == "true"

if ENV == "production":
    SECURE_SSL_REDIRECT = (env("DJANGO_SECURE_SSL_REDIRECT", "True").lower() == "true")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", 31536000))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_REFERRER_POLICY = "same-origin"
