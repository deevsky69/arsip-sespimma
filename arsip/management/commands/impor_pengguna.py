"""
Buat akun pengguna secara massal dari CSV.

Kolom CSV: nrp;nama;peran;email   (peran & email opsional)
  peran: pembaca (default) | pengunggah | reviewer | admin

Username = NRP. Kata sandi acak dibuat untuk setiap akun baru dan ditulis ke
file keluaran agar bisa dibagikan; minta pengguna menggantinya setelah login.

  python manage.py impor_pengguna serdik71.csv --keluaran akun_serdik71.csv
"""

import secrets
import string

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from arsip.csvutil import baca_csv, tulis_csv
from arsip.models import WajibGantiSandi

PERAN = {
    "pembaca": [],
    "pengunggah": ["Pengunggah"],
    "reviewer": ["Reviewer"],
    "admin": ["Admin Arsip"],
}
HURUF = string.ascii_letters + string.digits


def sandi_acak(panjang=10):
    # Hindari karakter yang mudah tertukar saat dibacakan/diketik ulang.
    pilihan = [c for c in HURUF if c not in "0O1lI"]
    return "".join(secrets.choice(pilihan) for _ in range(panjang))


class Command(BaseCommand):
    help = "Buat akun pengguna massal dari CSV (kolom: nrp;nama;peran;email)."

    def add_arguments(self, parser):
        parser.add_argument("csv")
        parser.add_argument("--keluaran", required=True, help="File CSV berisi username & kata sandi awal")

    @transaction.atomic
    def handle(self, *args, **opt):
        User = get_user_model()
        baris = baca_csv(opt["csv"])
        if not baris or "nrp" not in baris[0]:
            raise CommandError("CSV harus memiliki kolom 'nrp' dan 'nama'.")
        grup = {g.name: g for g in Group.objects.all()}

        keluaran, dibuat, dilewati = [], 0, 0
        for b in baris:
            nrp = b.get("nrp", "").replace(" ", "")
            if not nrp:
                continue
            peran = (b.get("peran") or "pembaca").lower()
            if peran not in PERAN:
                raise CommandError(f"Peran '{peran}' untuk NRP {nrp} tidak dikenal. Pilihan: {', '.join(PERAN)}")
            if User.objects.filter(username=nrp).exists():
                dilewati += 1
                self.stdout.write(self.style.WARNING(f"{nrp}: sudah ada, dilewati"))
                continue
            nama = b.get("nama", "")
            depan, _, belakang = nama.partition(" ")
            sandi = sandi_acak()
            u = User.objects.create_user(
                username=nrp, password=sandi, email=b.get("email", ""), first_name=depan[:150], last_name=belakang[:150]
            )
            WajibGantiSandi.objects.create(pengguna=u)  # sandi awal harus diganti saat login pertama
            if peran == "admin":
                u.is_staff = True
                u.save(update_fields=["is_staff"])
            for nama_grup in PERAN[peran]:
                if nama_grup in grup:
                    u.groups.add(grup[nama_grup])
            keluaran.append({"username": nrp, "nama": nama, "peran": peran, "kata_sandi_awal": sandi})
            dibuat += 1

        tulis_csv(opt["keluaran"], ["username", "nama", "peran", "kata_sandi_awal"], keluaran)
        self.stdout.write(self.style.SUCCESS(f"{dibuat} akun dibuat, {dilewati} dilewati. Sandi awal: {opt['keluaran']}"))
        self.stdout.write(self.style.WARNING("Simpan file keluaran dengan aman dan hapus setelah dibagikan."))
