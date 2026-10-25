"""
Bungkus seluruh data arsip (database + semua PDF) menjadi satu file ZIP untuk dipindahkan ke server lain.

  python manage.py ekspor_data                       -> <folder data>/paket-pindah-YYYYmmdd-HHMM.zip
  python manage.py ekspor_data --ke D:\\paket.zip

Aman dijalankan saat situs sedang dipakai (database disalin lewat backup API SQLite).
Pasang di server tujuan dengan: python manage.py impor_data <paket.zip>
"""

import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from arsip.models import Dokumen


class Command(BaseCommand):
    help = "Bungkus database + PDF menjadi satu file ZIP untuk pindah server."

    def add_arguments(self, parser):
        parser.add_argument("--ke", help="Lokasi file ZIP hasil (default: di folder data)")

    def handle(self, *args, **opt):
        waktu = timezone.localtime()
        tujuan = Path(opt["ke"] or settings.DATA_DIR / f"paket-pindah-{waktu:%Y%m%d-%H%M}.zip")
        berkas = Path(settings.DATA_DIR) / "berkas"

        with tempfile.TemporaryDirectory() as sementara:
            db = Path(sementara) / "arsip.sqlite3"
            connection.ensure_connection()
            with sqlite3.connect(db) as salinan:
                connection.connection.backup(salinan)
            salinan.close()

            jumlah_pdf = 0
            with zipfile.ZipFile(tujuan, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as z:
                z.write(db, "arsip.sqlite3")
                if berkas.exists():
                    for f in sorted(berkas.rglob("*")):
                        if f.is_file():
                            # PDF umumnya sudah terkompresi; simpan apa adanya agar cepat.
                            z.write(f, "berkas/" + f.relative_to(berkas).as_posix(), compress_type=zipfile.ZIP_STORED)
                            jumlah_pdf += 1
                info = {
                    "dibuat": waktu.isoformat(),
                    "jumlah_dokumen": Dokumen.objects.count(),
                    "jumlah_pdf": jumlah_pdf,
                    "nama_situs": settings.ARSIP_NAMA_SITUS,
                }
                z.writestr("paket.json", json.dumps(info, indent=2, ensure_ascii=False))

        ukuran = tujuan.stat().st_size / 1024 / 1024
        self.stdout.write(self.style.SUCCESS(
            f"Paket dibuat: {tujuan} ({ukuran:.1f} MB) berisi {info['jumlah_dokumen']} dokumen dan {jumlah_pdf} PDF."
        ))
        self.stdout.write("Kirim file ini ke server, lalu jalankan: python manage.py impor_data <nama-file.zip>")
