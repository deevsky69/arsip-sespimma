"""
Jalankan antrean OCR di terminal (berguna di server, atau untuk dokumen hasil scan yang lama).

  python manage.py jalankan_ocr              # kerjakan antrean yang ada
  python manage.py jalankan_ocr --semua      # antrekan semua PDF hasil scan yang belum/gagal di-OCR
  python manage.py jalankan_ocr --dokumen 12 # OCR ulang satu dokumen
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from arsip import ocr
from arsip.models import Dokumen


class Command(BaseCommand):
    help = "Kerjakan antrean OCR untuk PDF hasil scan."

    def add_arguments(self, parser):
        parser.add_argument("--semua", action="store_true", help="Antrekan semua PDF scan yang belum/gagal di-OCR")
        parser.add_argument("--dokumen", type=int, action="append", help="ID dokumen yang di-OCR (boleh berulang)")

    def handle(self, *args, **opt):
        if not ocr.tersedia():
            raise CommandError(f"Model bahasa OCR belum ada di {ocr.folder_model()}. Jalankan: manage.py siapkan_ocr")
        S = Dokumen.StatusOCR
        target = Dokumen.objects.none()
        if opt["semua"]:
            target = Dokumen.objects.filter(Q(perlu_ocr=True) & ~Q(status_ocr__in=[S.ANTRE, S.PROSES]))
        if opt["dokumen"]:
            target = target | Dokumen.objects.filter(pk__in=opt["dokumen"])
        for dok in target:
            Dokumen.objects.filter(pk=dok.pk).update(status_ocr=S.ANTRE, ocr_kemajuan=0, ocr_pesan="")
        antre = Dokumen.objects.filter(status_ocr=S.ANTRE).count()
        self.stdout.write(f"{antre} dokumen di antrean OCR.")
        n = ocr.jalankan_pekerja(catat=self.stdout.write)
        if n is None:
            self.stdout.write("Pekerja OCR lain sedang berjalan; dokumen akan dikerjakan olehnya.")
        else:
            self.stdout.write(self.style.SUCCESS(f"Selesai: {n} dokumen diproses."))
