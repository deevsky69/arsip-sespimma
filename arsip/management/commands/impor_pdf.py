"""
Impor massal PDF dari sebuah folder (mis. hasil unduhan folder Google Drive pengumpulan tugas).

Metadata dibaca otomatis dari halaman sampul (judul, topik, nama, NRP, nomor serdik,
pokjar, angkatan, tahun, abstrak, kata kunci, lokus). Nama subfolder ikut dipakai:
  - subfolder "NN - NAMA SERDIK"           -> nama penulis bila tidak terbaca di sampul
  - subfolder "NKP", "NKP-3", "PB", ...    -> kategori

Alur yang disarankan:

  1. Uji coba:                 python manage.py impor_pdf "D:\\Unduhan\\NKP-3" --kering
  2. (Opsional) periksa CSV:   python manage.py impor_pdf "D:\\Unduhan\\NKP-3" --buat-csv nkp3.csv
  3. Impor:                    python manage.py impor_pdf "D:\\Unduhan\\NKP-3" [--csv nkp3.csv] --terbit

Tanpa --csv, semua PDF langsung diimpor memakai hasil pembacaan otomatis.
Dari situs web, fitur yang sama tersedia di menu "Impor Drive".
"""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from arsip import pdf
from arsip.csvutil import baca_csv, tulis_csv
from arsip.impor import KOLOM, OpsiImpor, daftar_pdf, impor_folder, peta_kategori, ringkas, tebak_metadata


class Command(BaseCommand):
    help = "Impor massal file PDF dari folder ke arsip (metadata dibaca otomatis dari sampul)."

    def add_arguments(self, parser):
        parser.add_argument("folder", help="Folder berisi file PDF (subfolder ikut dibaca)")
        parser.add_argument("--buat-csv", metavar="FILE", help="Hanya tulis hasil pembacaan ke CSV, tanpa impor")
        parser.add_argument("--csv", metavar="FILE", help="CSV metadata (kolom yang diisi menimpa hasil otomatis)")
        parser.add_argument("--angkatan", type=int, help="Nomor angkatan bila tidak terbaca di sampul")
        parser.add_argument("--tahun", type=int, help="Tahun angkatan bila tidak terbaca di sampul")
        parser.add_argument("--kategori", help="Kode kategori bila tidak terbaca, mis. NKP")
        parser.add_argument("--terbit", action="store_true", help="Langsung terbitkan (tanpa antrean review)")
        parser.add_argument("--pengunggah", help="Username yang dicatat sebagai pengunggah")
        parser.add_argument("--kering", action="store_true", help="Uji coba: periksa saja tanpa menyimpan")

    def handle(self, *args, **opt):
        folder = Path(opt["folder"])
        if not folder.is_dir():
            raise CommandError(f"Folder tidak ditemukan: {folder}")
        semua_pdf = daftar_pdf(folder)
        if not semua_pdf:
            raise CommandError("Tidak ada file PDF di folder tersebut.")

        opsi = OpsiImpor(
            kategori=opt["kategori"] or "",
            angkatan=opt["angkatan"],
            tahun=opt["tahun"],
            terbitkan=opt["terbit"],
            kering=opt["kering"],
        )
        if opt["buat_csv"]:
            return self._buat_csv(folder, semua_pdf, opsi, opt["buat_csv"])

        if opt["csv"]:
            for b in baca_csv(opt["csv"]):
                kunci = b.get("nama_file", "").replace("\\", "/").lower()
                if kunci:
                    opsi.metadata[kunci] = b
            for k in opsi.metadata:
                if not (folder / k).is_file():
                    self.stderr.write(self.style.WARNING(f"Baris CSV tanpa file: {k}"))
        if opt["pengunggah"]:
            try:
                opsi.pengunggah = get_user_model().objects.get(username=opt["pengunggah"])
            except get_user_model().DoesNotExist:
                raise CommandError(f"Pengguna '{opt['pengunggah']}' tidak ditemukan.")

        semua = []
        n = len(semua_pdf)
        for i, h in enumerate(impor_folder(folder, opsi, catat=self.stdout.write), start=1):
            semua.append(h)
            label = f"[{i}/{n}] {Path(h.nama_file)}"
            if h.status == "berhasil":
                self.stdout.write(f"{label}: OK #{h.dokumen_id} ({h.jumlah_halaman} hlm){' - PERLU OCR' if h.perlu_ocr else ''}")
            elif h.status == "duplikat":
                self.stdout.write(self.style.WARNING(f"{label}: dilewati, {h.pesan}"))
            elif h.status == "dilewati":
                self.stderr.write(self.style.WARNING(f"{label}: dilewati ({h.pesan})"))
            elif h.status == "uji":
                self.stdout.write(
                    f"{label}: {h.pesan}\n      {h.kategori} {h.nomor_tugas or ''} | ak {h.angkatan} | "
                    f"{h.penulis or '(TANPA PENULIS)'} | {h.lokus or '-'}\n      {h.judul[:110] or '(TANPA JUDUL)'}"
                )
            else:
                self.stderr.write(self.style.ERROR(f"{label}: GAGAL - {h.pesan}"))

        if opt["kering"]:
            self.stdout.write(self.style.SUCCESS("Uji coba selesai, tidak ada yang disimpan."))
            return
        j = ringkas(semua)
        self.stdout.write(
            self.style.SUCCESS(f"Selesai: {j['berhasil']} berhasil, {j['duplikat']} duplikat, {j['gagal']} gagal.")
        )
        if j["perlu_ocr"]:
            self.stdout.write(self.style.WARNING(f"{j['perlu_ocr']} dokumen hasil scan perlu OCR (fase 2)."))

    def _buat_csv(self, folder, semua_pdf, opsi, tujuan):
        kategori_map = peta_kategori()
        baris = []
        for p in semua_pdf:
            rel = p.relative_to(folder)
            try:
                data, _ = tebak_metadata(p, rel, opsi, kategori_map)
            except pdf.PDFTidakValid as e:
                self.stderr.write(self.style.ERROR(f"{rel}: {e}"))
                data = {"nama_file": rel.as_posix()}
            baris.append(data)
        tulis_csv(tujuan, KOLOM, baris)
        kosong = {k: sum(1 for b in baris if not b.get(k)) for k in ("judul", "penulis", "kategori", "angkatan")}
        self.stdout.write(self.style.SUCCESS(f"{len(baris)} baris ditulis ke {tujuan}"))
        for k, n in kosong.items():
            if n:
                self.stdout.write(self.style.WARNING(f"  {n} baris belum ada {k}-nya; lengkapi di Excel."))
        self.stdout.write("Periksa/perbaiki di Excel (beberapa penulis dipisah dengan |), lalu jalankan dengan --csv.")
