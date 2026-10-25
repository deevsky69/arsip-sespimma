"""
Pasang paket hasil `ekspor_data` (database + PDF) di server ini.

  python manage.py impor_data /data/paket-pindah-20261025-1400.zip
  python manage.py impor_data paket.zip --timpa      # menimpa arsip yang sudah berisi dokumen

Jalankan saat situs BELUM/TIDAK sedang berjalan (di Docker: `docker compose run --rm app ...`).
"""

import json
import sqlite3
import zipfile
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections


class Command(BaseCommand):
    help = "Pasang paket data (hasil ekspor_data) di server ini."

    def add_arguments(self, parser):
        parser.add_argument("paket", help="File ZIP hasil ekspor_data")
        parser.add_argument("--timpa", action="store_true", help="Izinkan menimpa arsip yang sudah berisi dokumen")

    def handle(self, *args, **opt):
        paket = Path(opt["paket"])
        if not paket.is_file():
            raise CommandError(f"File tidak ditemukan: {paket}")
        db_tujuan = Path(settings.DATABASES["default"]["NAME"])
        berkas_tujuan = Path(settings.DATA_DIR) / "berkas"

        with zipfile.ZipFile(paket) as z:
            nama = set(z.namelist())
            if "arsip.sqlite3" not in nama or "paket.json" not in nama:
                raise CommandError("Ini bukan paket hasil `ekspor_data` (arsip.sqlite3/paket.json tidak ada).")
            info = json.loads(z.read("paket.json"))
            self.stdout.write(f"Paket: {info['jumlah_dokumen']} dokumen, {info['jumlah_pdf']} PDF, dibuat {info['dibuat']}")

            if db_tujuan.exists() and not opt["timpa"]:
                c = sqlite3.connect(db_tujuan)  # ditutup eksplisit: `with` sqlite3 tidak menutup koneksi
                try:
                    ada = c.execute("SELECT COUNT(*) FROM arsip_dokumen").fetchone()[0]
                except sqlite3.Error:
                    ada = 0
                finally:
                    c.close()
                if ada:
                    raise CommandError(
                        f"Arsip di {db_tujuan} sudah berisi {ada} dokumen. Tambahkan --timpa bila memang ingin "
                        "menggantinya (buat cadangan dulu)."
                    )

            connections.close_all()
            db_tujuan.parent.mkdir(parents=True, exist_ok=True)
            for ekor in ("", "-wal", "-shm"):
                Path(f"{db_tujuan}{ekor}").unlink(missing_ok=True)
            db_tujuan.write_bytes(z.read("arsip.sqlite3"))

            jumlah = 0
            for n in nama:
                p = PurePosixPath(n)
                if p.parts[:1] != ("berkas",) or n.endswith("/") or ".." in p.parts:
                    continue
                target = berkas_tujuan.joinpath(*p.parts[1:])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(n))
                jumlah += 1

        self.stdout.write(f"Database dipasang di {db_tujuan}; {jumlah} PDF disalin ke {berkas_tujuan}.")
        call_command("migrate", verbosity=0)
        self.stdout.write(self.style.SUCCESS("Selesai. Periksa dengan: python manage.py periksa_sistem"))
