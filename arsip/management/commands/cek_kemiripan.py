from django.core.management.base import BaseCommand

from arsip import kemiripan
from arsip.models import Kemiripan


class Command(BaseCommand):
    help = "Hitung ulang sidik jari dan kemiripan seluruh dokumen (jalankan setelah impor besar)."

    def handle(self, *args, **opt):
        n = kemiripan.hitung_semua(catat=self.stdout.write)
        tinggi = sum(1 for k in Kemiripan.objects.all() if k.tertinggi >= 20)
        self.stdout.write(self.style.SUCCESS(f"Selesai: {n} pasangan mirip tersimpan, {tinggi} di atas 20%."))
