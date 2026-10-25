"""Pengolahan PDF: ekstraksi teks per halaman dan watermark pembaca."""

import re
from dataclasses import dataclass, field

import pymupdf

# Rata-rata karakter per halaman di bawah angka ini dianggap PDF hasil scan.
AMBANG_KARAKTER_SCAN = 40


class PDFTidakValid(Exception):
    pass


@dataclass
class HasilEkstraksi:
    halaman: list[str] = field(default_factory=list)
    judul_metadata: str = ""

    @property
    def jumlah_halaman(self):
        return len(self.halaman)

    @property
    def jumlah_kata(self):
        return sum(len(t.split()) for t in self.halaman)

    @property
    def perlu_ocr(self):
        if not self.halaman:
            return True
        total = sum(len(t.strip()) for t in self.halaman)
        return total / len(self.halaman) < AMBANG_KARAKTER_SCAN


def _rapikan(teks: str) -> str:
    teks = teks.replace("­", "").replace("\x00", "")
    teks = re.sub(r"[ \t ]+", " ", teks)
    teks = re.sub(r"\n{3,}", "\n\n", teks)
    return teks.strip()


def buka(sumber) -> pymupdf.Document:
    """sumber: path (str/Path) atau bytes."""
    try:
        if isinstance(sumber, (bytes, bytearray)):
            doc = pymupdf.open(stream=sumber, filetype="pdf")
        else:
            doc = pymupdf.open(sumber, filetype="pdf")
    except Exception as e:  # pymupdf melempar beberapa jenis error berbeda
        raise PDFTidakValid(f"File tidak dapat dibaca sebagai PDF: {e}") from e
    if doc.needs_pass:
        doc.close()
        raise PDFTidakValid("PDF terkunci kata sandi. Hapus kata sandinya dulu sebelum diunggah.")
    if doc.page_count == 0:
        doc.close()
        raise PDFTidakValid("PDF tidak memiliki halaman.")
    return doc


def ekstrak(sumber) -> HasilEkstraksi:
    flags = pymupdf.TEXT_DEHYPHENATE | pymupdf.TEXT_PRESERVE_LIGATURES | pymupdf.TEXT_MEDIABOX_CLIP
    with buka(sumber) as doc:
        halaman = [_rapikan(page.get_text("text", flags=flags, sort=True)) for page in doc]
        judul = (doc.metadata or {}).get("title") or ""
    return HasilEkstraksi(halaman=halaman, judul_metadata=judul.strip())


def beri_watermark(path, baris_utama: str, baris_kaki: str) -> bytes:
    """Kembalikan isi PDF dengan watermark diagonal dan catatan kaki di setiap halaman."""
    with buka(path) as doc:
        for page in doc:
            # Koordinat dihitung pada tampilan halaman (sudah memperhitungkan rotasi),
            # lalu dipetakan ke koordinat asli halaman.
            lebar, tinggi = page.rect.width, page.rect.height
            derot = page.derotation_matrix
            ukuran = max(14, min(lebar, tinggi) / 22)
            panjang = pymupdf.get_text_length(baris_utama, fontname="helv", fontsize=ukuran)
            tengah = pymupdf.Point(lebar / 2, tinggi / 2)
            awal = pymupdf.Point(tengah.x - panjang / 2, tengah.y + ukuran / 3)
            sudut = 35 + page.rotation
            page.insert_text(
                awal * derot,
                baris_utama,
                fontsize=ukuran,
                fontname="helv",
                color=(0.55, 0.55, 0.6),
                fill_opacity=0.22,
                morph=(tengah * derot, pymupdf.Matrix(sudut)),
                overlay=True,
            )
            ukuran_kaki = 7
            page.insert_text(
                pymupdf.Point(18, tinggi - 8) * derot,
                baris_kaki,
                fontsize=ukuran_kaki,
                fontname="helv",
                color=(0.4, 0.4, 0.45),
                fill_opacity=0.8,
                rotate=page.rotation,
                overlay=True,
            )
        return doc.tobytes(garbage=1)
