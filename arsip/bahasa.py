"""
Pengolahan bahasa Indonesia untuk pencarian: kata dasar, sinonim/singkatan, dan daftar pustaka.
"""

import re
from functools import lru_cache

POLA_KATA = re.compile(r"\w+", re.UNICODE)

# ---------------------------------------------------------------------------
# Kata dasar (stemming) memakai Sastrawi: "penanganan", "menangani", "ditangani" -> "tangan"
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _stemmer():
    from Sastrawi.Dictionary.ArrayDictionary import ArrayDictionary
    from Sastrawi.Stemmer.Stemmer import Stemmer
    from Sastrawi.Stemmer.StemmerFactory import StemmerFactory

    class KamusCepat(ArrayDictionary):
        # Kamus bawaan Sastrawi disimpan sebagai list sehingga setiap pengecekan kata memindai
        # ~30 ribu entri (±30 ms per kata). Dengan set, pengecekan menjadi instan.
        def __init__(self, words):
            self.words = {w for w in words if w and w.strip()}

        def add(self, word):
            if word and word.strip():
                self.words.add(word)

    return Stemmer(KamusCepat(StemmerFactory().get_words()))


@lru_cache(maxsize=200_000)
def akar(kata: str) -> str:
    kata = kata.lower()
    if len(kata) <= 3 or not kata.isalpha():
        return kata
    return _stemmer().stem(kata) or kata


def teks_akar(teks: str) -> str:
    """Teks yang setiap katanya diganti kata dasarnya (urutan kata dipertahankan)."""
    return " ".join(akar(k) for k in POLA_KATA.findall(teks or ""))


# ---------------------------------------------------------------------------
# Sinonim & singkatan. Setiap baris = satu kelompok istilah yang dianggap sama.
# Silakan ditambah; kata dalam satu kelompok dipisah koma.
# ---------------------------------------------------------------------------

KELOMPOK_SINONIM = """
narkoba, narkotika, napza, psikotropika
pungli, pungutan liar
kkn, korupsi kolusi nepotisme, korupsi kolusi dan nepotisme
tipikor, tindak pidana korupsi
kamtibmas, keamanan dan ketertiban masyarakat
harkamtibmas, pemeliharaan keamanan dan ketertiban masyarakat
polres, kepolisian resor
polresta, kepolisian resor kota
polda, kepolisian daerah
polsek, kepolisian sektor
polri, kepolisian negara republik indonesia
bhabinkamtibmas, bhayangkara pembina keamanan dan ketertiban masyarakat
siber, cyber
lantas, lalu lintas
laka, kecelakaan
curanmor, pencurian kendaraan bermotor
sdm, sumber daya manusia
dumas, pengaduan masyarakat
propam, profesi dan pengamanan
rj, restorative justice, keadilan restoratif
ham, hak asasi manusia
phh, penanganan huru hara
tkp, tempat kejadian perkara
bko, bawah kendali operasi
anev, analisa dan evaluasi, analisis dan evaluasi
sop, standar operasional prosedur
ott, operasi tangkap tangan
kdrt, kekerasan dalam rumah tangga
tppo, tindak pidana perdagangan orang
karhutla, kebakaran hutan dan lahan
pemda, pemerintah daerah
ormas, organisasi kemasyarakatan
medsos, media sosial
hoaks, hoax, berita bohong
tik, teknologi informasi dan komunikasi
"""


@lru_cache(maxsize=1)
def _peta_sinonim() -> dict[tuple, tuple]:
    peta = {}
    for baris in KELOMPOK_SINONIM.strip().splitlines():
        anggota = tuple(tuple(POLA_KATA.findall(a.lower())) for a in baris.split(",") if a.strip())
        for a in anggota:
            peta[a] = anggota
    return peta


def kelompok_sinonim(kata: tuple) -> tuple:
    """('pungli',) -> (('pungli',), ('pungutan', 'liar')). Bila tidak ada sinonim: ((kata),)."""
    return _peta_sinonim().get(tuple(kata), (tuple(kata),))


def panjang_sinonim_terpanjang() -> int:
    return max(len(k) for k in _peta_sinonim())


# ---------------------------------------------------------------------------
# Daftar pustaka: dipisah dari isi supaya tidak mendominasi hasil pencarian.
# ---------------------------------------------------------------------------

_JUDUL_PUSTAKA = re.compile(
    # "DAFTAR PUSTAKA", "D. REFERENSI", "D. Referensi.", "5. Daftar Pustaka:" (satu baris sendiri), atau
    # "DAFTAR PUSTAKA" kapital yang menempel dengan teks berikutnya akibat ekstraksi PDF.
    r"^[ \t]*(?:(?:[A-Za-z]|\d{1,2}|[IVX]{1,4})\.[ \t]*)?"
    r"(?i:DAFTAR[ \t]+PUSTAKA|DAFTAR[ \t]+REFERENSI|REFERENSI|BIBLIOGRAFI|DAFTAR[ \t]+RUJUKAN|RUJUKAN)[ \t]*[:.]?[ \t]*$"
    r"|^[ \t]*DAFTAR[ \t]+PUSTAKA",
    re.M,
)
_JUDUL_SETELAH_PUSTAKA = re.compile(
    r"^[ \t]*(?:LAMPIRAN|DAFTAR[ \t]+LAMPIRAN|DAFTAR[ \t]+RIWAYAT[ \t]+HIDUP|RIWAYAT[ \t]+HIDUP|BIODATA)\b", re.I | re.M
)


def pisah_pustaka(halaman: list[str]) -> list[tuple[str, str]]:
    """
    Kembalikan [(teks_isi, teks_pustaka), ...] per halaman. Judul "DAFTAR PUSTAKA" dicari mulai
    30% dokumen (agar baris daftar isi di depan tidak terhitung); bagian pustaka berakhir di
    "LAMPIRAN" / "RIWAYAT HIDUP".
    """
    hasil = [(t, "") for t in halaman]
    mulai = int(len(halaman) * 0.3)
    for i in range(mulai, len(halaman)):
        m = _JUDUL_PUSTAKA.search(halaman[i])
        if not m:
            continue
        hasil[i] = (halaman[i][: m.start()], halaman[i][m.start():])
        for j in range(i + 1, len(halaman)):
            akhir = _JUDUL_SETELAH_PUSTAKA.search(halaman[j])
            if akhir:
                hasil[j] = (halaman[j][akhir.start():], halaman[j][: akhir.start()])
                break
            hasil[j] = ("", halaman[j])
        break
    return hasil
