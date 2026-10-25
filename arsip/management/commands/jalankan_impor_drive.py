from django.core.management.base import BaseCommand, CommandError

from arsip import tugas
from arsip.models import TugasImpor


class Command(BaseCommand):
    help = "Jalankan satu tugas impor Google Drive (biasanya diluncurkan otomatis dari menu Impor Drive)."

    def add_arguments(self, parser):
        parser.add_argument("id_tugas", type=int)

    def handle(self, *args, **opt):
        if not TugasImpor.objects.filter(pk=opt["id_tugas"]).exists():
            raise CommandError(f"Tugas impor #{opt['id_tugas']} tidak ditemukan.")
        t = tugas.jalankan(opt["id_tugas"])
        j = t.ringkasan()
        self.stdout.write(
            f"Impor #{t.pk} {t.get_status_display()}: {j['berhasil']} berhasil, {j['duplikat']} duplikat, "
            f"{j['gagal']} gagal, {j['dilewati']} dilewati. {t.pesan_galat}"
        )
