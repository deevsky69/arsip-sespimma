"""Baca/tulis CSV yang ramah Excel Indonesia (pemisah titik koma, UTF-8 dengan BOM)."""

import csv
import io
from pathlib import Path


def baca_csv(path) -> list[dict]:
    mentah = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            teks = mentah.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    baris_pertama = teks.splitlines()[0] if teks else ""
    pemisah = ";" if baris_pertama.count(";") >= baris_pertama.count(",") else ","
    pembaca = csv.DictReader(io.StringIO(teks, newline=""), delimiter=pemisah)
    hasil = []
    for baris in pembaca:
        bersih = {(k or "").strip().lower(): (v or "").strip() for k, v in baris.items() if k}
        if any(bersih.values()):
            hasil.append(bersih)
    return hasil


def tulis_csv(path, kolom: list[str], baris: list[dict]):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        penulis = csv.DictWriter(f, fieldnames=kolom, delimiter=";", extrasaction="ignore")
        penulis.writeheader()
        penulis.writerows(baris)
