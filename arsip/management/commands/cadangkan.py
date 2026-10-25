"""
Cadangkan database + file PDF (aman dijalankan saat situs sedang dipakai).

  python manage.py cadangkan
  python manage.py cadangkan --tujuan "D:\\Cadangan Arsip" --simpan 30

Tujuan default diambil dari ARSIP_CADANGAN_DIR (lihat .env); bila kosong: <folder data>/cadangan.
Di tujuan akan terbentuk:
  database/arsip-YYYYmmdd-HHMM.sqlite3   salinan database (disimpan N terbaru)
  berkas/...                             cermin folder PDF (hanya file baru/berubah yang disalin;
                                          file yang terhapus di arsip TIDAK ikut dihapus dari cadangan)
  cadangan.log                           riwayat pencadangan

Memulihkan: hentikan situs, salin database terbaru menjadi <folder data>/arsip.sqlite3 dan
folder berkas menjadi <folder data>/berkas, lalu jalankan situs kembali.
"""

import os
import shutil
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone


class Command(BaseCommand):
    help = "Cadangkan database dan file PDF arsip."

    def add_arguments(self, parser):
        parser.add_argument("--tujuan", help="Folder cadangan (default: ARSIP_CADANGAN_DIR atau data/cadangan)")
        parser.add_argument("--simpan", type=int, default=30, help="Jumlah salinan database terbaru yang disimpan")

    def handle(self, *args, **opt):
        tujuan = Path(opt["tujuan"] or getattr(settings, "ARSIP_CADANGAN_DIR", "") or settings.DATA_DIR / "cadangan")
        (tujuan / "database").mkdir(parents=True, exist_ok=True)
        waktu = timezone.localtime()

        # 1. Database: salinan konsisten lewat backup API SQLite
        berkas_db = tujuan / "database" / f"arsip-{waktu:%Y%m%d-%H%M}.sqlite3"
        connection.ensure_connection()
        with sqlite3.connect(berkas_db) as salinan:
            connection.connection.backup(salinan)
        salinan.close()
        semua = sorted((tujuan / "database").glob("arsip-*.sqlite3"))
        for lama in semua[: max(0, len(semua) - opt["simpan"])]:
            lama.unlink()

        # 2. File PDF: salin yang baru / berubah saja
        sumber = settings.DATA_DIR / "berkas"
        disalin = total = 0
        if sumber.exists():
            for f in sumber.rglob("*"):
                if not f.is_file():
                    continue
                total += 1
                t = tujuan / "berkas" / f.relative_to(sumber)
                st = f.stat()
                if t.exists() and t.stat().st_size == st.st_size and int(t.stat().st_mtime) >= int(st.st_mtime):
                    continue
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, t)
                disalin += 1

        ringkas = (
            f"{waktu:%Y-%m-%d %H:%M} database {berkas_db.name} ({os.path.getsize(berkas_db) // 1024} KB), "
            f"{disalin} PDF baru/berubah dari {total} PDF"
        )
        with open(tujuan / "cadangan.log", "a", encoding="utf-8") as log:
            log.write(ringkas + "\n")
        self.stdout.write(self.style.SUCCESS(f"Cadangan selesai di {tujuan}: {ringkas}"))
