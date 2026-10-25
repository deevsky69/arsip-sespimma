"""
Pencarian teks penuh memakai SQLite FTS5.

Indeks `arsip_fts` berisi satu baris per halaman ditambah satu baris metadata
per dokumen. rowid dikodekan sebagai `dokumen_id * KELIPATAN + halaman`
(halaman 0 = baris metadata), sehingga baris milik satu dokumen bisa dihapus
atau dicari dengan rentang rowid tanpa memindai seluruh indeks.

Kolom indeks:
  judul, meta  - judul dan metadata (hanya di baris metadata)
  isi          - teks halaman
  akar         - teks yang sama dalam bentuk kata dasar ("penanganan" -> "tangan")
  pustaka      - teks daftar pustaka (hanya dicari bila tidak ada hasil di isi)

Bila nanti pindah ke PostgreSQL/Meilisearch, cukup modul ini yang diganti.
"""

import re
from dataclasses import dataclass, field

from django.db import connection, transaction
from django.utils.html import escape
from django.utils.safestring import mark_safe

from .bahasa import POLA_KATA, akar, kelompok_sinonim, panjang_sinonim_terpanjang, pisah_pustaka, teks_akar

KELIPATAN = 100_000  # maksimum halaman per dokumen
BOBOT = "10.0, 4.0, 1.0, 0.7, 0.1"  # judul, meta, isi, akar, pustaka

SQL_BUAT_INDEKS = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS arsip_fts USING fts5("
    "judul, meta, isi, akar, pustaka, tokenize = 'unicode61 remove_diacritics 2')"
)
SQL_HAPUS_INDEKS = "DROP TABLE IF EXISTS arsip_fts"


# ---------------------------------------------------------------------------
# Pengindeksan
# ---------------------------------------------------------------------------


def _teks_meta(dok) -> str:
    # Teks yang enak dibaca di depan, nomor identitas di belakang, agar cuplikan hasil pencarian rapi.
    bagian = [
        dok.penulis,
        dok.lokus,
        dok.kata_kunci,
        dok.abstrak,
        dok.topik,
        dok.kelompok,
        dok.pembimbing,
        dok.kategori.kode if dok.kategori_id else "",
        dok.kategori.nama if dok.kategori_id else "",
        dok.nrp_penulis,
        dok.nomor_serdik,
    ]
    return "\n".join(b for b in bagian if b)


def hapus_dari_indeks(dokumen_id: int):
    with connection.cursor() as c:
        c.execute(
            "DELETE FROM arsip_fts WHERE rowid BETWEEN %s AND %s",
            [dokumen_id * KELIPATAN, dokumen_id * KELIPATAN + KELIPATAN - 1],
        )


def indeks_metadata(dok):
    """Perbarui baris metadata saja (dipanggil setiap kali metadata diubah)."""
    rowid = dok.pk * KELIPATAN
    # Kata dasar hanya dari bagian pendek (bukan abstrak) agar baris metadata tidak terlalu
    # panjang: BM25 menurunkan skor baris yang panjang, sehingga kecocokan di judul jadi lemah.
    pendek = "\n".join([dok.judul, dok.topik, dok.kata_kunci, dok.lokus])
    with connection.cursor() as c:
        c.execute("DELETE FROM arsip_fts WHERE rowid = %s", [rowid])
        c.execute(
            "INSERT INTO arsip_fts(rowid, judul, meta, isi, akar, pustaka) VALUES (%s, %s, %s, '', %s, '')",
            [rowid, dok.judul, _teks_meta(dok), teks_akar(pendek)],
        )


def indeks_dokumen(dok, halaman_teks: list[str]):
    """Indeks ulang seluruh dokumen: metadata + semua halaman."""
    if len(halaman_teks) >= KELIPATAN:
        raise ValueError("Dokumen terlalu banyak halaman untuk diindeks.")
    basis = dok.pk * KELIPATAN
    baris = [
        (basis + i, isi, teks_akar(isi), pustaka)
        for i, (isi, pustaka) in enumerate(pisah_pustaka(halaman_teks), start=1)
        if isi.strip() or pustaka.strip()
    ]
    with transaction.atomic():
        hapus_dari_indeks(dok.pk)
        indeks_metadata(dok)
        with connection.cursor() as c:
            c.executemany(
                "INSERT INTO arsip_fts(rowid, judul, meta, isi, akar, pustaka) VALUES (%s, '', '', %s, %s, %s)", baris
            )


def bangun_ulang_indeks():
    from .models import Dokumen

    with connection.cursor() as c:
        c.execute("DELETE FROM arsip_fts")
    jumlah = 0
    for dok in Dokumen.objects.select_related("kategori").prefetch_related("halaman"):
        indeks_dokumen(dok, [h.teks for h in sorted(dok.halaman.all(), key=lambda h: h.nomor)])
        jumlah += 1
    with connection.cursor() as c:
        c.execute("INSERT INTO arsip_fts(arsip_fts) VALUES ('optimize')")
    return jumlah


def indeks_kosong() -> bool:
    with connection.cursor() as c:
        c.execute("SELECT 1 FROM arsip_fts LIMIT 1")
        return c.fetchone() is None


# ---------------------------------------------------------------------------
# Penyusunan query
# ---------------------------------------------------------------------------

_POLA_TOKEN = re.compile(r'(-?)"([^"]+)"|(-?)(\S+)')


@dataclass
class Istilah:
    """Satu istilah pencarian beserta sinonimnya. `alternatif` = daftar urutan kata."""

    alternatif: tuple
    frasa: bool = False  # ditulis dalam tanda kutip -> tanpa pencocokan awalan

    def _tepat(self, kata):
        isi = " ".join(kata)
        # Awalan membuat "konflik" juga cocok dengan "konfliknya"; tidak untuk frasa/kata sangat pendek.
        return f'"{isi}"*' if not self.frasa and len(kata) == 1 and len(kata[0]) >= 3 else f'"{isi}"'

    def ekspresi(self, dengan_pustaka=False) -> str:
        kolom = "{judul meta isi pustaka}" if dengan_pustaka else "{judul meta isi}"
        tepat = " OR ".join(dict.fromkeys(self._tepat(k) for k in self.alternatif))
        dasar = " OR ".join(dict.fromkeys('"' + " ".join(akar(w) for w in k) + '"' for k in self.alternatif))
        return f"(({kolom} : ({tepat})) OR (akar : ({dasar})))"


@dataclass
class QueryTersusun:
    wajib: list[Istilah] = field(default_factory=list)
    larangan: list[Istilah] = field(default_factory=list)

    @property
    def kosong(self):
        return not self.wajib

    def ekspresi(self, mode="AND", dengan_pustaka=False) -> str:
        if not self.wajib:
            return ""
        inti = f" {mode} ".join(i.ekspresi(dengan_pustaka) for i in self.wajib)
        inti = f"({inti})"
        for x in self.larangan:
            inti = f"{inti} NOT {x.ekspresi(dengan_pustaka)}"
        return inti


def _istilah_dari_kata(kata: list[str]) -> list[Istilah]:
    """Kenali singkatan/sinonim multi-kata ("pungutan liar") secara serakah dari kiri."""
    hasil, i, maks = [], 0, panjang_sinonim_terpanjang()
    while i < len(kata):
        for n in range(min(maks, len(kata) - i), 0, -1):
            potong = tuple(kata[i : i + n])
            kelompok = kelompok_sinonim(potong)
            if n == 1 or len(kelompok) > 1:
                hasil.append(Istilah(alternatif=kelompok, frasa=n > 1))
                i += n
                break
    return hasil


def susun_query(teks: str) -> QueryTersusun:
    """
    Ubah masukan pengguna menjadi ekspresi FTS5 yang aman.

    - kata biasa      : semua kata harus ada (AND); cocok juga dengan bentuk berimbuhan & sinonimnya
    - "frasa persis"  : kata-kata harus berurutan
    - -kata / -"frasa": kecualikan
    """
    q = QueryTersusun()
    biasa: list[str] = []

    def simpan_biasa():
        q.wajib.extend(_istilah_dari_kata(biasa))
        biasa.clear()

    for m in _POLA_TOKEN.finditer(teks or ""):
        if m.group(2) is not None:
            negatif, mentah, frasa = m.group(1), m.group(2), True
        else:
            negatif, mentah, frasa = m.group(3), m.group(4), False
        kata = POLA_KATA.findall(mentah.lower())
        if not kata:
            continue
        if negatif:
            q.larangan.append(Istilah(alternatif=(tuple(kata),), frasa=True) if frasa else Istilah(alternatif=((kata[0],),)))
        elif frasa:
            simpan_biasa()
            q.wajib.append(Istilah(alternatif=kelompok_sinonim(tuple(kata)), frasa=True))
        else:
            biasa.extend(kata)  # "polres-garut" atau "a/b" dipecah menjadi kata-kata terpisah
    simpan_biasa()
    return q


# ---------------------------------------------------------------------------
# Penyorot cuplikan
# ---------------------------------------------------------------------------


class Penyorot:
    """Menentukan kata mana di teks yang cocok dengan query (termasuk bentuk berimbuhan & sinonim)."""

    def __init__(self, q: QueryTersusun):
        self.awalan, self.tepat, self.dasar = set(), set(), set()
        for istilah in q.wajib:
            for kata in istilah.alternatif:
                for w in kata:
                    self.tepat.add(w)
                    self.dasar.add(akar(w))
                    if not istilah.frasa and len(kata) == 1 and len(w) >= 3:
                        self.awalan.add(w)

    def cocok(self, kata: str) -> bool:
        k = kata.lower()
        return k in self.tepat or akar(k) in self.dasar or any(k.startswith(a) for a in self.awalan)

    def cuplikan(self, teks: str, lebar: int = 30) -> str | None:
        token = list(POLA_KATA.finditer(teks or ""))
        tanda = [self.cocok(t.group()) for t in token]
        if not any(tanda):
            return None
        # Jendela `lebar` kata dengan kata cocok terbanyak.
        jumlah = sum(tanda[:lebar])
        terbaik, mulai = jumlah, 0
        for i in range(1, max(1, len(token) - lebar + 1)):
            jumlah += tanda[i + lebar - 1] - tanda[i - 1]
            if jumlah > terbaik:
                terbaik, mulai = jumlah, i
        mulai = max(0, min(mulai, next(i for i, t in enumerate(tanda) if t and i >= mulai) - 3))
        akhir = min(len(token), mulai + lebar)

        bagian = ["… " if mulai > 0 else ""]
        posisi = token[mulai].start()
        for i in range(mulai, akhir):
            t = token[i]
            bagian.append(escape(re.sub(r"\s+", " ", teks[posisi : t.start()])))
            bagian.append(f"<mark>{escape(t.group())}</mark>" if tanda[i] else escape(t.group()))
            posisi = t.end()
        bagian.append(" …" if akhir < len(token) else "")
        return mark_safe("".join(bagian))


# ---------------------------------------------------------------------------
# Pencarian
# ---------------------------------------------------------------------------


@dataclass
class Cuplikan:
    halaman: int  # 0 = judul/metadata
    html: str
    pustaka: bool = False


@dataclass
class Hasil:
    dokumen_id: int
    skor: float
    jumlah_halaman_cocok: int = 0
    cuplikan: list[Cuplikan] = field(default_factory=list)
    dokumen: object = None


@dataclass
class Saringan:
    kategori: str = ""
    angkatan: int | None = None
    tahun: int | None = None
    topik: str = ""
    kelompok: str = ""
    lokus: str = ""
    hanya_terbit: bool = True

    def queryset(self):
        from .models import Dokumen

        qs = Dokumen.objects.all()
        if self.hanya_terbit:
            qs = qs.filter(status=Dokumen.Status.TERBIT)
        if self.kategori:
            qs = qs.filter(kategori__kode=self.kategori)
        if self.angkatan:
            qs = qs.filter(angkatan__nomor=self.angkatan)
        if self.tahun:
            qs = qs.filter(angkatan__tahun=self.tahun)
        if self.topik:
            qs = qs.filter(topik=self.topik)
        if self.kelompok:
            qs = qs.filter(kelompok=self.kelompok)
        if self.lokus:
            qs = qs.filter(lokus__icontains=self.lokus)
        return qs


def _dokumen_yang_memuat(ekspresi: str) -> set[int]:
    with connection.cursor() as c:
        c.execute(f"SELECT DISTINCT rowid / {KELIPATAN} FROM arsip_fts WHERE arsip_fts MATCH %s", [ekspresi])
        return {r[0] for r in c.fetchall()}


def cari(teks: str, saringan: Saringan | None = None, **kwargs):
    """
    Kembalikan (daftar Hasil terurut, mode).

    Mode "AND": dokumen memuat semua kata (boleh tersebar di judul, metadata,
    dan halaman yang berbeda). Bila tidak ada, otomatis mode "OR": dokumen yang
    memuat sebagian kata, yang memuat lebih banyak kata diurutkan lebih atas.
    Mode "PUSTAKA": kata hanya ditemukan di daftar pustaka.
    Cuplikan belum diisi; panggil `isi_cuplikan` untuk halaman hasil yang ditampilkan.
    """
    saringan = saringan or Saringan(**kwargs)
    q = susun_query(teks)
    if q.kosong:
        return [], "AND"

    lolos = set(saringan.queryset().values_list("pk", flat=True))
    terpilih, mode, per_kata = set(), "AND", []
    for dengan_pustaka in (False, True):
        per_kata = [_dokumen_yang_memuat(i.ekspresi(dengan_pustaka)) & lolos for i in q.wajib]
        dilarang = set().union(*(_dokumen_yang_memuat(i.ekspresi(dengan_pustaka)) for i in q.larangan))
        terpilih = set.intersection(*per_kata) - dilarang
        mode = "PUSTAKA" if dengan_pustaka else "AND"
        if not terpilih and len(q.wajib) > 1 and not dengan_pustaka:
            terpilih, mode = set.union(*per_kata) - dilarang, "OR"
        if terpilih:
            break
    if not terpilih:
        return [], "AND"

    # Peringkat: skor bm25 terbaik per dokumen. MATERIALIZED diperlukan karena
    # bm25() tidak boleh langsung dipakai di dalam fungsi agregat. "%%" = operator modulo
    # (ditulis ganda agar tidak dianggap placeholder parameter oleh Django).
    with connection.cursor() as c:
        c.execute(
            f"""
            WITH r AS MATERIALIZED (
                SELECT rowid / {KELIPATAN} AS dok,
                       bm25(arsip_fts, {BOBOT}) AS skor,
                       (rowid %% {KELIPATAN}) > 0 AS halaman_isi
                FROM arsip_fts WHERE arsip_fts MATCH %s
            )
            SELECT dok, min(skor), sum(halaman_isi) FROM r GROUP BY dok
            """,
            [q.ekspresi("OR", dengan_pustaka=mode == "PUSTAKA")],
        )
        baris = c.fetchall()

    hasil = []
    for dok, skor, n_halaman in baris:
        if dok not in terpilih:
            continue
        # bm25 bernilai negatif (makin kecil makin relevan). Dokumen yang cocok di
        # banyak halaman, atau memuat lebih banyak kata yang dicari, dinaikkan.
        n_kata = sum(dok in s for s in per_kata)
        skor = skor * (1 + 0.04 * min(n_halaman, 15)) * n_kata
        hasil.append(Hasil(dokumen_id=dok, skor=skor, jumlah_halaman_cocok=n_halaman))
    hasil.sort(key=lambda h: (h.skor, h.dokumen_id))
    return hasil, mode


def _baris_ke_cuplikan(penyorot, rowid, judul, meta, isi, pustaka):
    hlm = rowid % KELIPATAN
    teks, di_pustaka = (f"{judul}\n{meta}", False) if hlm == 0 else ((isi, False) if penyorot.cuplikan(isi) else (pustaka, True))
    html = penyorot.cuplikan(teks)
    return Cuplikan(halaman=hlm, html=html, pustaka=di_pustaka) if html else None


def isi_cuplikan(daftar: list[Hasil], teks: str, maks: int = 3):
    """Isi cuplikan teks bersorot untuk tiap hasil (cukup untuk yang sedang ditampilkan)."""
    q = susun_query(teks)
    if q.kosong:
        return daftar
    penyorot = Penyorot(q)
    with connection.cursor() as c:
        for h in daftar:
            awal = h.dokumen_id * KELIPATAN
            for dengan_pustaka in (False, True):
                c.execute(
                    f"""
                    SELECT rowid, judul, meta, isi, pustaka FROM arsip_fts
                    WHERE arsip_fts MATCH %s AND rowid BETWEEN %s AND %s
                    ORDER BY bm25(arsip_fts, {BOBOT}) LIMIT {int(maks)}
                    """,
                    [q.ekspresi("OR", dengan_pustaka), awal, awal + KELIPATAN - 1],
                )
                h.cuplikan = [x for x in (_baris_ke_cuplikan(penyorot, *r) for r in c.fetchall()) if x]
                if h.cuplikan:
                    break
    return daftar


def cari_dalam_dokumen(dokumen_id: int, teks: str, batas: int = 60) -> list[Cuplikan]:
    """Halaman-halaman di dalam satu dokumen yang memuat kata yang dicari (isi dulu, lalu pustaka)."""
    q = susun_query(teks)
    if q.kosong:
        return []
    penyorot = Penyorot(q)
    awal = dokumen_id * KELIPATAN + 1
    for mode in ("AND", "OR"):
        with connection.cursor() as c:
            c.execute(
                f"""
                SELECT rowid, judul, meta, isi, pustaka FROM arsip_fts
                WHERE arsip_fts MATCH %s AND rowid BETWEEN %s AND %s
                ORDER BY rowid LIMIT {int(batas)}
                """,
                [q.ekspresi(mode, dengan_pustaka=True), awal, awal + KELIPATAN - 2],
            )
            hasil = [x for x in (_baris_ke_cuplikan(penyorot, *r) for r in c.fetchall()) if x]
        if hasil or len(q.wajib) < 2:
            break
    hasil.sort(key=lambda c: (c.pustaka, c.halaman))
    return hasil
