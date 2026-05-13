from pathlib import Path
import os
from django.contrib.messages import constants as messages_constants
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATICFILES_DIRS = [os.path.join(BASE_DIR, "static")]


SECRET_KEY = os.getenv("SECRET_KEY", "dummy-development-secret")

DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "household-app-bacon.net",
]


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "trips",
    "analytics",
    "widget_tweaks",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "analytics.middleware.PageViewMiddleware",
]

ROOT_URLCONF = "TRproject.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [TEMPLATE_DIR],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "TRproject.wsgi.application"


# Bootstrap 5 用に messages のタグを調整（error → danger）
MESSAGE_TAGS = {
    messages_constants.ERROR: "danger",
}


# Database (Raspberry Pi 上の PostgreSQL)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("dbname"),
        "USER": os.getenv("user"),
        "PASSWORD": os.getenv("password"),
        "HOST": os.getenv("host"),
        "PORT": os.getenv("port"),
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]


LANGUAGE_CODE = "ja"
TIME_ZONE = "Asia/Tokyo"
USE_I18N = True
USE_TZ = True


STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# 写真機能用（ベストショット等）
# 本番(chaproject)は /travel/ 配下で動くため、他アプリと衝突しないよう
# MEDIA_URL もプレフィックス付きにする。Nginx 側で /travel/media/ を
# /opt/TRproject/media/ にマップする設定が必要。
MEDIA_ROOT = os.path.join(BASE_DIR, "media")
MEDIA_URL = "/travel/media/"


# カスタムユーザーモデル
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "accounts.backends.EmailOrUsernameBackend",
]

LOGIN_URL = "accounts:login"


# メール送信
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")


# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")


# サブパス /travel でのデプロイ設定
# Nginx 側で /travel プレフィックスを除去してから Gunicorn に転送する構成
# ローカル開発時は .env に FORCE_SCRIPT_NAME を書かない（空 = 無効）
# 本番（Raspberry Pi）の .env に FORCE_SCRIPT_NAME=/travel を設定する
_script_name = os.getenv("FORCE_SCRIPT_NAME", "")
if _script_name:
    FORCE_SCRIPT_NAME = _script_name
    STATIC_URL = f"{_script_name}/static/"
else:
    STATIC_URL = "/static/"


# プロキシ経由のHTTPS判定（Cloudflare Tunnel 共通）
CSRF_TRUSTED_ORIGINS = [
    "https://household-app-bacon.net",
]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# 他アプリ（/budget, /cooking）とCookieが競合しないよう分離
SESSION_COOKIE_NAME = "sessionid_travel"
CSRF_COOKIE_NAME = "csrftoken_travel"
