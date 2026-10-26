import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DIR = Path(sys.argv[1])
HTML = (DIR / "panduan.html").as_uri()
KAKI = """
<div style="width:100%; font-family:'Segoe UI',Arial,sans-serif; font-size:8px; color:#5d6678;
            padding:0 18mm; display:flex; justify-content:space-between; align-items:center;">
  <span><b style="color:#13284b">ARSIP SESPIMMA</b> &nbsp;·&nbsp; Panduan Penggunaan</span>
  <span>Halaman <span class="pageNumber"></span> dari <span class="totalPages"></span></span>
</div>"""

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page()
    pg.goto(HTML)
    pg.wait_for_load_state("networkidle")
    # Sampul saja
    pg.add_style_tag(content="body > section:not(.sampul) { display:none !important; } .sampul { break-after: auto !important; }")
    pg.pdf(path=str(DIR / "_sampul.pdf"), format="A4", print_background=True, margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
    # Isi tanpa sampul, dengan kaki halaman
    pg.goto(HTML)
    pg.wait_for_load_state("networkidle")
    pg.add_style_tag(content=".sampul { display:none !important; } @page :first { margin: 20mm 18mm 20mm 18mm; }")
    pg.pdf(path=str(DIR / "_isi.pdf"), format="A4", print_background=True, display_header_footer=True,
           header_template="<div></div>", footer_template=KAKI,
           margin={"top": "18mm", "bottom": "18mm", "left": "18mm", "right": "18mm"})
    b.close()
print("ok")
