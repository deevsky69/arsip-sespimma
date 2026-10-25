"""Logika bisnis arsip: simpan unggahan, ekstraksi, pengindeksan, dan review."""

import logging
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import kemiripan, ocr, pdf, pencarian
from .models import Dokumen, HalamanDokumen, hitung_sha256
from .sampul import baca_sampul

log = logging.getLogger(__name__)


class DokumenDuplikat(Exception):
    def __init__(self, dokumen_lama):
        self.dokumen_lama = dokumen_lama
        super().__init__(f"File yang sama persis sudah ada di arsip: {dokumen_lama}")


class MetadataKurang(ValueError):
    """Kolom wajib kosong dan tidak bisa dibaca dari sampul PDF."""


# Judul sementara untuk PDF hasil scan yang sampulnya belum terbaca; diganti setelah OCR selesai.
JUDUL_SEMENTARA = "[Menunggu OCR] "


# Kolom Dokumen <- atribut InfoSampul. Hanya diisi bila kolom dokumen masih kosong.
PETA_SAMPUL = {
    "judul": "judul",
    "topik": "topik",
    "nomor_tugas": "nomor_tugas",
    "penulis": "nama",
    "nrp_penulis": "nrp",
    "nomor_serdik": "nomor_serdik",
    "kelompok": "pokjar",
    "lokus": "lokus",
    "kata_kunci": "kata_kunci",
    "abstrak": "abstrak",
}


def lengkapi_dari_sampul(dok: Dokumen, halaman: list[str]) -> list[str]:
    """Isi kolom metadata yang masih kosong dari halaman sampul. Kembalikan nama kolom yang terisi."""
    info = baca_sampul(halaman)
    terisi = []
    for kolom, atribut in PETA_SAMPUL.items():
        nilai = getattr(info, atribut)
        if nilai not in ("", None) and getattr(dok, kolom) in ("", None):
            field = Dokumen._meta.get_field(kolom)
            if isinstance(nilai, str) and field.max_length:
                nilai = nilai[: field.max_length]
            setattr(dok, kolom, nilai)
            terisi.append(kolom)
    return terisi


def cari_duplikat_persis(sha256: str, kecuali_id=None):
    qs = Dokumen.objects.filter(sha256=sha256).exclude(status=Dokumen.Status.DITOLAK)
    if kecuali_id:
        qs = qs.exclude(pk=kecuali_id)
    return qs.first()


def proses_teks(dok: Dokumen, hasil: pdf.HasilEkstraksi | None = None):
    """Ekstrak teks PDF dokumen, simpan per halaman, dan perbarui indeks pencarian."""
    if hasil is None:
        hasil = pdf.ekstrak(dok.path_berkas)
    with transaction.atomic():
        HalamanDokumen.objects.filter(dokumen=dok).delete()
        HalamanDokumen.objects.bulk_create(
            [HalamanDokumen(dokumen=dok, nomor=i, teks=t) for i, t in enumerate(hasil.halaman, start=1)],
            batch_size=500,
        )
        Dokumen.objects.filter(pk=dok.pk).update(
            jumlah_halaman=hasil.jumlah_halaman,
            jumlah_kata=hasil.jumlah_kata,
            perlu_ocr=hasil.perlu_ocr,
        )
        dok.jumlah_halaman = hasil.jumlah_halaman
        dok.jumlah_kata = hasil.jumlah_kata
        dok.perlu_ocr = hasil.perlu_ocr
        pencarian.indeks_dokumen(dok, hasil.halaman)
    if not hasil.perlu_ocr:
        try:
            kemiripan.perbarui(dok)
        except Exception:  # cek kemiripan tidak boleh menggagalkan unggahan
            log.exception("Cek kemiripan dokumen #%s gagal", dok.pk)
    return hasil


def simpan_dokumen_baru(dok: Dokumen, berkas, pengunggah=None, terbitkan=False, hasil=None) -> Dokumen:
    """
    `dok` adalah instance Dokumen yang metadatanya sudah diisi tapi belum disimpan.
    Kolom yang dikosongkan (judul, penulis, topik, lokus, abstrak, ...) diisi dari sampul PDF.
    `berkas` adalah UploadedFile/File berisi PDF. `hasil` (opsional) = hasil pdf.ekstrak bila sudah ada.

    Melempar pdf.PDFTidakValid, DokumenDuplikat, atau MetadataKurang.
    """
    sha = hitung_sha256(berkas)
    lama = cari_duplikat_persis(sha)
    if lama:
        raise DokumenDuplikat(lama)

    isi = berkas.read()
    berkas.seek(0)
    if hasil is None:
        hasil = pdf.ekstrak(isi)  # validasi PDF sebelum menyimpan apa pun

    # Dicatat SEBELUM OCR sampul: setelah sampul terbaca, rata-rata teks per halaman naik sehingga
    # dokumen tidak lagi terlihat seperti scan, padahal halaman sisanya masih perlu di-OCR.
    antre_ocr = hasil.perlu_ocr and settings.ARSIP_OCR_OTOMATIS
    ocr.lengkapi_sampul(isi, hasil)  # PDF hasil scan: OCR halaman sampul agar metadata terbaca
    lengkapi_dari_sampul(dok, hasil.halaman)
    kurang = [nama for nama, kolom in (("judul", "judul"), ("penulis", "penulis")) if not getattr(dok, kolom).strip()]
    if kurang and not antre_ocr:
        raise MetadataKurang(
            f"{' dan '.join(kurang).capitalize()} tidak terbaca dari sampul PDF. Silakan isi secara manual."
        )
    if not dok.judul.strip():
        nama = Path(getattr(berkas, "name", "") or "dokumen.pdf").stem
        dok.judul = (JUDUL_SEMENTARA + nama)[:500]

    dok.sha256 = sha
    dok.ukuran_berkas = len(isi)
    dok.nama_berkas_asli = (getattr(berkas, "name", "") or "")[-300:]
    dok.diunggah_oleh = pengunggah
    if terbitkan:
        dok.status = Dokumen.Status.TERBIT
        dok.direview_oleh = pengunggah
        dok.direview_pada = timezone.now()
    else:
        dok.status = Dokumen.Status.MENUNGGU

    with transaction.atomic():
        dok.berkas.save("x.pdf", berkas, save=False)
        try:
            dok.save()
            proses_teks(dok, hasil)
        except Exception:
            dok.berkas.delete(save=False)
            raise
    log.info("Dokumen #%s diunggah oleh %s (%s halaman)", dok.pk, pengunggah, hasil.jumlah_halaman)
    if antre_ocr:
        ocr.antrekan(dok)
    return dok


def selesai_ocr(dok: Dokumen, halaman_teks: list[str]):
    """Simpan teks hasil OCR: lengkapi metadata yang masih kosong, indeks ulang, cek kemiripan."""
    hasil = pdf.HasilEkstraksi(halaman=halaman_teks)
    sementara = dok.judul if dok.judul.startswith(JUDUL_SEMENTARA) else None
    if sementara:
        dok.judul = ""
    terisi = set(lengkapi_dari_sampul(dok, hasil.halaman))
    if not dok.judul:
        dok.judul = sementara or ""
    # Hanya kolom metadata yang disimpan, agar status/kemajuan OCR yang diperbarui terpisah tidak tertimpa.
    dok.save(update_fields=sorted(terisi | {"judul", "diubah"}))
    proses_teks(dok, hasil)


def putuskan_review(dok: Dokumen, reviewer, setujui: bool, catatan: str = ""):
    dok.status = Dokumen.Status.TERBIT if setujui else Dokumen.Status.DITOLAK
    dok.direview_oleh = reviewer
    dok.direview_pada = timezone.now()
    dok.catatan_review = catatan
    dok.save(update_fields=["status", "direview_oleh", "direview_pada", "catatan_review", "diubah"])
    return dok
