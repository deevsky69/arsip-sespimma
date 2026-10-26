"""
Pengaturan Django untuk ARSIP SESPIMMA.

Semua nilai yang berbeda antara komputer pengembangan dan server produksi
dibaca dari environment variable (atau file .env di root proyek).
Lihat .env.example untuk daftar lengkapnya.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "ya")


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key-jangan-dipakai-di-server"
    else:
        raise RuntimeError("DJANGO_SECRET_KEY wajib diisi saat DJANGO_DEBUG=false.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Folder data: database SQLite dan file PDF. Di server, folder ini yang di-backup.
DATA_DIR = Path(os.environ.get("ARSIP_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
# Folder tujuan `manage.py cadangkan` (sebaiknya di disk/layanan lain, mis. folder OneDrive).
ARSIP_CADANGAN_DIR = os.environ.get("ARSIP_CADANGAN_DIR", "")

# OCR untuk PDF hasil scan. Folder berisi model bahasa Tesseract (ind/eng .traineddata);
# isi dengan `manage.py siapkan_ocr`. Di Docker dipasang lewat paket tesseract-ocr-ind.
ARSIP_TESSDATA = os.environ.get("ARSIP_TESSDATA", str(DATA_DIR / "tessdata"))
ARSIP_OCR_BAHASA = os.environ.get("ARSIP_OCR_BAHASA", "ind+eng")
ARSIP_OCR_DPI = int(os.environ.get("ARSIP_OCR_DPI", "300"))
# true = PDF hasil scan otomatis dibaca sampulnya saat diunggah lalu masuk antrean OCR.
ARSIP_OCR_OTOMATIS = env_bool("ARSIP_OCR_OTOMATIS", True)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "axes",
    "arsip",
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
    "arsip.middleware.WajibLoginMiddleware",
    "arsip.middleware.WajibGantiSandiMiddleware",
    "axes.middleware.AxesMiddleware",  # harus paling akhir
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",  # batas percobaan login; harus paling awal
    "django.contrib.auth.backends.ModelBackend",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "arsip.context_processors.navigasi",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "arsip.sqlite3",
        "OPTIONS": {
            # WAL membuat pembaca tidak terblokir saat ada yang mengunggah.
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
            "transaction_mode": "IMMEDIATE",
            "timeout": 20,
        },
    }
}

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

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    # File PDF disimpan di folder privat dan hanya dilayani lewat view yang
    # memeriksa login, jadi tidak ada MEDIA_URL publik.
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": DATA_DIR / "berkas", "base_url": None},
    },
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "arsip:beranda"
LOGOUT_REDIRECT_URL = "login"

# Batas ukuran unggahan (MB).
ARSIP_MAKS_UKURAN_MB = int(os.environ.get("ARSIP_MAKS_UKURAN_MB", "50"))
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# Watermark nama + NRP pembaca di setiap halaman PDF yang dibuka.
ARSIP_WATERMARK = env_bool("ARSIP_WATERMARK", True)
# Izinkan tombol unduh PDF (tetap ber-watermark). False = hanya baca di browser.
ARSIP_IZINKAN_UNDUH = env_bool("ARSIP_IZINKAN_UNDUH", False)
ARSIP_NAMA_SITUS = os.environ.get("ARSIP_NAMA_SITUS", "ARSIP SESPIMMA")
# True bila aplikasi berjalan di belakang reverse proxy (Caddy/Nginx), agar IP asli pembaca tercatat di log.
ARSIP_DI_BELAKANG_PROXY = env_bool("ARSIP_DI_BELAKANG_PROXY", False)

# Batas percobaan login (django-axes): kombinasi username + IP dikunci setelah N kali gagal.
# Membuka kunci lebih awal: Panel Admin -> Axes -> Access attempts (hapus), atau `manage.py axes_reset`.
LOGIN_KUNCI_MENIT = int(os.environ.get("ARSIP_LOGIN_KUNCI_MENIT", "15"))
AXES_FAILURE_LIMIT = int(os.environ.get("ARSIP_LOGIN_MAKS_GAGAL", "5"))
AXES_COOLOFF_TIME = timedelta(minutes=LOGIN_KUNCI_MENIT)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "registration/terkunci.html"
AXES_CLIENT_IP_CALLABLE = "arsip.keamanan.ip_klien"
AXES_VERBOSE = False

SESSION_COOKIE_AGE = 60 * 60 * 12
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"

# PDF ditampilkan dalam <iframe> di halaman sendiri, jadi izinkan same-origin.
X_FRAME_OPTIONS = "SAMEORIGIN"

SILENCED_SYSTEM_CHECKS = [
    "security.W008",  # pengalihan HTTP -> HTTPS sudah dilakukan Caddy
    "security.W019",  # X_FRAME_OPTIONS sengaja SAMEORIGIN untuk penampil PDF
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    # django-axes mencatat setiap login (berhasil/gagal) di level INFO; cukup tampilkan peringatan.
    "loggers": {"axes": {"level": "WARNING"}},
}
