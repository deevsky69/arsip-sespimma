"""Screenshot situs contoh untuk panduan pengguna."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(sys.argv[1])
OUT.mkdir(exist_ok=True)
D = "http://127.0.0.1:8766"
SANDI = "contoh12345"


def masuk(ctx, user):
    pg = ctx.new_page()
    pg.goto(D + "/akun/login/")
    pg.fill("#id_username", user)
    pg.fill("#id_password", SANDI)
    pg.click("form.formulir button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return pg


def foto(pg, nama, penuh=False, klip=None):
    pg.wait_for_timeout(400)
    pg.screenshot(path=OUT / f"{nama}.png", full_page=penuh, clip=klip)
    print("ok", nama)


with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    baru = lambda lebar=1280, tinggi=820: b.new_context(viewport={"width": lebar, "height": tinggi}, device_scale_factor=1.5)

    # --- Login & terkunci
    ctx = baru()
    pg = ctx.new_page()
    pg.goto(D + "/akun/login/")
    foto(pg, "01-login")
    for _ in range(5):
        pg.goto(D + "/akun/login/")
        pg.fill("#id_username", "80010004")
        pg.fill("#id_password", "salah-sandi")
        pg.click("form.formulir button[type=submit]")
        pg.wait_for_load_state("networkidle")
    foto(pg, "14-terkunci")
    ctx.close()

    # --- Pembaca/Reviewer
    ctx = baru()
    pg = masuk(ctx, "80010002")
    foto(pg, "02-beranda")
    pg.goto(D + "/cari/?q=patroli+dialogis")
    foto(pg, "03-cari")
    pg.goto(D + "/cari/?kategori=POLICY+BRIEF&urut=judul")
    foto(pg, "04-jelajah-saring")
    pg.goto(D + "/dokumen/1/?q=patroli+dialogis")
    pg.wait_for_timeout(2500)
    foto(pg, "05-detail")
    pg.goto(D + "/review/")
    foto(pg, "08-review")
    pg.goto(D + "/dokumen/8/")
    pg.wait_for_timeout(2000)
    foto(pg, "09-detail-review", penuh=True)
    pg.goto(D + "/kemiripan/?min=5")
    foto(pg, "10-kemiripan")
    pg.goto(D + "/kemiripan/6/8/")
    foto(pg, "11-banding")
    pg.mouse.wheel(0, 760)
    foto(pg, "11b-banding-bagian")
    pg.goto(D + "/impor/")
    foto(pg, "12-impor", penuh=True)
    pg.goto(D + "/akun/ganti-sandi/")
    foto(pg, "13-ganti-sandi")
    pg.goto(D + "/dokumen/1/ubah/")
    foto(pg, "15-ubah-metadata")
    # PDF ber-watermark
    pdfpg = ctx.new_page()
    pdfpg.goto(D + "/dokumen/1/pdf/")
    pdfpg.wait_for_timeout(2500)
    foto(pdfpg, "06-pdf-watermark")
    ctx.close()

    # --- Pengunggah
    ctx = baru()
    pg = masuk(ctx, "80010003")
    pg.goto(D + "/unggah/")
    foto(pg, "07-unggah", penuh=True)
    pg.goto(D + "/unggahan-saya/")
    foto(pg, "07b-unggahan-saya")
    ctx.close()

    # --- Admin
    ctx = baru()
    pg = masuk(ctx, "admin")
    pg.goto(D + "/admin/")
    foto(pg, "16-admin")
    pg.goto(D + "/admin/auth/user/add/")
    foto(pg, "17-admin-tambah-pengguna")
    pg.goto(D + "/admin/auth/user/4/change/")
    pg.locator("#id_groups_from, .field-groups").first.scroll_into_view_if_needed()
    foto(pg, "18-admin-peran")
    pg.goto(D + "/admin/axes/accessattempt/")
    foto(pg, "19-admin-buka-kunci")
    ctx.close()

    # --- Tampilan HP
    ctx = b.new_context(viewport={"width": 390, "height": 780}, device_scale_factor=2)
    pg = masuk(ctx, "80010004x") if False else None
    pg = ctx.new_page()
    pg.goto(D + "/akun/login/")
    pg.fill("#id_username", "admin")
    pg.fill("#id_password", SANDI)
    pg.click("form.formulir button[type=submit]")
    pg.wait_for_load_state("networkidle")
    pg.goto(D + "/cari/?q=narkoba")
    foto(pg, "20-hp-cari")
    ctx.close()
    b.close()
