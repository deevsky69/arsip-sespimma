"""
Mesin impor massal: membaca setiap PDF di sebuah folder, menebak metadatanya dari
halaman sampul + nama folder/file, lalu menyimpannya ke arsip.

Dipakai oleh perintah `manage.py impor_pdf` dan oleh fitur "Impor dari Google Drive" di situs.
"""

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from django.core.files import File

from . import layanan, ocr, pdf
from .models import Angkatan, Dokumen, Kategori, hitung_sha256
from .sampul import baca_sampul, nama_dari_folder, nomor_tugas_dari_nama_file

KOLOM = [
    "nama_file",
    "judul",
    "kategori",
    "nomor_tugas",
    "angkatan",
    "tahun",
    "topik",
    "penulis",
    "nrp_penulis",
    "nomor_serdik",
    "kelompok",
    "pembimbing",
    "lokus",
    "kata_kunci",
    "abstrak",
]
ALIAS_KATEGORI = {"PB": "POLICY BRIEF", "POLICYBRIEF": "POLICY BRIEF"}


class GagalImpor(Exception):
    pass


@dataclass
class OpsiImpor:
    kategori: str = ""  # kode kategori bila tidak terbaca
    angkatan: int | None = None  # nomor angkatan bila tidak terbaca
    tahun: int | None = None  # tahun angkatan bila tidak terbaca / angkatan baru
    terbitkan: bool = False
    pengunggah: object = None
    kering: bool = False  # uji coba, tidak menyimpan apa pun
    metadata: dict = field(default_factory=dict)  # nama_file (huruf kecil) -> baris CSV


@dataclass
class HasilFile:
    nama_file: str
    status: str  # berhasil | duplikat | gagal | dilewati | uji
    pesan: str = ""
    dokumen_id: int | None = None
    kategori: str = ""
    nomor_tugas: int | None = None
    angkatan: int | None = None
    judul: str = ""
    penulis: str = ""
    lokus: str = ""
    jumlah_halaman: int = 0
    perlu_ocr: bool = False

    def sebagai_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------


def daftar_pdf(folder: Path) -> list[Path]:
    return sorted(p for p in Path(folder).rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")


def peta_kategori() -> dict:
    return {k.kode.upper(): k for k in Kategori.objects.all()}


def _normal_kategori(kode: str) -> str:
    kode = (kode or "").strip().upper()
    return ALIAS_KATEGORI.get(kode.replace(" ", ""), kode)


def _judul_dari_nama_file(path: Path) -> str:
    teks = re.sub(r"[_]+", " ", path.stem)
    teks = re.sub(r"\s*-\s*", " - ", teks)
    return re.sub(r"\s+", " ", teks).strip()


def _judul_metadata(meta: str) -> str:
    # Judul metadata PDF sering berupa "Microsoft Word - file.docx", "NKP 3", atau kosong.
    if meta and len(meta) > 25 and not re.match(r"(?i)(microsoft|untitled|document|\w+\.docx?$)", meta):
        return meta
    return ""


def kategori_dari_folder(rel: Path, kategori_map: dict) -> str:
    for bagian in rel.parts[:-1]:
        kode = _normal_kategori(re.sub(r"[\s_\-]*\d+$", "", bagian.strip()))  # "NKP-3" -> "NKP"
        if kode in kategori_map:
            return kode
    return ""


def tebak_metadata(path: Path, rel: Path, opsi: OpsiImpor, kategori_map: dict):
    """Kembalikan (dict metadata sesuai KOLOM, hasil ekstraksi PDF)."""
    hasil = pdf.ekstrak(path)
    ocr.lengkapi_sampul(path, hasil)  # PDF hasil scan: OCR sampul dulu agar kategori/angkatan terbaca
    info = baca_sampul(hasil.halaman)
    folder_penulis = nama_dari_folder(rel.parent.name) if rel.parent != Path(".") else ""
    data = {
        "nama_file": rel.as_posix(),
        "judul": info.judul or _judul_metadata(hasil.judul_metadata) or _judul_dari_nama_file(path),
        "kategori": kategori_dari_folder(rel, kategori_map) or info.kategori or _normal_kategori(opsi.kategori),
        "nomor_tugas": info.nomor_tugas or nomor_tugas_dari_nama_file(path.name) or "",
        "angkatan": info.angkatan or opsi.angkatan or "",
        "tahun": info.tahun or opsi.tahun or "",
        "topik": info.topik,
        "penulis": info.nama or folder_penulis,
        "nrp_penulis": info.nrp,
        "nomor_serdik": info.nomor_serdik,
        "kelompok": info.pokjar,
        "pembimbing": "",
        "lokus": info.lokus,
        "kata_kunci": info.kata_kunci,
        "abstrak": info.abstrak,
    }
    return {k: ("" if v is None else str(v)) for k, v in data.items()}, hasil


def _sha_file(path):
    with open(path, "rb") as f:
        return hitung_sha256(File(f))


def impor_folder(folder, opsi: OpsiImpor, catat=lambda pesan: None):
    """
    Generator: memproses setiap PDF di `folder` dan menghasilkan HasilFile satu per satu,
    sehingga pemanggil bisa menampilkan kemajuan. `catat(pesan)` menerima pesan sampingan
    (mis. "Angkatan 76 (2026) dibuat.").
    """
    folder = Path(folder)
    kategori_map = peta_kategori()
    angkatan_cache = {}

    def ambil_angkatan(nomor, tahun):
        if nomor not in angkatan_cache:
            a = Angkatan.objects.filter(nomor=nomor).first()
            if a is None:
                if not tahun:
                    raise GagalImpor(f"Angkatan {nomor} belum ada; isi tahunnya agar dibuat otomatis.")
                a = Angkatan(nomor=nomor, tahun=tahun)
                if not opsi.kering:
                    a.save()
                    catat(f"Angkatan {nomor} ({tahun}) dibuat.")
            angkatan_cache[nomor] = a
        return angkatan_cache[nomor]

    for p in daftar_pdf(folder):
        rel = p.relative_to(folder)
        m = opsi.metadata.get(rel.as_posix().lower(), {})
        if opsi.metadata and not m:
            yield HasilFile(rel.as_posix(), "dilewati", "tidak ada di CSV")
            continue
        h = HasilFile(rel.as_posix(), "gagal")
        try:
            tebakan, ekstraksi = tebak_metadata(p, rel, opsi, kategori_map)
            # Kolom CSV yang diisi menimpa hasil pembacaan otomatis.
            d = {k: (m.get(k) or tebakan.get(k, "")).strip() for k in KOLOM}
            h.judul, h.lokus, h.jumlah_halaman = d["judul"], d["lokus"], ekstraksi.jumlah_halaman
            h.penulis = d["penulis"].split("|")[0].strip()

            kategori = kategori_map.get(_normal_kategori(d["kategori"]))
            if not kategori:
                raise GagalImpor(
                    f"kategori '{d['kategori'] or '?'}' tidak dikenali (pilihan: {', '.join(kategori_map)})"
                )
            h.kategori = kategori.kode
            if not d["angkatan"].isdigit():
                raise GagalImpor("nomor angkatan tidak terbaca dari sampul; isi angkatan default")
            tahun = int(d["tahun"]) if d["tahun"].isdigit() else opsi.tahun
            angkatan = ambil_angkatan(int(d["angkatan"]), tahun)
            h.angkatan = angkatan.nomor
            h.nomor_tugas = int(d["nomor_tugas"]) if d["nomor_tugas"].isdigit() else None

            dok = Dokumen(
                judul=d["judul"][:500],
                kategori=kategori,
                angkatan=angkatan,
                nomor_tugas=h.nomor_tugas,
                topik=d["topik"][:500],
                penulis="\n".join(x.strip() for x in re.split(r"[|\n]", d["penulis"]) if x.strip()),
                nrp_penulis=d["nrp_penulis"][:200],
                nomor_serdik=d["nomor_serdik"][:100],
                kelompok=d["kelompok"][:100],
                pembimbing=d["pembimbing"][:300],
                lokus=d["lokus"][:300],
                kata_kunci=d["kata_kunci"][:500],
                abstrak=d["abstrak"],
            )
            if opsi.kering:
                lama = layanan.cari_duplikat_persis(_sha_file(p))
                h.status = "uji"
                h.perlu_ocr = ekstraksi.perlu_ocr
                h.pesan = f"DUPLIKAT dari #{lama.pk}" if lama else ("perlu OCR" if ekstraksi.perlu_ocr else "ok")
                yield h
                continue
            with open(p, "rb") as fh:
                dok = layanan.simpan_dokumen_baru(
                    dok, File(fh, name=p.name), opsi.pengunggah, terbitkan=opsi.terbitkan, hasil=ekstraksi
                )
        except layanan.DokumenDuplikat as e:
            h.status, h.dokumen_id = "duplikat", e.dokumen_lama.pk
            h.pesan = f"file yang sama sudah ada (#{e.dokumen_lama.pk})"
        except (pdf.PDFTidakValid, GagalImpor, ValueError) as e:
            h.status, h.pesan = "gagal", str(e)
        else:
            h.status, h.dokumen_id, h.perlu_ocr = "berhasil", dok.pk, dok.perlu_ocr
            h.judul, h.penulis = dok.judul, (dok.daftar_penulis or [""])[0]
            h.pesan = "PERLU OCR" if dok.perlu_ocr else ""
        yield h


def ringkas(hasil: list[HasilFile]) -> dict:
    jumlah = {"berhasil": 0, "duplikat": 0, "gagal": 0, "dilewati": 0, "perlu_ocr": 0}
    for h in hasil:
        if h.status in jumlah:
            jumlah[h.status] += 1
        if h.status == "berhasil" and h.perlu_ocr:
            jumlah["perlu_ocr"] += 1
    return jumlah
