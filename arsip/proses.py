"""
Meluncurkan pekerjaan berat (OCR, impor Google Drive) sebagai PROSES terpisah, bukan thread.

Alasannya: pekerjaan ini memakai CPU penuh dan menahan GIL Python, sehingga bila dijalankan di
dalam proses web seluruh situs ikut melambat; selain itu thread ikut mati ketika server web
di-restart, sedangkan proses terpisah tetap berjalan sampai selesai.
"""

import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings


def luncurkan(argumen: list[str], nama_log: str):
    """Jalankan `python manage.py <argumen...>` di latar belakang; keluarannya ditambahkan ke <data>/<nama_log>."""
    opsi = {}
    if os.name == "nt":
        opsi["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        opsi["start_new_session"] = True
    with open(Path(settings.DATA_DIR) / nama_log, "ab") as log:
        subprocess.Popen(
            [sys.executable, str(Path(settings.BASE_DIR) / "manage.py"), *argumen],
            cwd=settings.BASE_DIR,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            **opsi,
        )
