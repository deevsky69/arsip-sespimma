"""
Unduh model bahasa Tesseract (versi "fast") untuk OCR ke folder ARSIP_TESSDATA.

  python manage.py siapkan_ocr

Di Docker tidak perlu: model sudah dipasang lewat paket tesseract-ocr-ind/eng.
"""

import urllib.request

from django.core.management.base import BaseCommand, CommandError

from arsip import ocr


class Command(BaseCommand):
    help = "Unduh model bahasa OCR (ind, eng) ke folder ARSIP_TESSDATA."

    def handle(self, *args, **opt):
        folder = ocr.folder_model()
        folder.mkdir(parents=True, exist_ok=True)
        for b in ocr.bahasa():
            tujuan = folder / f"{b}.traineddata"
            if tujuan.exists():
                self.stdout.write(f"{b}: sudah ada")
                continue
            url = ocr.SUMBER_MODEL.format(b)
            self.stdout.write(f"{b}: mengunduh {url} ...")
            try:
                sementara = tujuan.with_suffix(".unduh")
                urllib.request.urlretrieve(url, sementara)
                sementara.replace(tujuan)
            except Exception as e:
                raise CommandError(f"Gagal mengunduh model {b}: {e}")
        self.stdout.write(self.style.SUCCESS(f"Model OCR siap di {folder}"))
