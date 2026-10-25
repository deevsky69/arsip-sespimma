"""
Menjalankan TugasImpor (unduh folder Google Drive -> baca sampul -> simpan) di latar belakang.

Tugas dijalankan sebagai proses terpisah (`manage.py jalankan_impor_drive <id>`, lihat arsip/proses.py)
supaya situs tidak melambat dan impor tidak terputus bila server web di-restart. Kemajuan disimpan ke
database, dan halaman tugas memuat ulang dirinya untuk menampilkannya. Log-nya di <folder data>/impor.log.
"""

import logging
import shutil
from pathlib import PurePosixPath

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import drive, proses
from .impor import HasilFile, OpsiImpor, impor_folder
from .models import TugasImpor

log = logging.getLogger(__name__)
EKSTENSI_WORD = (".doc", ".docx")


def tugas_berjalan():
    return [t for t in TugasImpor.objects.filter(
        status__in=[TugasImpor.Status.ANTRE, TugasImpor.Status.MENGUNDUH, TugasImpor.Status.MEMPROSES]
    ) if not t.terputus]


def mulai(tugas: TugasImpor):
    """Jalankan tugas: langsung (mode uji/sinkron) atau sebagai proses terpisah setelah transaksi tersimpan."""
    if getattr(settings, "ARSIP_IMPOR_SINKRON", False):
        jalankan(tugas.pk)
    else:
        pk = tugas.pk
        transaction.on_commit(lambda: proses.luncurkan(["jalankan_impor_drive", str(pk)], "impor.log"))


def _simpan(tugas, *kolom):
    tugas.save(update_fields=[*kolom, "diperbarui"])


def _catat(tugas, pesan):
    tugas.log += f"[{timezone.localtime():%H:%M:%S}] {pesan}\n"
    _simpan(tugas, "log")


def word_tanpa_pdf(berkas: list[drive.BerkasDrive]) -> list[str]:
    """File Word di folder yang tidak berisi PDF sama sekali (serdik lupa mengunggah versi PDF)."""
    folder_ber_pdf = {str(PurePosixPath(b.path).parent) for b in berkas if b.pdf}
    return [
        b.path for b in berkas
        if b.path.lower().endswith(EKSTENSI_WORD) and str(PurePosixPath(b.path).parent) not in folder_ber_pdf
    ]


def jalankan(pk):
    tugas = TugasImpor.objects.get(pk=pk)
    folder = settings.DATA_DIR / "impor-drive" / f"tugas-{pk}"
    shutil.rmtree(folder, ignore_errors=True)
    try:
        tugas.status, tugas.hasil, tugas.pesan_galat, tugas.jumlah_selesai = TugasImpor.Status.MENGUNDUH, [], "", 0
        _simpan(tugas, "status", "hasil", "pesan_galat", "jumlah_selesai")
        _catat(tugas, "Membaca isi folder Google Drive...")

        semua = drive.daftar_berkas(tugas.link)
        pdf = [b for b in semua if b.pdf]
        word = word_tanpa_pdf(semua)
        tugas.jumlah_total, tugas.jumlah_bukan_pdf = len(pdf), len(semua) - len(pdf)
        _simpan(tugas, "jumlah_total", "jumlah_bukan_pdf")
        _catat(tugas, f"Ditemukan {len(semua)} file: {len(pdf)} PDF akan diunduh, {len(semua) - len(pdf)} file lain diabaikan.")
        if not pdf:
            raise drive.GagalDrive("Tidak ada file PDF di folder tersebut.")

        hasil = [
            HasilFile(p, "dilewati", "hanya ada file Word; minta penulis mengunggah versi PDF").sebagai_dict()
            for p in word
        ]
        for b in pdf:
            try:
                drive.unduh(b, folder)
            except drive.GagalDrive as e:
                hasil.append(HasilFile(b.path, "gagal", str(e)).sebagai_dict())
            tugas.jumlah_selesai += 1
            _simpan(tugas, "jumlah_selesai")

        tugas.status, tugas.jumlah_selesai = TugasImpor.Status.MEMPROSES, 0
        _simpan(tugas, "status", "jumlah_selesai")
        _catat(tugas, "Unduhan selesai. Membaca sampul dan menyimpan ke arsip...")
        opsi = OpsiImpor(
            kategori=tugas.kategori_default.kode if tugas.kategori_default else "",
            angkatan=tugas.angkatan_default,
            tahun=tugas.tahun_default,
            terbitkan=tugas.terbitkan,
            pengunggah=tugas.dibuat_oleh,
        )
        if folder.exists():
            for h in impor_folder(folder, opsi, catat=lambda pesan: _catat(tugas, pesan)):
                hasil.append(h.sebagai_dict())
                tugas.hasil, tugas.jumlah_selesai = hasil, tugas.jumlah_selesai + 1
                _simpan(tugas, "hasil", "jumlah_selesai")

        tugas.hasil, tugas.status = hasil, TugasImpor.Status.SELESAI
        _simpan(tugas, "hasil", "status")
        j = tugas.ringkasan()
        _catat(tugas, f"Selesai: {j['berhasil']} berhasil, {j['duplikat']} duplikat, {j['gagal']} gagal, {j['dilewati']} dilewati.")
    except drive.GagalDrive as e:
        tugas.status, tugas.pesan_galat = TugasImpor.Status.GAGAL, str(e)
        _simpan(tugas, "status", "pesan_galat")
    except Exception as e:
        log.exception("Tugas impor #%s gagal", pk)
        tugas.status, tugas.pesan_galat = TugasImpor.Status.GAGAL, f"Terjadi kesalahan tak terduga: {e}"
        _simpan(tugas, "status", "pesan_galat")
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return tugas
