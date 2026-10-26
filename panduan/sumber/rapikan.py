"""Pangkas ruang kosong di bawah screenshot & buat gambar halaman PDF ber-watermark."""
import io
import sys
from pathlib import Path

import pymupdf
from PIL import Image
from playwright.sync_api import sync_playwright

DIR = Path(sys.argv[1])
G = DIR / "gambar"
LATAR = (244, 245, 248)
LEWATI = {"01-login", "14-terkunci", "20-hp-cari", "06-pdf-watermark"}


def pangkas(f):
    im = Image.open(f).convert("RGB")
    w, h = im.size
    px = im.load()
    y = h - 1
    while y > h * 0.25:
        baris = [px[x, y] for x in range(0, w, 4)]
        if any(abs(r - LATAR[0]) + abs(g - LATAR[1]) + abs(b - LATAR[2]) > 18 for r, g, b in baris):
            break
        y -= 1
    batas = min(h, y + 30)
    if batas < h - 40:
        im.crop((0, 0, w, batas)).save(f)
        return f"{f.stem}: {h} -> {batas}px"
    return f"{f.stem}: tetap"


for f in sorted(G.glob("*.png")):
    if f.stem not in LEWATI:
        print(pangkas(f))

# Halaman PDF ber-watermark yang sesungguhnya (dibuka sebagai pembaca contoh)
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    ctx = b.new_context()
    pg = ctx.new_page()
    pg.goto("http://127.0.0.1:8766/akun/login/")
    pg.fill("#id_username", "80010004")
    pg.fill("#id_password", "contoh12345")
    pg.click("form.formulir button[type=submit]")
    pg.wait_for_load_state("networkidle")
    isi = ctx.request.get("http://127.0.0.1:8766/dokumen/1/pdf/").body()
    b.close()
doc = pymupdf.open(stream=isi, filetype="pdf")
pix = doc[1].get_pixmap(dpi=110)
im = Image.open(io.BytesIO(pix.tobytes("png")))
im.save(G / "06-pdf-watermark.png")
print("watermark:", im.size)
