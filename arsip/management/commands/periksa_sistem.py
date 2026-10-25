"""
Pemeriksaan kesehatan arsip: jalankan setelah memasang/memindahkan server, atau kapan saja.

  python manage.py periksa_sistem

Keluar dengan kode 1 bila ada masalah serius ([GAGAL]); [PERINGATAN] tidak menggagalkan.
"""

import shutil
import sys
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from arsip import ocr, pencarian
from arsip.models import Dokumen, Kemiripan


class Command(BaseCommand):
    help = "Periksa kesehatan sistem arsip (data, berkas, indeks, OCR, cadangan, keamanan)."

    def handle(self, *args, **opt):
        self.gagal = 0
        data = Path(settings.DATA_DIR)

        self.judul("Pengaturan")
        if settings.DEBUG:
            self.info("Mode pengembangan (DEBUG=true): wajar di laptop, tetapi WAJIB false di server")
        else:
            self.cek(not settings.SECRET_KEY.startswith("dev-only"), "Mode produksi, DJANGO_SECRET_KEY diisi",
                     "DJANGO_SECRET_KEY masih kunci pengembangan")
            self.cek(all(h not in ("localhost", "127.0.0.1") for h in settings.ALLOWED_HOSTS),
                     f"Domain: {', '.join(settings.ALLOWED_HOSTS)}",
                     "DJANGO_ALLOWED_HOSTS belum diisi domain situs", serius=False)
            self.cek(bool(settings.CSRF_TRUSTED_ORIGINS), "DJANGO_CSRF_TRUSTED_ORIGINS diisi",
                     "DJANGO_CSRF_TRUSTED_ORIGINS kosong: form login akan ditolak lewat HTTPS")

        self.judul("Folder data")
        self.info(f"Lokasi: {data}")
        try:
            uji = data / ".uji-tulis"
            uji.write_text("ok")
            uji.unlink()
            self.cek(True, "Folder data bisa ditulis", "")
        except OSError as e:
            self.cek(False, "", f"Folder data tidak bisa ditulis: {e}")
        sisa = shutil.disk_usage(data).free / 1024**3
        self.cek(sisa > 2, f"Sisa disk {sisa:.1f} GB", f"Sisa disk tinggal {sisa:.1f} GB", serius=False)

        self.judul("Database")
        rencana = MigrationExecutor(connection).migration_plan(MigrationExecutor(connection).loader.graph.leaf_nodes())
        self.cek(not rencana, "Struktur database terbaru", f"{len(rencana)} migrasi belum dijalankan (manage.py migrate)")
        User = get_user_model()
        n_dok = Dokumen.objects.count()
        self.info(f"{n_dok} dokumen ({Dokumen.objects.filter(status='terbit').count()} terbit), {User.objects.count()} pengguna")
        self.cek(User.objects.filter(is_superuser=True, is_active=True).exists(), "Ada akun admin (superuser)",
                 "Belum ada superuser: jalankan manage.py createsuperuser")

        self.judul("Berkas PDF")
        hilang = [d.pk for d in Dokumen.objects.only("berkas") if not d.berkas or not Path(d.berkas.path).exists()]
        self.cek(not hilang, f"Semua {n_dok} file PDF ditemukan",
                 f"{len(hilang)} file PDF hilang (contoh dokumen #{', #'.join(map(str, hilang[:5]))})")

        self.judul("Indeks pencarian & kemiripan")
        with connection.cursor() as c:
            c.execute(f"SELECT COUNT(*) FROM arsip_fts WHERE rowid % {pencarian.KELIPATAN} = 0")
            n_indeks = c.fetchone()[0]
            c.execute("SELECT COUNT(DISTINCT dokumen_id) FROM arsip_sidikjari")
            n_sidik = c.fetchone()[0]
        self.cek(n_indeks == n_dok, f"Indeks pencarian lengkap ({n_indeks} dokumen)",
                 f"Indeks pencarian berisi {n_indeks} dari {n_dok} dokumen: jalankan manage.py bangun_ulang_indeks")
        bisa = Dokumen.objects.filter(perlu_ocr=False).count()
        self.cek(n_sidik >= bisa, f"Sidik jari kemiripan lengkap ({n_sidik} dokumen, {Kemiripan.objects.count()} pasangan mirip)",
                 f"Sidik jari baru {n_sidik} dari {bisa} dokumen: jalankan manage.py cek_kemiripan", serius=False)

        self.judul("OCR")
        self.cek(ocr.tersedia(), f"Model bahasa OCR ada di {ocr.folder_model()}",
                 f"Model OCR ({', '.join(ocr.model_kurang())}) belum ada: jalankan manage.py siapkan_ocr", serius=False)
        S = Dokumen.StatusOCR
        antre = Dokumen.objects.filter(status_ocr__in=[S.ANTRE, S.PROSES]).count()
        gagal = Dokumen.objects.filter(status_ocr=S.GAGAL).count()
        self.info(f"Antrean OCR: {antre} · gagal: {gagal} · pekerja {'berjalan' if ocr.pekerja_hidup() else 'tidak berjalan'}")

        self.judul("Cadangan")
        tujuan = Path(settings.ARSIP_CADANGAN_DIR or data / "cadangan")
        log = tujuan / "cadangan.log"
        if log.exists():
            terakhir = log.read_text(encoding="utf-8").strip().splitlines()[-1]
            umur = (timezone.now().timestamp() - log.stat().st_mtime) / 3600
            self.cek(umur < 48, f"Cadangan terakhir: {terakhir[:16]} ({umur:.0f} jam lalu)",
                     f"Cadangan terakhir {umur:.0f} jam lalu, periksa jadwal cadangan", serius=False)
        else:
            self.cek(False, "", f"Belum pernah ada cadangan di {tujuan}: jalankan manage.py cadangkan & pasang jadwalnya",
                     serius=False)

        self.judul("Keamanan")
        self.cek("axes" in settings.INSTALLED_APPS, f"Batas percobaan login aktif ({settings.AXES_FAILURE_LIMIT}x gagal)", "")
        if not settings.DEBUG:
            manifest = Path(settings.STATIC_ROOT) / "staticfiles.json"
            self.cek(manifest.exists(), "File statis siap (collectstatic)", "File statis belum disiapkan: manage.py collectstatic")

        self.stdout.write("")
        if self.gagal:
            self.stdout.write(self.style.ERROR(f"{self.gagal} masalah serius perlu dibereskan."))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS("Tidak ada masalah serius."))

    # ------------------------------------------------------------------

    def judul(self, teks):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n{teks}"))

    def info(self, teks):
        self.stdout.write(f"  [INFO]       {teks}")

    def cek(self, ok, pesan_ok, pesan_gagal, serius=True):
        if ok:
            self.stdout.write(self.style.SUCCESS(f"  [OK]         {pesan_ok}"))
        elif serius:
            self.gagal += 1
            self.stdout.write(self.style.ERROR(f"  [GAGAL]      {pesan_gagal}"))
        else:
            self.stdout.write(self.style.WARNING(f"  [PERINGATAN] {pesan_gagal}"))
