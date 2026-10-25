"""
Mengunduh isi folder Google Drive yang dibagikan "Siapa saja yang memiliki link".

Hanya ID folder yang diambil dari link yang ditempel pengguna, lalu permintaan selalu
dikirim ke drive.google.com, jadi link tidak bisa dipakai untuk mengakses alamat lain.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path

POLA_ID_FOLDER = re.compile(r"drive\.google\.com/(?:drive/(?:u/\d+/)?folders/|open\?id=|folderview\?id=)([-\w]{10,})")


class GagalDrive(Exception):
    pass


@dataclass
class BerkasDrive:
    id: str
    path: str  # path relatif di dalam folder, mis. "01 - NAMA/NKP03.pdf"

    @property
    def pdf(self):
        return self.path.lower().endswith(".pdf")


def id_folder(link: str) -> str:
    m = POLA_ID_FOLDER.search((link or "").strip())
    if not m:
        raise GagalDrive(
            "Link tidak dikenali. Gunakan link folder Google Drive, "
            "mis. https://drive.google.com/drive/folders/1AbC..."
        )
    return m.group(1)


def daftar_berkas(link: str) -> list[BerkasDrive]:
    import gdown

    fid = id_folder(link)
    try:
        isi = gdown.download_folder(
            url=f"https://drive.google.com/drive/folders/{fid}", skip_download=True, quiet=True
        )
    except Exception as e:  # gdown melempar beberapa jenis error berbeda
        raise GagalDrive(
            "Isi folder tidak bisa dibaca. Pastikan akses folder diatur ke "
            "'Siapa saja yang memiliki link' (Anyone with the link). "
            f"Detail: {str(e)[:200]}"
        ) from e
    if not isi:
        raise GagalDrive("Folder kosong atau tidak bisa diakses.")
    return [BerkasDrive(id=f.id, path=f.path.replace("\\", "/")) for f in isi]


def unduh(berkas: BerkasDrive, folder_tujuan: Path) -> Path:
    import gdown

    bagian = [b for b in berkas.path.split("/") if b not in ("", ".", "..")]
    tujuan = Path(folder_tujuan, *bagian)
    tujuan.parent.mkdir(parents=True, exist_ok=True)
    try:
        hasil = gdown.download(id=berkas.id, output=str(tujuan), quiet=True)
    except Exception as e:
        raise GagalDrive(f"Gagal mengunduh {berkas.path}: {str(e)[:200]}") from e
    if not hasil or not os.path.exists(tujuan):
        raise GagalDrive(f"Gagal mengunduh {berkas.path}")
    return tujuan
