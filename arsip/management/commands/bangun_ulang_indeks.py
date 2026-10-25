from django.core.management.base import BaseCommand

from arsip import layanan, pencarian
from arsip.models import Dokumen


class Command(BaseCommand):
    help = "Bangun ulang indeks pencarian. Pakai --ekstrak-ulang untuk membaca ulang teks semua PDF."

    def add_arguments(self, parser):
        parser.add_argument("--ekstrak-ulang", action="store_true")

    def handle(self, *args, **opt):
        if opt["ekstrak_ulang"]:
            for dok in Dokumen.objects.select_related("kategori").iterator():
                layanan.proses_teks(dok)
                self.stdout.write(f"#{dok.pk} {dok.judul[:70]}")
        n = pencarian.bangun_ulang_indeks()
        self.stdout.write(self.style.SUCCESS(f"Indeks dibangun ulang untuk {n} dokumen."))
