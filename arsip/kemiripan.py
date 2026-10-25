"""
Cek kemiripan internal antar naskah, termasuk deteksi naskah yang "hanya mengganti lokus".

Cara kerja:
1. Teks isi (tanpa daftar pustaka) dipecah menjadi kata. Nama tempat/satuan disamarkan menjadi "@"
   (mis. "Polres Garut" -> "polres @", "Kabupaten Bolaang Mongondow" -> "kabupaten @", serta nama
   dari kolom lokus di mana pun muncul) dan angka/tahun menjadi "#". Kata samaran yang berurutan
   digabung, sehingga "Polres Garut" dan "Polres Bolaang Mongondow Utara" sama-sama menjadi "polres @".
2. Setiap rangkaian 5 kata (shingle) di-hash; kumpulan hash = sidik jari dokumen.
3. Hash yang muncul di banyak dokumen (sampul, surat pernyataan, kalimat topik yang ditetapkan)
   dianggap teks templat dan diabaikan.
4. Persentase kemiripan = bagian sidik jari A yang juga ada di B (dan sebaliknya).
5. Untuk pasangan yang mirip, bagian-bagian yang sama disejajarkan untuk laporan berdampingan;
   kata yang sama setelah disamarkan tetapi berbeda aslinya (mis. nama Polres) dihitung sebagai "diganti".
"""

import hashlib
import logging
import math
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from django.db import connection, transaction
from django.db.models import Q
from django.utils.html import escape
from django.utils.safestring import mark_safe

from .bahasa import pisah_pustaka
from .sampul import KATA_HENTI_LOKUS

log = logging.getLogger(__name__)

N = 5  # panjang rangkaian kata
AMBANG_SIMPAN = 5.0  # persen; pasangan di bawah ini tidak disimpan
MIN_KANDIDAT = 15  # minimal hash sama agar sebuah dokumen dihitung sebagai kandidat
MIN_BAGIAN = 15  # minimal kata agar sebuah bagian ditampilkan di laporan
CELAH = 12  # bagian yang terpisah <= CELAH kata digabung (selisihnya = kata yang diubah)
SAMAR, ANGKA = "@", "#"

_KATA = re.compile(r"\w+", re.UNICODE)
_SATUAN = (
    r"polda|polres|polresta|polrestabes|polsek|polsekta|kapolda|kapolres|kapolresta|kapolsek|"
    r"wakapolda|wakapolres|satbrimob|polairud"
)
_WILAYAH = (
    r"kabupaten|kab|kota|provinsi|prov|kecamatan|kec|desa|kelurahan|distrik|kampung|nagari|"
    r"kawasan|pulau|sungai|wilayah hukum|wilkum"
)
_ENTITAS = re.compile(rf"\b(?i:{_SATUAN}|{_WILAYAH})\.?((?:[ \t]+[A-Z][\w'’-]*){{1,5}})")
_KATA_SATUAN = set(_SATUAN.upper().split("|"))


# ---------------------------------------------------------------------------
# Tokenisasi dengan penyamaran
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Unit:
    samar: str  # kata (huruf kecil) atau "@"/"#"
    asli: str  # teks asli (bisa beberapa kata untuk samaran yang digabung)
    halaman: int


def _pola_lokus(lokus: str):
    nama = [
        w for w in _KATA.findall(lokus or "")
        if len(w) >= 3 and w.upper() not in _KATA_SATUAN and w.upper() not in KATA_HENTI_LOKUS and not w.isdigit()
    ]
    return re.compile(r"\b(?:" + "|".join(map(re.escape, nama)) + r")\b", re.I) if nama else None


def _rentang_samar(teks: str, pola_lokus) -> list[tuple[int, int]]:
    rentang = []
    for m in _ENTITAS.finditer(teks):
        mulai = akhir = None
        for w in re.finditer(r"[\w'’-]+", m.group(1)):
            if w.group().upper() in KATA_HENTI_LOKUS or w.group().upper() in _KATA_SATUAN:
                break
            mulai = m.start(1) + w.start() if mulai is None else mulai
            akhir = m.start(1) + w.end()
        if mulai is not None:
            rentang.append((mulai, akhir))
    if pola_lokus:
        rentang.extend((m.start(), m.end()) for m in pola_lokus.finditer(teks))
    return sorted(rentang)


def satuan_teks(halaman: list[str], lokus: str = "") -> list[Unit]:
    pola_lokus = _pola_lokus(lokus)
    hasil: list[Unit] = []
    for nomor, (isi, _pustaka) in enumerate(pisah_pustaka(halaman), start=1):
        rentang, r = _rentang_samar(isi, pola_lokus), 0
        for m in _KATA.finditer(isi):
            while r < len(rentang) and rentang[r][1] <= m.start():
                r += 1
            w = m.group()
            if r < len(rentang) and rentang[r][0] <= m.start() < rentang[r][1]:
                tanda = SAMAR
            elif any(ch.isdigit() for ch in w):
                tanda = ANGKA
            else:
                tanda = w.lower()
            if tanda in (SAMAR, ANGKA) and hasil and hasil[-1].samar == tanda and hasil[-1].halaman == nomor:
                hasil[-1].asli += " " + w
            else:
                hasil.append(Unit(tanda, w, nomor))
    return hasil


def _hash(teks: str) -> int:
    return int.from_bytes(hashlib.blake2b(teks.encode(), digest_size=8).digest(), "big", signed=True)


def hash_per_posisi(unit: list[Unit]) -> list[int | None]:
    """Hash rangkaian N kata yang dimulai di setiap posisi (None untuk rangkaian yang isinya kebanyakan angka/samaran)."""
    hasil = []
    for i in range(len(unit) - N + 1):
        jendela = unit[i : i + N]
        if sum(u.samar in (SAMAR, ANGKA) for u in jendela) >= 3:
            hasil.append(None)
        else:
            hasil.append(_hash(" ".join(u.samar for u in jendela)))
    return hasil


def unit_dokumen(dok) -> list[Unit]:
    return satuan_teks(list(dok.halaman.order_by("nomor").values_list("teks", flat=True)), dok.lokus)


# ---------------------------------------------------------------------------
# Indeks sidik jari
# ---------------------------------------------------------------------------


def simpan_sidik(dok, hashes: set[int]):
    with transaction.atomic(), connection.cursor() as c:
        c.execute("DELETE FROM arsip_sidikjari WHERE dokumen_id = %s", [dok.pk])
        c.executemany("INSERT INTO arsip_sidikjari (dokumen_id, hash) VALUES (%s, %s)", [(dok.pk, h) for h in hashes])


def hash_umum() -> set[int]:
    """Hash teks templat: muncul di >= max(5, 10%) dokumen."""
    with connection.cursor() as c:
        c.execute("SELECT COUNT(DISTINCT dokumen_id) FROM arsip_sidikjari")
        ambang = max(5, math.ceil(0.10 * c.fetchone()[0]))
        c.execute("SELECT hash FROM arsip_sidikjari GROUP BY hash HAVING COUNT(*) >= %s", [ambang])
        return {r[0] for r in c.fetchall()}


def _hash_dokumen(pk) -> set[int]:
    with connection.cursor() as c:
        c.execute("SELECT hash FROM arsip_sidikjari WHERE dokumen_id = %s", [pk])
        return {r[0] for r in c.fetchall()}


def _kandidat(pk) -> list[int]:
    with connection.cursor() as c:
        c.execute(
            """
            SELECT s.dokumen_id FROM arsip_sidikjari s
            WHERE s.dokumen_id != %s AND s.hash IN (SELECT hash FROM arsip_sidikjari WHERE dokumen_id = %s)
            GROUP BY s.dokumen_id HAVING COUNT(*) >= %s
            """,
            [pk, pk, MIN_KANDIDAT],
        )
        return [r[0] for r in c.fetchall()]


# ---------------------------------------------------------------------------
# Penyejajaran bagian yang sama
# ---------------------------------------------------------------------------


@dataclass
class Bagian:
    a0: int
    a1: int
    b0: int
    b1: int
    html_a: str = ""
    html_b: str = ""
    halaman_a: str = ""
    halaman_b: str = ""
    kata_diganti: int = 0
    contoh_diganti: list = field(default_factory=list)

    @property
    def panjang(self):
        return self.a1 - self.a0


def _sejajarkan(ua, ha, ub, hb, umum) -> list[Bagian]:
    peta_b: dict[int, list[int]] = {}
    for j, h in enumerate(hb):
        if h is not None and h not in umum:
            peta_b.setdefault(h, []).append(j)

    lintasan, i = [], 0
    while i < len(ha):
        h = ha[i]
        if h is None or h in umum or h not in peta_b:
            i += 1
            continue
        terbaik = (0, None)
        for j in peta_b[h][:30]:
            # Diperpanjang selama kata sama, tetapi berhenti di batas halaman A agar laporan
            # tersaji per halaman ("hlm 12 di naskah ini ↔ hlm 14 di naskah lain").
            k, hal = 0, ua[i].halaman
            while (
                i + k < len(ua) and j + k < len(ub) and ua[i + k].halaman == hal
                and ua[i + k].samar == ub[j + k].samar
            ):
                k += 1
            if k > terbaik[0]:
                terbaik = (k, j)
        k, j = terbaik
        lintasan.append(Bagian(i, i + k, j, j + k))
        i += max(k, 1)

    gabung: list[Bagian] = []
    for b in lintasan:
        p = gabung[-1] if gabung else None
        if (
            p and ua[b.a0].halaman == ua[p.a0].halaman
            and 0 <= b.a0 - p.a1 <= CELAH and 0 <= b.b0 - p.b1 <= CELAH * 2
        ):
            p.a1, p.b1 = b.a1, b.b1
        else:
            gabung.append(b)
    return [b for b in gabung if b.panjang >= MIN_BAGIAN]


def _rentang_halaman(unit, a, b):
    h0, h1 = unit[a].halaman, unit[b - 1].halaman
    return f"{h0}" if h0 == h1 else f"{h0}–{h1}"


def _isi_tampilan(bagian: Bagian, ua, ub):
    """Isi HTML kedua sisi; kata yang berbeda disorot, kata yang hanya berganti lokus/angka dihitung."""
    sa, sb = ua[bagian.a0 : bagian.a1], ub[bagian.b0 : bagian.b1]
    tanda_a, tanda_b = [False] * len(sa), [False] * len(sb)
    matcher = SequenceMatcher(None, [u.samar for u in sa], [u.samar for u in sb], autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for x, y in zip(range(i1, i2), range(j1, j2)):
                if sa[x].asli.lower() != sb[y].asli.lower():
                    tanda_a[x] = tanda_b[y] = True
                    bagian.kata_diganti += 1
                    if len(bagian.contoh_diganti) < 6 and (sa[x].asli, sb[y].asli) not in bagian.contoh_diganti:
                        bagian.contoh_diganti.append((sa[x].asli, sb[y].asli))
        else:
            for x in range(i1, i2):
                tanda_a[x] = True
            for y in range(j1, j2):
                tanda_b[y] = True

    def html(seri, tanda):
        return mark_safe(" ".join(f'<mark class="beda">{escape(u.asli)}</mark>' if t else escape(u.asli) for u, t in zip(seri, tanda)))

    bagian.html_a, bagian.html_b = html(sa, tanda_a), html(sb, tanda_b)
    bagian.halaman_a = _rentang_halaman(ua, bagian.a0, bagian.a1)
    bagian.halaman_b = _rentang_halaman(ub, bagian.b0, bagian.b1)
    return bagian


# ---------------------------------------------------------------------------
# Perhitungan & penyimpanan
# ---------------------------------------------------------------------------


@dataclass
class Perbandingan:
    persen_a: float
    persen_b: float
    bagian: list[Bagian]

    @property
    def kata_sama(self):
        return sum(b.panjang for b in self.bagian)

    @property
    def kata_diganti(self):
        return sum(b.kata_diganti for b in self.bagian)


def bandingkan(dok_a, dok_b, umum=None, ua=None, ub=None) -> Perbandingan:
    umum = hash_umum() if umum is None else umum
    ua = unit_dokumen(dok_a) if ua is None else ua
    ub = unit_dokumen(dok_b) if ub is None else ub
    ha, hb = hash_per_posisi(ua), hash_per_posisi(ub)
    set_a = {h for h in ha if h is not None} - umum
    set_b = {h for h in hb if h is not None} - umum
    sama = len(set_a & set_b)
    bagian = [_isi_tampilan(b, ua, ub) for b in _sejajarkan(ua, ha, ub, hb, umum)]
    return Perbandingan(
        persen_a=100 * sama / len(set_a) if set_a else 0.0,
        persen_b=100 * sama / len(set_b) if set_b else 0.0,
        bagian=bagian,
    )


def indeks(dok) -> list[Unit]:
    unit = unit_dokumen(dok)
    simpan_sidik(dok, {h for h in hash_per_posisi(unit) if h is not None})
    return unit


def perbarui(dok, umum=None, unit=None, hanya_id_lebih_besar=False):
    """Indeks sidik jari `dok` (bila `unit` belum ada) lalu hitung kemiripannya dengan dokumen lain."""
    from .models import Dokumen, Kemiripan

    if unit is None:
        unit = indeks(dok)
    umum = hash_umum() if umum is None else umum
    set_a = _hash_dokumen(dok.pk) - umum

    if hanya_id_lebih_besar:
        Kemiripan.objects.filter(dokumen_a=dok).delete()
    else:
        Kemiripan.objects.filter(Q(dokumen_a=dok) | Q(dokumen_b=dok)).delete()
    if len(set_a) < 30:
        return 0

    jumlah = 0
    for pk_lain in _kandidat(dok.pk):
        if hanya_id_lebih_besar and pk_lain < dok.pk:
            continue
        set_b = _hash_dokumen(pk_lain) - umum
        sama = len(set_a & set_b)
        pa = 100 * sama / len(set_a)
        pb = 100 * sama / len(set_b) if set_b else 0.0
        if max(pa, pb) < AMBANG_SIMPAN:
            continue
        lain = Dokumen.objects.get(pk=pk_lain)
        hasil = bandingkan(dok, lain, umum, ua=unit)
        a, b, persen_a, persen_b = (dok, lain, pa, pb) if dok.pk < lain.pk else (lain, dok, pb, pa)
        Kemiripan.objects.update_or_create(
            dokumen_a=a,
            dokumen_b=b,
            defaults=dict(
                persen_a=round(persen_a, 1),
                persen_b=round(persen_b, 1),
                kata_sama=hasil.kata_sama,
                kata_diganti=hasil.kata_diganti,
                jumlah_bagian=len(hasil.bagian),
            ),
        )
        jumlah += 1
    return jumlah


def hitung_semua(catat=lambda pesan: None):
    """Indeks ulang semua dokumen lalu hitung semua pasangan (dipakai perintah cek_kemiripan)."""
    from .models import Dokumen, Kemiripan

    dokumen = list(Dokumen.objects.filter(perlu_ocr=False).order_by("pk"))
    unit = {}
    for d in dokumen:
        unit[d.pk] = indeks(d)
    umum = hash_umum()
    catat(f"{len(dokumen)} dokumen diindeks; {len(umum)} rangkaian kata templat diabaikan.")
    Kemiripan.objects.all().delete()
    total = 0
    for d in dokumen:
        total += perbarui(d, umum=umum, unit=unit[d.pk], hanya_id_lebih_besar=True)
    return total
