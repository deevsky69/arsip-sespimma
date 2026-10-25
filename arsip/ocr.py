"""
OCR untuk PDF hasil scan, memakai mesin Tesseract yang sudah tertanam di PyMuPDF.

Yang dibutuhkan hanya model bahasa (ind.traineddata, eng.traineddata) di folder ARSIP_TESSDATA;
pasang dengan `manage.py siapkan_ocr`. Hanya halaman tanpa teks yang di-OCR, sehingga PDF campuran
(sebagian ketik, sebagian scan) tetap cepat.

Alur:
- saat unggah/impor: 3 halaman pertama di-OCR langsung agar sampul (judul, nama, angkatan) terbaca;
- sisanya masuk antrean dan dikerjakan oleh satu proses pekerja terpisah (`manage.py jalankan_ocr`),
  dokumen demi dokumen; kemajuannya tersimpan di Dokumen.status_ocr / ocr_kemajuan dan log-nya
  di <folder data>/ocr.log.
"""

import logging
import os
import time
from datetime import timedelta
from pathlib import Path

import pymupdf
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import pdf

log = logging.getLogger(__name__)
HALAMAN_SAMPUL = 3
SUMBER_MODEL = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/{}.traineddata"


class OCRTidakTersedia(Exception):
    pass


# ---------------------------------------------------------------------------
# Mesin
# ---------------------------------------------------------------------------


def folder_model() -> Path:
    return Path(settings.ARSIP_TESSDATA)


def bahasa() -> list[str]:
    return [b for b in settings.ARSIP_OCR_BAHASA.split("+") if b]


def model_kurang() -> list[str]:
    return [b for b in bahasa() if not (folder_model() / f"{b}.traineddata").exists()]


def tersedia() -> bool:
    return not model_kurang()


def _perlu(teks: str) -> bool:
    return len((teks or "").strip()) < pdf.AMBANG_KARAKTER_SCAN


def ocr_halaman(page) -> str:
    if not tersedia():
        raise OCRTidakTersedia(
            f"Model bahasa OCR ({', '.join(model_kurang())}) belum ada di {folder_model()}. "
            "Jalankan: python manage.py siapkan_ocr"
        )
    tp = page.get_textpage_ocr(
        flags=pymupdf.TEXT_DEHYPHENATE,
        language=settings.ARSIP_OCR_BAHASA,
        dpi=settings.ARSIP_OCR_DPI,
        full=True,
        tessdata=str(folder_model()),
    )
    return pdf._rapikan(page.get_text("text", textpage=tp, sort=True))


def ocr_dokumen(sumber, halaman_teks: list[str], saat_kemajuan=None, hanya=None) -> list[str]:
    """
    Kembalikan teks per halaman: halaman yang sudah berteks dipakai apa adanya, halaman kosong di-OCR.
    `hanya`: batasi ke indeks halaman tertentu (mis. range(3) untuk sampul).
    `saat_kemajuan(selesai, total)` dipanggil setiap satu halaman selesai.
    """
    hasil = list(halaman_teks)
    with pdf.buka(sumber) as doc:
        while len(hasil) < doc.page_count:
            hasil.append("")
        target = [i for i in (hanya if hanya is not None else range(doc.page_count)) if i < doc.page_count]
        for n, i in enumerate(target, start=1):
            if _perlu(hasil[i]):
                hasil[i] = ocr_halaman(doc[i])
            if saat_kemajuan:
                saat_kemajuan(n, len(target))
    return hasil


def lengkapi_sampul(sumber, ekstraksi: "pdf.HasilEkstraksi") -> bool:
    """OCR beberapa halaman awal PDF hasil scan agar metadata sampul bisa dibaca. Mengubah `ekstraksi`."""
    if not (settings.ARSIP_OCR_OTOMATIS and ekstraksi.perlu_ocr and tersedia()):
        return False
    awal = range(min(HALAMAN_SAMPUL, ekstraksi.jumlah_halaman))
    if not any(_perlu(ekstraksi.halaman[i]) for i in awal):
        return False
    try:
        ekstraksi.halaman = ocr_dokumen(sumber, ekstraksi.halaman, hanya=awal)
        return True
    except Exception:
        log.exception("OCR sampul gagal")
        return False


# ---------------------------------------------------------------------------
# Antrean latar belakang
# ---------------------------------------------------------------------------

def antrekan(dok):
    from .models import Dokumen

    Dokumen.objects.filter(pk=dok.pk).update(
        status_ocr=Dokumen.StatusOCR.ANTRE, ocr_kemajuan=0, ocr_pesan="", ocr_diperbarui=timezone.now()
    )
    dok.status_ocr = Dokumen.StatusOCR.ANTRE
    mulai_pekerja()


def mulai_pekerja():
    """
    Jalankan pekerja OCR setelah transaksi tersimpan. Pekerja adalah PROSES terpisah
    (`manage.py jalankan_ocr`), bukan thread: OCR memakai CPU penuh dan menahan GIL Python,
    sehingga bila dijalankan di dalam proses web seluruh situs ikut melambat.
    """
    if getattr(settings, "ARSIP_OCR_SINKRON", False):
        proses_antrean()
    else:
        transaction.on_commit(_luncurkan_proses)


# --- Kunci "satu pekerja saja", berupa file yang terus disentuh selama pekerja hidup ---

UMUR_KUNCI_MATI = 10 * 60  # detik tanpa kemajuan -> pekerja dianggap mati


def _berkas_kunci() -> Path:
    return Path(settings.DATA_DIR) / "ocr.lock"


def pekerja_hidup() -> bool:
    try:
        return time.time() - _berkas_kunci().stat().st_mtime < UMUR_KUNCI_MATI
    except FileNotFoundError:
        return False


def _ambil_kunci() -> bool:
    f = _berkas_kunci()
    for _ in range(2):
        try:
            fd = os.open(f, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            if pekerja_hidup():
                return False
            f.unlink(missing_ok=True)  # kunci basi (pekerja sebelumnya mati), ambil alih
    return False


def _sentuh_kunci():
    try:
        os.utime(_berkas_kunci())
    except OSError:
        pass


def _lepas_kunci():
    _berkas_kunci().unlink(missing_ok=True)


def _luncurkan_proses():
    if pekerja_hidup():
        return  # pekerja yang ada akan mengambil dokumen baru dari antrean
    from . import proses

    proses.luncurkan(["jalankan_ocr"], "ocr.log")


def jalankan_pekerja(catat=lambda pesan: None) -> int | None:
    """
    Kerjakan antrean sampai habis dengan memegang kunci. Kembalikan jumlah dokumen yang diproses,
    atau None bila pekerja lain sudah berjalan.
    """
    if not _ambil_kunci():
        return None
    total = 0
    try:
        while True:
            total += proses_antrean(catat)
            _lepas_kunci()
            # Dokumen bisa saja masuk antrean tepat saat kunci dilepas: periksa sekali lagi.
            if not ada_antrean() or not _ambil_kunci():
                return total
    finally:
        if _berkas_kunci().exists() and _berkas_kunci().read_text(errors="ignore").strip() == str(os.getpid()):
            _lepas_kunci()


def ada_antrean() -> bool:
    from .models import Dokumen

    return Dokumen.objects.filter(status_ocr=Dokumen.StatusOCR.ANTRE).exists()


def _ambil_berikutnya():
    """Klaim satu dokumen dari antrean secara atomik (aman bila ada beberapa proses server)."""
    from .models import Dokumen

    S = Dokumen.StatusOCR
    # Dokumen yang "sedang diproses" tetapi tidak bergerak > 15 menit (server sempat mati) diantrekan lagi.
    Dokumen.objects.filter(status_ocr=S.PROSES, ocr_diperbarui__lt=timezone.now() - timedelta(minutes=15)).update(
        status_ocr=S.ANTRE
    )
    for pk in Dokumen.objects.filter(status_ocr=S.ANTRE).order_by("ocr_diperbarui", "pk").values_list("pk", flat=True):
        if Dokumen.objects.filter(pk=pk, status_ocr=S.ANTRE).update(status_ocr=S.PROSES, ocr_diperbarui=timezone.now()):
            return Dokumen.objects.select_related("kategori").get(pk=pk)
    return None


def proses_antrean(catat=lambda pesan: None) -> int:
    jumlah = 0
    while (dok := _ambil_berikutnya()) is not None:
        proses_satu(dok, catat)
        jumlah += 1
    return jumlah


def proses_satu(dok, catat=lambda pesan: None):
    from . import layanan
    from .models import Dokumen

    S = Dokumen.StatusOCR

    def kemajuan(selesai, total):
        Dokumen.objects.filter(pk=dok.pk).update(ocr_kemajuan=selesai, ocr_diperbarui=timezone.now())
        _sentuh_kunci()
        if selesai == total or selesai % 10 == 0:
            catat(f"  #{dok.pk}: {selesai}/{total} halaman")

    try:
        lama = list(dok.halaman.order_by("nomor").values_list("teks", flat=True))
        teks = ocr_dokumen(dok.path_berkas, lama, saat_kemajuan=kemajuan)
        layanan.selesai_ocr(dok, teks)
        dok.refresh_from_db()
        pesan = "" if not dok.perlu_ocr else "Tidak ada teks yang terbaca; periksa kualitas scan."
        Dokumen.objects.filter(pk=dok.pk).update(status_ocr=S.SELESAI, ocr_pesan=pesan, ocr_diperbarui=timezone.now())
        catat(f"#{dok.pk} selesai: {dok.jumlah_kata} kata terbaca.")
    except Exception as e:
        log.exception("OCR dokumen #%s gagal", dok.pk)
        Dokumen.objects.filter(pk=dok.pk).update(
            status_ocr=S.GAGAL, ocr_pesan=str(e)[:500], ocr_diperbarui=timezone.now()
        )
        catat(f"#{dok.pk} GAGAL: {e}")
