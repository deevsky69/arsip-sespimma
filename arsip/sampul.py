"""
Membaca metadata dari halaman sampul naskah Sespim (NKP, Policy Brief, NASKAP).

Sampul naskah Sespim umumnya berpola:

    SESPIM LEMDIKLAT POLRI                     NKP : 3
    NASKAH KARYA PERSEORANGAN (NKP)   /  POLICY BRIEF
    TOPIK 1 : <teks topik>
    JUDUL : <judul beberapa baris>
    OLEH :
    NAMA       : ...
    NO. SERDIK : ...
    POKJAR     : II (DUA)
    ... ANGKATAN KE-76 T.A. 2026

dan halaman berikutnya berisi surat pernyataan (Nama, Pangkat / NRP) atau abstrak.
Semua hasil bersifat tebakan terbaik; kolom yang tidak ditemukan dibiarkan kosong.
"""

import re
from dataclasses import asdict, dataclass

KATA_SAMBUNG = {
    "dan", "di", "ke", "dari", "guna", "dalam", "rangka", "yang", "pada", "oleh", "untuk", "terhadap",
    "melalui", "sebagai", "atas", "bagi", "dengan", "serta", "atau", "antara", "secara", "demi", "agar",
}
AKRONIM = {
    "AI", "SDM", "BNN", "TNI", "IT", "ITE", "KUHP", "KUHAP", "SOP", "CCTV", "ETLE", "SPKT", "PPKT", "UU", "RI",
    "DKI", "NTB", "NTT", "DIY", "IKN", "ASN", "APBN", "APBD", "BBM", "OPD", "UMKM", "KDRT", "TPPO", "PPA",
    "TPPU", "TIK", "KKN", "RS", "PHH", "BKO", "VUCA", "OSINT", "PETI", "STPL", "SIPP", "LP", "BAP", "SKCK", "SIM", "STNK", "BPKB", "PNS", "PHL", "OTT", "KPK", "PPATK", "OJK",
    "BPN", "PLN", "SMA", "SMP", "SD", "TKP", "IoT", "KTP", "NIK", "SP2HP", "WBK", "WBBM", "ZI", "PNBP",
}
SATUAN_WILAYAH = r"POLDA METRO|POLRES METRO|POLRESTABES|POLRESTA|POLRES|POLSEKTA|POLSEK|POLDA"
SATUAN_PUSAT = (
    r"BARESKRIM|BAHARKAM|KORLANTAS|KORBRIMOB|KORPS BRIMOB|DIVPROPAM|DIVHUMAS|DIVHUBINTER|DIVTIK|DIVKUM|"
    r"LEMDIKLAT|SSDM|STAMAOPS|SOPS|SRENA|ITWASUM|DENSUS 88|BAINTELKAM|PUSDOKKES|POLAIRUD|KORPOLAIRUD"
)
KATA_HENTI_LOKUS = {
    "GUNA", "DALAM", "DI", "KE", "DARI", "UNTUK", "SEBAGAI", "BERBASIS", "MELALUI", "PADA", "DAN", "YANG",
    "OLEH", "TERHADAP", "SERTA", "ATAU", "TAHUN", "DENGAN", "AGAR", "BAGI", "ATAS", "TELAH", "BELUM", "MASIH",
    "MENJADI", "MEMILIKI", "SELAMA", "SEJAK", "HINGGA", "SAAT", "NAMUN", "KARENA", "ADALAH", "YAITU", "INI",
    "ITU", "TERSEBUT", "BARU", "DIBENTUK", "MENANGANI", "MENCATAT", "SEHINGGA", "PERLU", "SECARA", "JAJARAN",
    "MAUPUN", "BAIK", "SEBANYAK", "MENUNJUKKAN", "MERUPAKAN", "SUDAH", "AKAN", "DAPAT",
    "MENCEGAH", "MENINGKATKAN", "MENGHADAPI", "MENJAGA", "MEWUJUDKAN", "MENDUKUNG", "MEMPERKUAT",
    "MENANGANI", "MENGOPTIMALKAN", "MENEKAN", "MEMBANGUN",
    # nama satuan berikutnya, mis. "POLRES YAHUKIMO POLDA PAPUA" -> berhenti di POLDA
    "POLDA", "POLRES", "POLRESTA", "POLRESTABES", "POLSEK", "POLSEKTA", "POLRI",
}


@dataclass
class InfoSampul:
    kategori: str = ""
    nomor_tugas: int | None = None
    nomor_topik: int | None = None
    topik: str = ""
    judul: str = ""
    nama: str = ""
    nomor_serdik: str = ""
    nrp: str = ""
    pokjar: str = ""
    angkatan: int | None = None
    tahun: int | None = None
    lokus: str = ""
    abstrak: str = ""
    kata_kunci: str = ""

    def sebagai_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# Utilitas teks
# ---------------------------------------------------------------------------


def _baris(teks: str) -> list[str]:
    return [re.sub(r"\s+", " ", b).strip(" `'") for b in teks.splitlines() if b.strip(" `'\t")]


def _gabung(baris: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(baris)).strip(" :")


def romawi(nilai: str) -> str:
    """'2' -> 'II' agar "Pokjar 2" dan "Pokjar II" tercatat sama."""
    if not nilai.isdigit() or not 0 < int(nilai) < 40:
        return nilai.upper()
    n, hasil = int(nilai), ""
    for angka, huruf in ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= angka:
            hasil, n = hasil + huruf, n - angka
    return hasil


def huruf_judul(teks: str) -> str:
    """'OPTIMALISASI PERAN POLRES GARUT GUNA ...' -> 'Optimalisasi Peran Polres Garut guna ...'"""
    if not teks or sum(c.islower() for c in teks) > sum(c.isupper() for c in teks) * 0.3:
        return teks  # sudah huruf campuran, biarkan apa adanya

    def kapital(b):
        # Huruf pertama yang berupa huruf (bukan tanda kurung/kutip) dijadikan kapital.
        b = b.lower()
        m = re.search(r"[^\W\d_]", b)
        return b[: m.start()] + b[m.start()].upper() + b[m.start() + 1 :] if m else b

    def kata(k, pertama):
        inti = k.strip("()\"',.;:“”‘’")
        if not inti:
            return k
        if inti.upper() in {a.upper() for a in AKRONIM} or re.fullmatch(r"[IVX]+", inti) or re.search(r"\d", inti):
            return k
        if not pertama and inti.lower() in KATA_SAMBUNG:
            return k.lower()
        return "-".join(kapital(b) for b in k.split("-"))

    return " ".join(kata(k, i == 0) for i, k in enumerate(teks.split()))


# ---------------------------------------------------------------------------
# Pembacaan
# ---------------------------------------------------------------------------

_JUDUL = re.compile(r"^JUDUL(?:\s+KEBIJAKAN)?\s*:?\s*(.*)$", re.I)
_OLEH = re.compile(r"^(DISUSUN\s+)?OLEH\s*:?\s*$|^(NAMA|PENULIS)\s*:", re.I)
_TOPIK = re.compile(r"^TOPIK\s*(?:KE)?\s*[:\-–]?\s*(\d+)?\s*[:\-–]?\s*(.*)$", re.I)
_JENIS = re.compile(r"NASKAH KARYA PERSEORANGAN|NASKAH KARYA PERORANGAN|POLICY BRIEF|NASKAH KELOMPOK|NASKAP", re.I)


def _kategori(teks: str) -> str:
    t = teks.upper()
    if "POLICY BRIEF" in t:
        return "POLICY BRIEF"
    if "NASKAP" in t or "NASKAH KELOMPOK" in t:
        return "NASKAP"
    if re.search(r"NASKAH KARYA PER(SE)?ORANGAN|\bNKP\b", t):
        return "NKP"
    return ""


def _nomor_tugas(teks: str) -> int | None:
    # (?!\d) bukan \b: teks sampul kadang menempel, mis. "NKP : 3SEKOLAH STAF".
    m = re.search(r"\b(?:NKP|PB|POLICY BRIEF|NASKAP)[ \t]*[:\-–]?[ \t]*0?(\d{1,2})(?![\d.,])", teks, re.I)
    return int(m.group(1)) if m else None


def _blok_judul_topik(baris: list[str]):
    topik, nomor_topik, judul = [], None, []
    i_topik = next((i for i, b in enumerate(baris) if _TOPIK.match(b)), None)
    i_judul = next((i for i, b in enumerate(baris) if _JUDUL.match(b)), None)
    if i_judul is None:
        return "", None, ""

    if i_topik is not None and i_topik < i_judul:
        m = _TOPIK.match(baris[i_topik])
        nomor_topik = int(m.group(1)) if m.group(1) else None
        topik = ([m.group(2)] if m.group(2) else []) + baris[i_topik + 1 : i_judul]
    else:
        # Tanpa baris "TOPIK": ambil teks antara baris jenis naskah dan JUDUL.
        i_jenis = next((i for i, b in enumerate(baris[:i_judul]) if _JENIS.search(b)), None)
        if i_jenis is not None:
            topik = baris[i_jenis + 1 : i_judul]

    sisa = _JUDUL.match(baris[i_judul]).group(1)
    if sisa:
        judul.append(sisa)
    for b in baris[i_judul + 1 :]:
        if _OLEH.match(b) or re.match(r"^PESERTA DIDIK", b, re.I):
            break
        judul.append(b)
    return _gabung(topik).strip("\"“”'– "), nomor_topik, _gabung(judul)


def _nilai(pola: str, teks: str) -> str:
    m = re.search(pola, teks, re.I | re.M)
    return re.sub(r"\s+", " ", m.group(1)).strip(" :,") if m else ""


def cari_lokus(*teks: str) -> str:
    for t in teks:
        if not t:
            continue
        up = re.sub(r"\s+", " ", t.upper())
        m = re.search(rf"\b({SATUAN_WILAYAH})\s+((?:[A-Z]+\s?){{1,4}})", up)
        if m:
            nama = []
            for k in m.group(2).split():
                if k in KATA_HENTI_LOKUS:
                    break
                nama.append(k)
            if nama:
                return huruf_judul(f"{m.group(1)} {' '.join(nama)}")
        m = re.search(rf"\b({SATUAN_PUSAT})\b(\s+POLRI)?", up)
        if m:
            return huruf_judul(m.group(1)) + " Polri"
    return ""


def _abstrak_dan_kata_kunci(halaman: list[str]) -> tuple[str, str]:
    for teks in halaman[:8]:
        m = re.search(r"^\s*(?:ABSTRA[KC]T?|RINGKASAN EKSEKUTIF)\s*:?\s*(.*)$", teks, re.I | re.M)
        if not m:
            continue
        isi = teks[m.start(1) :]
        if len(re.findall(r"\.{5,}|…", isi[:600])) >= 2:
            continue  # ini daftar isi ("ABSTRAK ........ 2"), bukan abstraknya
        kk = ""
        mk = re.search(r"Kata[\s-]*kunci\s*:?\s*(.+?)(?:\n\s*\n|\n[A-Z ]{6,}\n|$)", isi, re.I | re.S)
        if mk:
            kk = re.sub(r"\s+", " ", mk.group(1)).strip(" .;")[:500]
            isi = isi[: mk.start()]
        # Berhenti di judul bagian berikutnya (baris huruf kapital semua) bila ada.
        potong = re.search(r"\n\s*(?:[A-Z][A-Z .]{5,}|I\.|1\.\s+[A-Z])\s*\n", isi)
        if potong and potong.start() > 200:
            isi = isi[: potong.start()]
        isi = re.sub(r"[ \t]+", " ", isi)
        isi = re.sub(r"\s*\n\s*", " ", isi).strip()
        return isi[:3000], kk.replace(";", ",")
    return "", ""


def baca_sampul(halaman: list[str]) -> InfoSampul:
    """`halaman`: teks per halaman (hasil pdf.ekstrak). Hanya beberapa halaman awal yang dipakai."""
    info = InfoSampul()
    if not halaman:
        return info
    sampul = halaman[0]
    # Surat pernyataan (Nama, Pangkat / NRP) kadang baru muncul di halaman 5.
    awal = "\n".join(halaman[:6])
    baris = _baris(sampul)

    info.kategori = _kategori(sampul)
    info.nomor_tugas = _nomor_tugas(sampul)
    topik, info.nomor_topik, judul = _blok_judul_topik(baris)
    info.topik = huruf_judul(topik)[:500]
    info.judul = huruf_judul(judul)[:500]

    nama_sampul = _nilai(r"^\s*NAMA\s*:\s*(.+)$", sampul)
    nama_pernyataan = _nilai(r"^\s*Nama\s*:\s*(.+)$", "\n".join(halaman[1:6]))
    # Nama di surat pernyataan biasanya lengkap & berhuruf campuran; pakai bila cocok dengan sampul.
    if nama_pernyataan and nama_sampul and nama_pernyataan.split()[0].upper() == nama_sampul.split()[0].upper():
        info.nama = nama_pernyataan
    else:
        info.nama = nama_sampul or nama_pernyataan
    # "Achmad ..., S.H. - No.Serdik : 2026..." -> buang ekor setelah pemisah
    info.nama = re.split(r"\s+[-–|/]\s+|\s*\bNo\.?\s*Serdik", info.nama, flags=re.I)[0].strip(" ,")

    info.nomor_serdik = _nilai(r"(?:NO\.?|NOMOR)\s*SERDIK\s*:?\s*(\d{6,})", awal)
    info.nrp = _nilai(r"NRP\s*:?\s*(?:[A-Z]+\s*/?\s*)?(\d{8})\b", awal)
    pokjar = _nilai(r"POKJAR\W*:\s*([IVX]+|\d+)\b", sampul)
    info.pokjar = f"Pokjar {romawi(pokjar)}" if pokjar else ""

    angkatan = _nilai(r"ANGKATAN\s*KE\s*[-–]?\s*(\d{1,3})\b", awal)
    info.angkatan = int(angkatan) if angkatan else None
    tahun = _nilai(r"(?:T\.?\s?A\.?|TAHUN\s+ANGGARAN)\s*(20\d\d)\b", awal)
    info.tahun = int(tahun) if tahun else None

    info.abstrak, info.kata_kunci = _abstrak_dan_kata_kunci(halaman)
    info.lokus = cari_lokus(judul, info.abstrak, "\n".join(halaman[1:6]))
    return info


# ---------------------------------------------------------------------------
# Petunjuk dari nama file / folder (dipakai saat impor massal)
# ---------------------------------------------------------------------------


def nomor_tugas_dari_nama_file(nama: str) -> int | None:
    """'NKP03-HANAFI.pdf' / 'PB 3 - ...' / 'POLICY BRIEF 3_...' / 'NKP_3_AKP' -> 3"""
    m = re.search(r"(?:^|[^A-Z])(?:NKP|PB|POLICY[ _]?BRIEF|NASKAP)[ _\-–]*0?(\d{1,2})(?!\d)", nama.upper())
    return int(m.group(1)) if m else None


def nama_dari_folder(folder: str) -> str:
    """'07 - INDRA PARERA, S.SOS' -> 'INDRA PARERA, S.SOS' (pola folder pengumpulan per serdik)."""
    m = re.match(r"^\s*\d{1,3}\s*[-–._]\s*(.+?)\s*$", folder)
    return m.group(1) if m else ""
