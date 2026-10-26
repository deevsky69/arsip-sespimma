"""
Buat akun Pembaca untuk setiap penulis naskah yang NRP-nya tercatat di arsip.

  python manage.py buat_akun_dari_naskah --sandi "qwerty123" --kering    # lihat dulu, tidak menyimpan
  python manage.py buat_akun_dari_naskah --sandi "qwerty123"             # buat akun

- Username = NRP; nama diambil dari naskah (huruf kapital dirapikan).
- Akun yang sudah ada tidak diubah.
- Semua akun baru WAJIB mengganti kata sandi saat pertama kali masuk.
- Penulis yang naskahnya tidak memuat NRP dilaporkan agar dibuatkan manual.
"""

import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from arsip.models import Dokumen, WajibGantiSandi


def rapikan_nama(nama: str) -> str:
    """'RITA APRINA IFADI, S.H' -> 'Rita Aprina Ifadi, S.H' (gelar setelah koma dibiarkan)."""
    nama = re.sub(r"\s+", " ", nama).strip()
    inti, koma, gelar = nama.partition(",")
    if inti.isupper():
        inti = " ".join(k.capitalize() for k in inti.split())
    return f"{inti}{koma}{gelar}"


def _kunci_nama(nama: str) -> str:
    """Kata pertama + terakhir nama (tanpa gelar), agar "Eriestu R. Prananda" = "ERIESTU RIZQI PRANANDA"."""
    kata = re.findall(r"[a-z]+", nama.lower().split(",")[0])
    return f"{kata[0]}-{kata[-1]}" if kata else ""


def penulis_ber_nrp():
    """{nrp: nama} dari seluruh naskah, plus daftar nama penulis yang tidak punya NRP di naskah mana pun."""
    ada, semua_nama = {}, {}
    for d in Dokumen.objects.exclude(penulis="").order_by("pk"):
        nama = d.daftar_penulis
        nrp = [n for n in re.findall(r"\d{8}", d.nrp_penulis)]
        for i, n in enumerate(nrp):
            ada.setdefault(n, rapikan_nama(nama[i] if i < len(nama) else nama[0]))
        for nm in nama:
            semua_nama.setdefault(_kunci_nama(nm), rapikan_nama(nm))
    kunci_ber_nrp = {_kunci_nama(n) for n in ada.values()}
    tanpa = sorted(v for k, v in semua_nama.items() if k not in kunci_ber_nrp)
    return ada, tanpa


class Command(BaseCommand):
    help = "Buat akun Pembaca (username = NRP) untuk semua penulis yang NRP-nya ada di naskah."

    def add_arguments(self, parser):
        parser.add_argument("--sandi", required=True, help="Kata sandi awal untuk semua akun baru")
        parser.add_argument("--kering", action="store_true", help="Uji coba: tampilkan saja, tidak menyimpan")

    @transaction.atomic
    def handle(self, *args, **opt):
        if len(opt["sandi"]) < 6:
            raise CommandError("Kata sandi awal terlalu pendek (minimal 6 karakter).")
        User = get_user_model()
        ada, tanpa = penulis_ber_nrp()
        dibuat = dilewati = 0
        for nrp, nama in sorted(ada.items(), key=lambda x: x[1]):
            if User.objects.filter(username=nrp).exists():
                dilewati += 1
                self.stdout.write(f"  sudah ada : {nrp}  {nama}")
                continue
            if not opt["kering"]:
                u = User.objects.create_user(username=nrp, password=opt["sandi"], first_name=nama[:150])
                WajibGantiSandi.objects.create(pengguna=u)
            dibuat += 1
            self.stdout.write(f"  {'akan dibuat' if opt['kering'] else 'dibuat'} : {nrp}  {nama}")
        if tanpa:
            self.stdout.write(self.style.WARNING(f"\n{len(tanpa)} penulis tanpa NRP di naskah (buat manual di Panel Admin):"))
            for n in tanpa:
                self.stdout.write(f"  - {n}")
        ringkas = f"\n{dibuat} akun {'akan dibuat' if opt['kering'] else 'dibuat'}, {dilewati} sudah ada sebelumnya."
        self.stdout.write(self.style.SUCCESS(ringkas))
        if opt["kering"]:
            transaction.set_rollback(True)
            self.stdout.write("Uji coba: tidak ada yang disimpan.")
