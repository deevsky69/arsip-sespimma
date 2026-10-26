import atexit
import shutil
import tempfile
from io import StringIO
from pathlib import Path

import pymupdf
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from . import layanan, pdf, pencarian
from .csvutil import baca_csv, tulis_csv
from .models import Angkatan, Dokumen, HalamanDokumen, Kategori, LogAkses, TugasImpor
from .sampul import baca_sampul, cari_lokus, huruf_judul, nama_dari_folder, nomor_tugas_dari_nama_file


def buat_pdf(halaman: list[str]) -> bytes:
    doc = pymupdf.open()
    for teks in halaman:
        page = doc.new_page()
        if teks:
            page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), teks, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


TEMP = tempfile.mkdtemp(prefix="arsip-test-")
atexit.register(shutil.rmtree, TEMP, True)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": TEMP}},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
    ARSIP_WATERMARK=True,
    ARSIP_IZINKAN_UNDUH=False,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    DATA_DIR=Path(TEMP),
    ARSIP_OCR_OTOMATIS=False,
)
class DasarTest(TestCase):
    def setUp(self):
        self.nkp = Kategori.objects.get(kode="NKP")
        self.naskap = Kategori.objects.get(kode="NASKAP")
        self.a71 = Angkatan.objects.create(nomor=71, tahun=2025)
        self.a70 = Angkatan.objects.create(nomor=70, tahun=2024)
        self.pembaca = User.objects.create_user("80010001", password="rahasia-123", first_name="Budi")
        self.pengunggah = User.objects.create_user("80010002", password="rahasia-123")
        self.pengunggah.groups.add(Group.objects.get(name="Pengunggah"))
        self.reviewer = User.objects.create_user("80010003", password="rahasia-123")
        self.reviewer.groups.add(Group.objects.get(name="Reviewer"))

    def dokumen(self, judul, halaman, kategori=None, angkatan=None, terbit=True, **meta):
        dok = Dokumen(
            judul=judul,
            kategori=kategori or self.nkp,
            angkatan=angkatan or self.a71,
            penulis=meta.pop("penulis", "Penulis Uji"),
            **meta,
        )
        berkas = SimpleUploadedFile(f"{judul[:20]}.pdf", buat_pdf(halaman), content_type="application/pdf")
        return layanan.simpan_dokumen_baru(dok, berkas, self.pengunggah, terbitkan=terbit)


class PdfTest(DasarTest):
    def test_ekstrak_per_halaman(self):
        h = pdf.ekstrak(
            buat_pdf(
                [
                    "Halaman satu membahas strategi penanganan kecelakaan lalu lintas di wilayah hukum.",
                    "Halaman dua membahas pencegahan peredaran narkoba di lingkungan kampus.",
                ]
            )
        )
        self.assertEqual(h.jumlah_halaman, 2)
        self.assertIn("lalu lintas", h.halaman[0])
        self.assertIn("narkoba", h.halaman[1])
        self.assertFalse(h.perlu_ocr)

    def test_pdf_scan_terdeteksi(self):
        self.assertTrue(pdf.ekstrak(buat_pdf(["", "", ""])).perlu_ocr)

    def test_bukan_pdf_ditolak(self):
        with self.assertRaises(pdf.PDFTidakValid):
            pdf.ekstrak(b"ini bukan pdf")

    def test_watermark(self):
        dok = self.dokumen("Watermark", ["isi naskah"])
        hasil = pdf.beri_watermark(dok.path_berkas, "Budi - 80010001", "Diakses oleh Budi")
        teks = pdf.ekstrak(hasil).halaman[0]
        self.assertIn("80010001", teks)
        self.assertIn("isi naskah", teks)

    def test_watermark_halaman_berotasi(self):
        doc = pymupdf.open()
        p = doc.new_page()
        p.insert_text((72, 72), "teks miring")
        p.set_rotation(90)
        path = Path(TEMP) / "rotasi.pdf"
        doc.save(path)
        teks = pdf.ekstrak(pdf.beri_watermark(path, "Budi - 80010001", "kaki")).halaman[0]
        self.assertIn("80010001", teks)


class QueryTest(TestCase):
    def test_kata_biasa_dan_prefiks(self):
        q = pencarian.susun_query("Konflik sosial")
        self.assertEqual([i.alternatif for i in q.wajib], [(("konflik",),), (("sosial",),)])
        e = q.ekspresi()
        self.assertIn('"konflik"*', e)  # awalan: cocok dengan "konfliknya"
        self.assertIn('akar : ("konflik")', e)  # kata dasar
        self.assertIn(" AND ", e)
        self.assertIn('("di")', pencarian.susun_query("di polres").ekspresi())  # kata pendek tanpa awalan

    def test_frasa_dan_pengecualian(self):
        q = pencarian.susun_query('"restorative justice" polres -narkoba')
        self.assertEqual(len(q.wajib), 2)
        self.assertTrue(q.wajib[0].frasa)
        self.assertIn(("keadilan", "restoratif"), q.wajib[0].alternatif)  # sinonim frasa
        self.assertEqual(q.larangan[0].alternatif, (("narkoba",),))
        self.assertIn(" NOT ", q.ekspresi())

    def test_sinonim_multi_kata(self):
        q = pencarian.susun_query("pungutan liar di polres")
        self.assertEqual(q.wajib[0].alternatif, (("pungli",), ("pungutan", "liar")))
        self.assertEqual(len(q.wajib), 3)

    def test_karakter_berbahaya_aman(self):
        for teks in ['a" OR 1=1 --', "NEAR(x y)", "*", "(((", "AND OR NOT", "polres-garut", "'; DROP TABLE x"]:
            q = pencarian.susun_query(teks)
            if not q.kosong:
                with connection.cursor() as c:
                    c.execute("SELECT count(*) FROM arsip_fts WHERE arsip_fts MATCH %s", [q.ekspresi()])

    def test_kosong(self):
        self.assertTrue(pencarian.susun_query("  -- ").kosong)
        self.assertTrue(pencarian.susun_query("-narkoba").kosong)


class PencarianTest(DasarTest):
    def setUp(self):
        super().setUp()
        self.d1 = self.dokumen(
            "Optimalisasi Penanganan Konflik Sosial",
            ["pendahuluan umum", "bab dua", "strategi pemolisian masyarakat di wilayah Garut"],
            lokus="Polres Garut",
        )
        self.d2 = self.dokumen(
            "Pencegahan Peredaran Narkoba",
            ["peredaran narkoba di kampus", "konfliknya tidak dibahas"],
            kategori=self.naskap,
            angkatan=self.a70,
        )
        self.d3 = self.dokumen("Draft Rahasia Pemolisian", ["pemolisian masyarakat"], terbit=False)

    def ids(self, hasil):
        return [h.dokumen_id for h in hasil]

    def test_isi_halaman_ditemukan_dengan_nomor_halaman(self):
        hasil, mode = pencarian.cari("pemolisian masyarakat")
        self.assertEqual(self.ids(hasil), [self.d1.pk])
        pencarian.isi_cuplikan(hasil, "pemolisian masyarakat")
        self.assertEqual(hasil[0].cuplikan[0].halaman, 3)
        self.assertIn("<mark>", hasil[0].cuplikan[0].html)

    def test_dokumen_belum_terbit_tidak_muncul(self):
        hasil, _ = pencarian.cari("draft rahasia")
        self.assertNotIn(self.d3.pk, self.ids(hasil))

    def test_judul_lebih_relevan_dan_prefiks(self):
        # Dokumen pengisi agar bobot IDF pada BM25 bermakna (korpus 3 dokumen terlalu kecil).
        for i in range(6):
            self.dokumen(f"Naskah Pengisi {i}", [f"pembahasan umum lalu lintas nomor {i}"] * 2)
        hasil, _ = pencarian.cari("konflik")
        self.assertEqual(self.ids(hasil), [self.d1.pk, self.d2.pk])  # d2 cocok lewat "konfliknya"

    def test_kata_berimbuhan_dan_sinonim(self):
        # "menangani" (kata dasar: tangan) cocok dengan "Penanganan" di judul d1
        self.assertEqual(self.ids(pencarian.cari("menangani konflik")[0]), [self.d1.pk])
        # sinonim: "narkotika" menemukan dokumen yang memakai kata "narkoba"
        self.assertEqual(self.ids(pencarian.cari("narkotika")[0]), [self.d2.pk])
        hasil, _ = pencarian.cari("menangani")
        pencarian.isi_cuplikan(hasil, "menangani")
        self.assertIn("<mark>Penanganan</mark>", hasil[0].cuplikan[0].html)

    def test_daftar_pustaka_dipisah(self):
        isi = ["pendahuluan tentang patroli"] * 4 + [
            "BAB V PENUTUP kesimpulan patroli\nDAFTAR PUSTAKA\nSherman, L. Criminal Justice Quarterly 1995",
            "Weisburd, D. Justice Review 2001",
            "LAMPIRAN\nTabel data patroli justice",
        ]
        dok = self.dokumen("Penguatan Patroli Wilayah", isi)
        hasil, mode = pencarian.cari("criminal")
        self.assertEqual((self.ids(hasil), mode), ([dok.pk], "PUSTAKA"))  # hanya ada di pustaka
        cuplikan = pencarian.cari_dalam_dokumen(dok.pk, "justice")
        self.assertEqual([(c.halaman, c.pustaka) for c in cuplikan], [(7, False), (5, True), (6, True)])
        self.assertEqual(pencarian.cari("kesimpulan")[1], "AND")  # teks sebelum judul pustaka tetap isi

    def test_metadata_lokus_bisa_dicari(self):
        hasil, _ = pencarian.cari("polres garut")
        self.assertEqual(self.ids(hasil)[0], self.d1.pk)

    def test_filter(self):
        self.assertEqual(self.ids(pencarian.cari("konflik", kategori="NASKAP")[0]), [self.d2.pk])
        self.assertEqual(self.ids(pencarian.cari("konflik", angkatan=71)[0]), [self.d1.pk])
        self.assertEqual(self.ids(pencarian.cari("konflik", tahun=2024)[0]), [self.d2.pk])

    def test_and_berlaku_per_dokumen(self):
        # "konflik" hanya di judul d1, "garut" hanya di halaman 3 d1 -> tetap cocok sebagai AND
        hasil, mode = pencarian.cari("konflik garut")
        self.assertEqual((self.ids(hasil), mode), ([self.d1.pk], "AND"))
        pencarian.isi_cuplikan(hasil, "konflik garut")
        self.assertEqual({c.halaman for c in hasil[0].cuplikan}, {0, 3})

    def test_fallback_or(self):
        hasil, mode = pencarian.cari("narkoba garut")
        self.assertEqual(mode, "OR")
        self.assertEqual(set(self.ids(hasil)), {self.d1.pk, self.d2.pk})
        hasil, mode = pencarian.cari("narkoba kampus garut")
        self.assertEqual(self.ids(hasil)[0], self.d2.pk)  # memuat 2 dari 3 kata
        hasil, mode = pencarian.cari("narkoba xyzabc")
        self.assertEqual((self.ids(hasil), mode), ([self.d2.pk], "OR"))
        self.assertEqual(pencarian.cari("xyzabc"), ([], "AND"))

    def test_pengecualian_per_dokumen(self):
        hasil, _ = pencarian.cari("konflik -narkoba")
        self.assertEqual(self.ids(hasil), [self.d1.pk])

    def test_cari_dalam_dokumen(self):
        c = pencarian.cari_dalam_dokumen(self.d2.pk, "narkoba")
        self.assertEqual([x.halaman for x in c], [1])

    def test_edit_metadata_memperbarui_indeks(self):
        self.d2.lokus = "Polda Sumatera Utara"
        self.d2.save()
        self.assertEqual(self.ids(pencarian.cari("sumatera")[0]), [self.d2.pk])

    def test_hapus_dokumen_membersihkan_indeks_dan_file(self):
        path, pk = self.d1.path_berkas, self.d1.pk
        self.assertTrue(path.exists())
        self.d1.delete()
        self.assertEqual(pencarian.cari("pemolisian")[0], [])
        self.assertFalse(path.exists())
        with connection.cursor() as c:
            c.execute("SELECT count(*) FROM arsip_fts WHERE rowid BETWEEN %s AND %s",
                      [pk * pencarian.KELIPATAN, (pk + 1) * pencarian.KELIPATAN - 1])
            self.assertEqual(c.fetchone()[0], 0)

    def test_bangun_ulang_indeks(self):
        with connection.cursor() as c:
            c.execute("DELETE FROM arsip_fts")
        self.assertEqual(pencarian.cari("pemolisian")[0], [])
        call_command("bangun_ulang_indeks", stdout=StringIO())
        self.assertEqual(self.ids(pencarian.cari("pemolisian")[0]), [self.d1.pk])

    def test_duplikat_persis_ditolak(self):
        dok = Dokumen(judul="salinan", kategori=self.nkp, angkatan=self.a71, penulis="x")
        with open(self.d1.path_berkas, "rb") as f:
            berkas = SimpleUploadedFile("salinan.pdf", f.read())
        with self.assertRaises(layanan.DokumenDuplikat):
            layanan.simpan_dokumen_baru(dok, berkas)


class ViewTest(DasarTest):
    def setUp(self):
        super().setUp()
        self.d1 = self.dokumen("Strategi Pemolisian Masyarakat", ["isi tentang pemolisian masyarakat"])

    def test_wajib_login(self):
        r = self.client.get(reverse("arsip:beranda"))
        self.assertRedirects(r, reverse("login") + "?next=/")
        r = self.client.get(reverse("arsip:baca", args=[self.d1.pk]))
        self.assertEqual(r.status_code, 302)

    def test_halaman_pembaca(self):
        self.client.force_login(self.pembaca)
        for url in [
            reverse("arsip:beranda"),
            reverse("arsip:cari"),
            reverse("arsip:cari") + "?q=pemolisian&kategori=NKP&angkatan=71&tahun=2025",
            reverse("arsip:cari") + "?q=%22",
            reverse("arsip:cari") + "?angkatan=abc&hal=99",
            reverse("arsip:detail", args=[self.d1.pk]) + "?q=pemolisian",
            reverse("arsip:unggahan_saya"),
            reverse("password_change"),
        ]:
            # CaptureQueriesContext memaksa debug cursor seperti saat DEBUG=True,
            # yang ikut memformat SQL (menangkap salah tulis "%" di query mentah).
            with CaptureQueriesContext(connection):
                self.assertEqual(self.client.get(url).status_code, 200, url)
        r = self.client.get(reverse("arsip:cari") + "?q=pemolisian")
        self.assertContains(r, "Strategi Pemolisian Masyarakat")
        self.assertContains(r, "<mark>")
        self.assertTrue(LogAkses.objects.filter(aksi="cari", keterangan="pemolisian").exists())

    def test_pembaca_tidak_bisa_unggah_atau_review(self):
        self.client.force_login(self.pembaca)
        self.assertEqual(self.client.get(reverse("arsip:unggah")).status_code, 403)
        self.assertEqual(self.client.get(reverse("arsip:review")).status_code, 403)

    def test_baca_pdf_ber_watermark_dan_tercatat(self):
        self.client.force_login(self.pembaca)
        r = self.client.get(reverse("arsip:baca", args=[self.d1.pk]))
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r["Content-Disposition"].startswith("inline"))
        self.assertIn("80010001", pdf.ekstrak(r.content).halaman[0])
        self.assertTrue(LogAkses.objects.filter(aksi="baca", pengguna=self.pembaca, dokumen=self.d1).exists())
        self.assertEqual(self.client.get(reverse("arsip:baca", args=[self.d1.pk]) + "?unduh=1").status_code, 403)

    def _unggah(self, nama="naskah.pdf", isi=None, **lain):
        data = {
            "judul": "Naskah Baru tentang Siber",
            "kategori": self.nkp.pk,
            "angkatan": self.a71.pk,
            "penulis": "Andi\nBudi",
            "lokus": "Polda Jabar",
            "berkas": SimpleUploadedFile(nama, isi or buat_pdf(["kejahatan siber di jawa barat"])),
        }
        data.update(lain)
        return self.client.post(reverse("arsip:unggah"), data)

    def test_alur_unggah_review_terbit(self):
        self.client.force_login(self.pengunggah)
        r = self._unggah()
        dok = Dokumen.objects.get(judul="Naskah Baru tentang Siber")
        self.assertRedirects(r, dok.get_absolute_url())
        self.assertEqual(dok.status, "menunggu")
        self.assertEqual(dok.jumlah_halaman, 1)
        self.assertEqual(HalamanDokumen.objects.filter(dokumen=dok).count(), 1)

        # Pembaca lain belum bisa melihat
        self.client.force_login(self.pembaca)
        self.assertEqual(self.client.get(dok.get_absolute_url()).status_code, 403)
        self.assertEqual(pencarian.cari("siber")[0], [])

        # Reviewer menolak tanpa catatan -> gagal; lalu menyetujui
        self.client.force_login(self.reviewer)
        self.assertContains(self.client.get(reverse("arsip:review")), "Naskah Baru tentang Siber")
        self.client.post(reverse("arsip:review_putus", args=[dok.pk]), {"keputusan": "tolak", "catatan": ""})
        dok.refresh_from_db()
        self.assertEqual(dok.status, "menunggu")
        self.client.post(reverse("arsip:review_putus", args=[dok.pk]), {"keputusan": "setujui"})
        dok.refresh_from_db()
        self.assertEqual(dok.status, "terbit")
        self.assertEqual(dok.direview_oleh, self.reviewer)

        self.client.force_login(self.pembaca)
        self.assertEqual(self.client.get(dok.get_absolute_url()).status_code, 200)
        self.assertEqual([h.dokumen_id for h in pencarian.cari("siber")[0]], [dok.pk])

    def test_reviewer_bisa_langsung_terbitkan(self):
        self.client.force_login(self.reviewer)
        self._unggah(terbitkan="on")
        self.assertEqual(Dokumen.objects.get(judul="Naskah Baru tentang Siber").status, "terbit")

    def test_pengunggah_biasa_tidak_bisa_memaksa_terbit(self):
        self.client.force_login(self.pengunggah)
        self._unggah(terbitkan="on")
        self.assertEqual(Dokumen.objects.get(judul="Naskah Baru tentang Siber").status, "menunggu")

    def test_unggah_ditolak_bukan_pdf_dan_duplikat(self):
        self.client.force_login(self.pengunggah)
        r = self._unggah(nama="x.pdf", isi=b"bukan pdf sama sekali")
        self.assertContains(r, "bukan PDF yang valid")
        r = self._unggah(nama="x.docx")
        self.assertContains(r, "Hanya file PDF")
        with open(self.d1.path_berkas, "rb") as f:
            r = self._unggah(isi=f.read())
        self.assertContains(r, "sudah ada di arsip")
        self.assertEqual(Dokumen.objects.count(), 1)

    def test_admin_dokumen(self):
        admin = User.objects.create_superuser("admin", password="rahasia-123")
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse("admin:arsip_dokumen_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:arsip_dokumen_change", args=[self.d1.pk])).status_code, 200)
        r = self.client.get(reverse("arsip:baca", args=[self.d1.pk]) + "?unduh=1")
        self.assertTrue(r["Content-Disposition"].startswith("attachment"))


class PerintahTest(DasarTest):
    def setUp(self):
        super().setUp()
        self.folder = Path(tempfile.mkdtemp(prefix="impor-", dir=TEMP))
        (self.folder / "NKP").mkdir()
        (self.folder / "NASKAP").mkdir()
        (self.folder / "NKP" / "Strategi_Polres_Garut.pdf").write_bytes(buat_pdf(["isi tentang garut"]))
        (self.folder / "NKP" / "Naskah Kedua.pdf").write_bytes(buat_pdf(["isi tentang bandung"]))
        (self.folder / "NASKAP" / "Kelompok 3.pdf").write_bytes(buat_pdf(["isi kelompok tiga"]))
        (self.folder / "rusak.pdf").write_bytes(b"%PDF-rusak")

    def test_buat_csv_lalu_impor(self):
        csv_path = self.folder / "meta.csv"
        call_command("impor_pdf", str(self.folder), buat_csv=str(csv_path), angkatan=72, stdout=StringIO())
        baris = baca_csv(csv_path)
        self.assertEqual(len(baris), 4)
        per_file = {b["nama_file"]: b for b in baris}
        self.assertEqual(per_file["NKP/Strategi_Polres_Garut.pdf"]["kategori"], "NKP")
        self.assertEqual(per_file["NKP/Strategi_Polres_Garut.pdf"]["judul"], "Strategi Polres Garut")
        self.assertEqual(per_file["NASKAP/Kelompok 3.pdf"]["kategori"], "NASKAP")

        # Simulasi user melengkapi di Excel (penulis Kelompok 3 sengaja tidak diisi)
        per_file["NKP/Strategi_Polres_Garut.pdf"].update(penulis="Andi | Budi", lokus="Polres Garut")
        per_file["NKP/Naskah Kedua.pdf"].update(penulis="Citra")
        tulis_csv(csv_path, list(baris[0].keys()), list(per_file.values()))

        out, err = StringIO(), StringIO()
        call_command(
            "impor_pdf", str(self.folder), csv=str(csv_path), tahun=2026, terbit=True, stdout=out, stderr=err
        )
        self.assertIn("2 berhasil, 0 duplikat, 2 gagal", out.getvalue())
        self.assertIn("rusak.pdf: GAGAL", err.getvalue())
        self.assertIn("Kelompok 3.pdf: GAGAL - Penulis tidak terbaca", err.getvalue())
        self.assertTrue(Angkatan.objects.filter(nomor=72, tahun=2026).exists())
        dok = Dokumen.objects.get(judul="Strategi Polres Garut")
        self.assertEqual(dok.daftar_penulis, ["Andi", "Budi"])
        self.assertEqual(dok.status, "terbit")
        self.assertEqual([h.dokumen_id for h in pencarian.cari("garut")[0]], [dok.pk])

        # Impor ulang: semua terlewati sebagai duplikat
        out = StringIO()
        call_command("impor_pdf", str(self.folder), csv=str(csv_path), stdout=out, stderr=StringIO())
        self.assertIn("0 berhasil, 2 duplikat", out.getvalue())

    def test_impor_tanpa_csv_dan_kering(self):
        out = StringIO()
        call_command("impor_pdf", str(self.folder), angkatan=71, kategori="NKP", kering=True, stdout=out, stderr=StringIO())
        self.assertIn("Uji coba selesai", out.getvalue())
        self.assertEqual(Dokumen.objects.count(), 0)

    def test_impor_pengguna(self):
        src = self.folder / "pengguna.csv"
        src.write_text("nrp;nama;peran\n80020001;Andi Wijaya;\n80020002;Citra Dewi;reviewer\n", encoding="utf-8-sig")
        keluar = self.folder / "akun.csv"
        call_command("impor_pengguna", str(src), keluaran=str(keluar), stdout=StringIO())
        akun = baca_csv(keluar)
        self.assertEqual(len(akun), 2)
        u = User.objects.get(username="80020002")
        self.assertTrue(u.has_perm("arsip.review_dokumen"))
        self.assertEqual(u.first_name, "Citra")
        self.assertTrue(u.check_password(akun[1]["kata_sandi_awal"]))


# Sampul fiktif yang meniru pola sampul naskah Sespim (bukan data serdik sungguhan).
SAMPUL_NKP = """SESPIM LEMDIKLAT POLRI
SEKOLAH STAF DAN PIMPINAN PERTAMA                NKP : 3SEKOLAH
NASKAH KARYA PERSEORANGAN (NKP)
TOPIK – 2
“PENCEGAHAN KORUPSI MELALUI PENGUATAN INTEGRITAS”
JUDUL :
OPTIMALISASI PENGAWASAN ANGGARAN PADA POLRES CONTOH JAYA POLDA SULAWESI
CONTOH GUNA MENCEGAH PRAKTIK KKN (KOLUSI, KORUPSI, DAN NEPOTISME)
OLEH :
NAMA            : ANDI CONTOH, S.H.
NO. SERDIK      : 202699000001
POKJAR          : II (DUA)
PESERTA DIDIK SEKOLAH STAF DAN PIMPINAN PERTAMA POLRI
ANGKATAN KE – 76 T.A. 2026"""

PERNYATAAN = """PERNYATAAN
Nama                 : Andi Contoh, S.H.
Pangkat / NRP        : AKP 80010099
Nomor Serdik         : 202699000001
menyatakan bahwa Naskah Karya Perseorangan (NKP) yang saya tulis adalah asli."""

SAMPUL_PB = """SESPIM LEMDIKLAT POLRI
POLICY BRIEF
TOPIK
PENGARUH KOMPETISI SUMBER DAYA TERHADAP POTENSI KONFLIK SOSIAL
JUDUL
PENGUATAN DETEKSI DINI KONFLIK LAHAN
OLEH :
NAMA : BUDI CONTOH - No.Serdik : 202699000002
PESERTA DIDIK SEKOLAH STAF DAN PIMPINAN PERTAMA POLRI
ANGKATAN KE-76 T.A. 2026"""

DAFTAR_ISI = """DAFTAR ISI
ABSTRAK ................................................ 2
PENDAHULUAN .......................................... 3
REKOMENDASI .......................................... 5"""

ABSTRAK_PB = """ABSTRAK
Policy brief ini membahas deteksi dini konflik lahan di wilayah hukum Polres Contoh Raya
yang meningkat dalam dua tahun terakhir.

Kata kunci: konflik lahan; deteksi dini; Bhabinkamtibmas"""


def ascii(teks):
    # Font bawaan generator PDF uji tidak memuat tanda pisah/kutip melengkung.
    return teks.replace("–", "-").replace("“", "").replace("”", "")


class SampulTest(TestCase):
    def test_sampul_nkp(self):
        info = baca_sampul([SAMPUL_NKP, PERNYATAAN, "isi bab satu"])
        self.assertEqual(info.kategori, "NKP")
        self.assertEqual(info.nomor_tugas, 3)  # "NKP : 3SEKOLAH" (teks menempel)
        self.assertEqual(info.nomor_topik, 2)  # "TOPIK – 2"
        self.assertEqual(info.topik, "Pencegahan Korupsi melalui Penguatan Integritas")
        self.assertEqual(
            info.judul,
            "Optimalisasi Pengawasan Anggaran pada Polres Contoh Jaya Polda Sulawesi Contoh guna "
            "Mencegah Praktik KKN (Kolusi, Korupsi, dan Nepotisme)",
        )
        self.assertEqual(info.nama, "Andi Contoh, S.H.")  # versi huruf campuran dari surat pernyataan
        self.assertEqual((info.nomor_serdik, info.nrp, info.pokjar), ("202699000001", "80010099", "Pokjar II"))
        self.assertEqual((info.angkatan, info.tahun), (76, 2026))
        self.assertEqual(info.lokus, "Polres Contoh Jaya")  # berhenti sebelum satuan berikutnya
        self.assertEqual(info.abstrak, "")

    def test_sampul_pb_abstrak_bukan_daftar_isi(self):
        info = baca_sampul(pdf.ekstrak(buat_pdf([SAMPUL_PB, DAFTAR_ISI, ABSTRAK_PB])).halaman)  # lewat PDF sungguhan
        self.assertEqual(info.kategori, "POLICY BRIEF")
        self.assertIsNone(info.nomor_tugas)
        self.assertEqual(info.judul, "Penguatan Deteksi Dini Konflik Lahan")
        self.assertEqual(info.nama, "BUDI CONTOH")
        self.assertTrue(info.abstrak.startswith("Policy brief ini membahas deteksi dini"), info.abstrak)
        self.assertNotIn("Kata kunci", info.abstrak)
        self.assertEqual(info.kata_kunci, "konflik lahan, deteksi dini, Bhabinkamtibmas")
        self.assertEqual(info.lokus, "Polres Contoh Raya")

    def test_bukan_sampul(self):
        info = baca_sampul(["sekadar teks biasa tanpa pola sampul"])
        self.assertEqual((info.judul, info.nama, info.angkatan), ("", "", None))

    def test_petunjuk_nama_file_dan_folder(self):
        for nama, harap in [
            ("NKP03-HANAFI-POK II.pdf", 3),
            ("NKP 3 - ELIA - POKJAR II.pdf", 3),
            ("NKP_3_AKP_DIDIK.pdf", 3),
            ("PB _03_ ARYA AGUNG _ POKJAR II.pdf", 3),
            ("POLICY BRIEF 3_DANIE.pdf", 3),
            ("Policy_Brief_Sungai_Ntorap_2026.pdf", None),
            ("Draft NKP03_SERDIK.pdf", 3),
        ]:
            self.assertEqual(nomor_tugas_dari_nama_file(nama), harap, nama)
        self.assertEqual(nama_dari_folder("07 - INDRA CONTOH, S.SOS"), "INDRA CONTOH, S.SOS")
        self.assertEqual(nama_dari_folder("NKP"), "")
        self.assertEqual(baca_sampul(["POKJAR : 2"]).pokjar, "Pokjar II")
        self.assertEqual(baca_sampul(["POKJAR : IV (EMPAT)"]).pokjar, "Pokjar IV")

    def test_huruf_judul_dan_lokus(self):
        self.assertEqual(
            huruf_judul("PERAN RS BHAYANGKARA TK. III DALAM RANGKA"), "Peran RS Bhayangkara Tk. III dalam rangka"
        )
        self.assertEqual(huruf_judul("Sudah Huruf Campuran di sini"), "Sudah Huruf Campuran di sini")
        self.assertEqual(cari_lokus("PATROLI DI POLRESTA CONTOH KOTA GUNA"), "Polresta Contoh Kota")
        self.assertEqual(cari_lokus("LABORATORIUM DITTIPIDSIBER BARESKRIM POLRI"), "Bareskrim Polri")
        self.assertEqual(cari_lokus("BHABINKAMTIBMAS POLSEK CONTOH HULU MENCEGAH KONFLIK"), "Polsek Contoh Hulu")


class IsiOtomatisTest(DasarTest):
    def test_unggah_tanpa_judul_dan_penulis_diisi_dari_sampul(self):
        self.client.force_login(self.pengunggah)
        r = self.client.post(
            reverse("arsip:unggah"),
            {
                "kategori": self.nkp.pk,
                "angkatan": self.a71.pk,
                "judul": "",
                "penulis": "",
                "lokus": "Lokus Manual",
                "berkas": SimpleUploadedFile("nkp.pdf", buat_pdf([ascii(SAMPUL_NKP), PERNYATAAN, "isi naskah"])),
            },
        )
        dok = Dokumen.objects.get()
        self.assertRedirects(r, dok.get_absolute_url())
        self.assertTrue(dok.judul.startswith("Optimalisasi Pengawasan Anggaran"))
        self.assertEqual(dok.penulis, "Andi Contoh, S.H.")
        self.assertEqual((dok.nomor_tugas, dok.kelompok, dok.nrp_penulis), (3, "Pokjar II", "80010099"))
        self.assertEqual(dok.lokus, "Lokus Manual")  # isian manual tidak ditimpa
        hasil, _ = pencarian.cari("pencegahan korupsi", hanya_terbit=False)
        self.assertEqual([h.dokumen_id for h in hasil], [dok.pk])  # topik ikut terindeks

    def test_unggah_tanpa_judul_dan_tanpa_sampul_ditolak(self):
        self.client.force_login(self.pengunggah)
        r = self.client.post(
            reverse("arsip:unggah"),
            {
                "kategori": self.nkp.pk,
                "angkatan": self.a71.pk,
                "berkas": SimpleUploadedFile(
                    "polos.pdf", buat_pdf(["teks tanpa sampul yang cukup panjang untuk dibaca sistem"])
                ),
            },
        )
        self.assertContains(r, "tidak terbaca dari sampul")
        self.assertEqual(Dokumen.objects.count(), 0)

    def test_impor_folder_pengumpulan(self):
        folder = Path(tempfile.mkdtemp(prefix="drive-", dir=TEMP))
        (folder / "NKP-3" / "01 - ANDI CONTOH, S.H").mkdir(parents=True)
        (folder / "PB-3" / "02 - CITRA CONTOH").mkdir(parents=True)
        (folder / "NKP-3" / "01 - ANDI CONTOH, S.H" / "NKP03-ANDI-POKJAR II.pdf").write_bytes(
            buat_pdf([ascii(SAMPUL_NKP), PERNYATAAN, "isi naskah nkp"])
        )
        sampul_tanpa_nama = SAMPUL_PB.replace("NAMA : BUDI CONTOH - No.Serdik : 202699000002\n", "")
        (folder / "PB-3" / "02 - CITRA CONTOH" / "PB 3 - CITRA.pdf").write_bytes(
            buat_pdf([sampul_tanpa_nama, ABSTRAK_PB])
        )
        out, err = StringIO(), StringIO()
        call_command("impor_pdf", str(folder), terbit=True, stdout=out, stderr=err)
        self.assertIn("2 berhasil", out.getvalue(), err.getvalue())
        self.assertIn("Angkatan 76 (2026) dibuat", out.getvalue())
        nkp = Dokumen.objects.get(kategori__kode="NKP")
        self.assertEqual((nkp.angkatan.nomor, nkp.nomor_tugas, nkp.penulis), (76, 3, "Andi Contoh, S.H."))
        pb = Dokumen.objects.get(kategori__kode="POLICY BRIEF")
        self.assertEqual(pb.penulis, "CITRA CONTOH")  # dari nama subfolder
        self.assertEqual(pb.nomor_tugas, 3)  # dari nama file
        self.assertEqual(pb.kata_kunci, "konflik lahan, deteksi dini, Bhabinkamtibmas")


class ImporDriveTest(DasarTest):
    """Alur impor dari link Google Drive. Unduhan Drive diganti file lokal agar test tidak butuh internet."""

    LINK = "https://drive.google.com/drive/folders/1tmlnIEnQU_ContohFolderUji123?usp=sharing"

    def setUp(self):
        super().setUp()
        self.reviewer.groups.add(Group.objects.get(name="Reviewer"))
        sampul_pb_tanpa_nama = SAMPUL_PB.replace("NAMA : BUDI CONTOH - No.Serdik : 202699000002\n", "")
        self.isi = {
            "01 - ANDI CONTOH, S.H/NKP03-ANDI-POKJAR II.pdf": buat_pdf([ascii(SAMPUL_NKP), PERNYATAAN, "isi nkp"]),
            "01 - ANDI CONTOH, S.H/NKP03-ANDI-POKJAR II.docx": b"word",
            "02 - CITRA CONTOH/PB 3 - CITRA.pdf": buat_pdf([sampul_pb_tanpa_nama, ABSTRAK_PB]),
            "03 - DEDI CONTOH/NKP03-DEDI.docx": b"hanya word",
            "04 - EKA CONTOH/rusak.pdf": b"%PDF-rusak",
            "lampiran.jpg": b"gambar",
        }

    def _palsukan_drive(self):
        from unittest import mock

        from . import drive

        def daftar(link):
            drive.id_folder(link)
            return [drive.BerkasDrive(id=f"id{i}", path=p) for i, p in enumerate(self.isi)]

        def unduh(berkas, folder):
            tujuan = Path(folder, *berkas.path.split("/"))
            tujuan.parent.mkdir(parents=True, exist_ok=True)
            tujuan.write_bytes(self.isi[berkas.path])
            return tujuan

        return mock.patch.multiple(drive, daftar_berkas=daftar, unduh=unduh)

    def test_id_folder(self):
        from . import drive

        self.assertEqual(drive.id_folder(self.LINK), "1tmlnIEnQU_ContohFolderUji123")
        self.assertEqual(drive.id_folder("https://drive.google.com/drive/u/0/folders/AbC-123_xyzQRS"), "AbC-123_xyzQRS")
        self.assertEqual(drive.id_folder("https://drive.google.com/open?id=AbC-123_xyzQRS"), "AbC-123_xyzQRS")
        for salah in ["https://contoh.com/folders/abc", "https://drive.google.com/file/d/AbC123/view", ""]:
            with self.assertRaises(drive.GagalDrive):
                drive.id_folder(salah)

    def test_hak_akses(self):
        self.client.force_login(self.pengunggah)
        self.assertEqual(self.client.get(reverse("arsip:impor")).status_code, 403)
        self.client.force_login(self.reviewer)
        self.assertEqual(self.client.get(reverse("arsip:impor")).status_code, 200)

    def test_link_tidak_valid(self):
        self.client.force_login(self.reviewer)
        r = self.client.post(reverse("arsip:impor"), {"link": "https://contoh.com/abc", "terbitkan": "on"})
        self.assertContains(r, "Link tidak dikenali")
        self.assertEqual(TugasImpor.objects.count(), 0)

    @override_settings(ARSIP_IMPOR_SINKRON=True)
    def test_impor_dari_link(self):
        self.client.force_login(self.reviewer)
        with self._palsukan_drive():
            r = self.client.post(reverse("arsip:impor"), {"link": self.LINK, "terbitkan": "on"})
        t = TugasImpor.objects.get()
        self.assertRedirects(r, t.get_absolute_url())
        self.assertEqual(t.status, "selesai", t.pesan_galat)
        self.assertEqual((t.jumlah_total, t.jumlah_bukan_pdf), (3, 3))
        self.assertEqual(t.ringkasan(), {"berhasil": 2, "duplikat": 0, "gagal": 1, "dilewati": 1})
        status = {h["nama_file"]: h["status"] for h in t.hasil}
        self.assertEqual(status["03 - DEDI CONTOH/NKP03-DEDI.docx"], "dilewati")  # hanya Word, tanpa PDF
        self.assertNotIn("01 - ANDI CONTOH, S.H/NKP03-ANDI-POKJAR II.docx", status)  # ada PDF-nya
        self.assertEqual(status["04 - EKA CONTOH/rusak.pdf"], "gagal")

        nkp = Dokumen.objects.get(kategori__kode="NKP")
        self.assertEqual((nkp.angkatan.nomor, nkp.nomor_tugas, nkp.status), (76, 3, "terbit"))
        self.assertEqual(nkp.diunggah_oleh, self.reviewer)
        pb = Dokumen.objects.get(kategori__kode="POLICY BRIEF")
        self.assertEqual(pb.penulis, "CITRA CONTOH")
        self.assertFalse((settings.DATA_DIR / "impor-drive" / f"tugas-{t.pk}").exists())  # folder sementara dibersihkan

        r = self.client.get(t.get_absolute_url())
        self.assertContains(r, "berhasil masuk")
        self.assertContains(r, "hanya ada file Word")
        self.assertNotContains(r, 'http-equiv="refresh"')

        # Diulang: semuanya sudah ada -> duplikat, tidak ada dokumen ganda
        with self._palsukan_drive():
            self.client.post(reverse("arsip:impor_ulang", args=[t.pk]))
        t.refresh_from_db()
        self.assertEqual(t.ringkasan()["duplikat"], 2)
        self.assertEqual(Dokumen.objects.count(), 2)

    @override_settings(ARSIP_IMPOR_SINKRON=True)
    def test_folder_tidak_bisa_diakses(self):
        from unittest import mock

        from . import drive

        self.client.force_login(self.reviewer)
        gagal = mock.Mock(side_effect=drive.GagalDrive("Isi folder tidak bisa dibaca. Pastikan akses..."))
        with mock.patch.object(drive, "daftar_berkas", gagal):
            self.client.post(reverse("arsip:impor"), {"link": self.LINK})
        t = TugasImpor.objects.get()
        self.assertEqual(t.status, "gagal")
        self.assertContains(self.client.get(t.get_absolute_url()), "Ulangi impor")

    def test_tidak_boleh_dua_impor_bersamaan(self):
        self.client.force_login(self.reviewer)
        lama = TugasImpor.objects.create(link=self.LINK, status="mengunduh", dibuat_oleh=self.reviewer)
        r = self.client.post(reverse("arsip:impor"), {"link": self.LINK})
        self.assertRedirects(r, lama.get_absolute_url(), fetch_redirect_response=False)
        self.assertEqual(TugasImpor.objects.count(), 1)
        self.assertContains(self.client.get(lama.get_absolute_url()), 'http-equiv="refresh"')

    def test_panel_admin_bertema_situs(self):
        admin = User.objects.create_superuser("admin", password="rahasia-123")
        self.client.force_login(admin)
        r = self.client.get(reverse("admin:index"))
        self.assertContains(r, "admin-arsip")
        self.assertContains(r, 'class="nav-arsip"')
        self.assertContains(r, reverse("arsip:impor"))
        self.assertEqual(self.client.get(reverse("admin:arsip_tugasimpor_changelist")).status_code, 200)


class SaringanDanUbahTest(DasarTest):
    def setUp(self):
        super().setUp()
        self.a = self.dokumen("Patroli Dialogis Polres Garut", ["patroli dialogis rutin"], topik="Kepemimpinan Adaptif",
                              kelompok="Pokjar II", lokus="Polres Garut")
        self.b = self.dokumen("Patroli Siber Polda Papua", ["patroli siber dan patroli dialogis"], topik="Pencegahan Korupsi",
                              kelompok="Pokjar I", lokus="Polda Papua", angkatan=self.a70)
        self.client.force_login(self.pembaca)

    def ids(self, r):
        return [h.dokumen.pk for h in r.context["daftar"]]

    def test_saringan_topik_kelompok_lokus(self):
        url = reverse("arsip:cari")
        self.assertEqual(self.ids(self.client.get(url, {"q": "patroli", "topik": "Pencegahan Korupsi"})), [self.b.pk])
        self.assertEqual(self.ids(self.client.get(url, {"kelompok": "Pokjar II"})), [self.a.pk])
        self.assertEqual(self.ids(self.client.get(url, {"q": "patroli", "lokus": "papua"})), [self.b.pk])
        r = self.client.get(url)
        self.assertContains(r, "Kepemimpinan Adaptif")  # pilihan topik tersedia
        self.assertContains(r, '<option value="Polda Papua">')  # saran lokus

    def test_urutan(self):
        url = reverse("arsip:cari")
        self.assertEqual(self.ids(self.client.get(url, {"urut": "judul"})), [self.a.pk, self.b.pk])
        self.assertEqual(self.ids(self.client.get(url, {"urut": "angkatan"})), [self.a.pk, self.b.pk])  # 71 lalu 70
        self.assertEqual(self.ids(self.client.get(url, {"q": "patroli", "urut": "terbaru"})), [self.b.pk, self.a.pk])
        self.assertEqual(self.client.get(url, {"urut": "ngawur"}).status_code, 200)

    def test_ubah_metadata(self):
        url = reverse("arsip:ubah", args=[self.a.pk])
        self.assertEqual(self.client.get(url).status_code, 403)  # pembaca biasa tidak boleh
        self.client.force_login(self.reviewer)
        self.assertContains(self.client.get(reverse("arsip:detail", args=[self.a.pk])), "Ubah metadata")
        data = {f: getattr(self.a, f) or "" for f in ["judul", "penulis", "topik", "kelompok", "lokus", "kata_kunci", "abstrak"]}
        data.update(kategori=self.nkp.pk, angkatan=self.a71.pk, lokus="Polres Tasikmalaya", nomor_tugas=2)
        r = self.client.post(url, data)
        self.assertRedirects(r, self.a.get_absolute_url())
        self.a.refresh_from_db()
        self.assertEqual((self.a.lokus, self.a.nomor_tugas), ("Polres Tasikmalaya", 2))
        self.assertEqual([h.dokumen_id for h in pencarian.cari("tasikmalaya")[0]], [self.a.pk])  # indeks ikut diperbarui


KOSAKATA = (
    "anggota personel satuan pimpinan strategi kebijakan pelayanan masyarakat pengawasan evaluasi pelatihan "
    "kemampuan koordinasi data laporan kegiatan program sasaran kinerja disiplin integritas pembinaan operasional "
    "wilayah keamanan ketertiban pencegahan penanganan perkara penyidikan teknologi informasi aplikasi digital "
    "sarana prasarana anggaran sumber daya manusia budaya organisasi perubahan adaptasi kepemimpinan komunikasi "
    "partisipasi kemitraan tokoh agama adat pemuda sekolah pasar jalan desa kecamatan patroli dialogis responsif "
    "transparan akuntabel profesional modern terpercaya optimal efektif efisien berkelanjutan terukur terpadu"
).split()


def teks_acak(seed, jumlah_halaman=6, kata_per_halaman=220):
    import random

    r = random.Random(seed)
    return [" ".join(r.choice(KOSAKATA) for _ in range(kata_per_halaman)) for _ in range(jumlah_halaman)]


class KemiripanTest(DasarTest):
    def test_penyamaran_lokus_dan_angka(self):
        from .kemiripan import satuan_teks

        a = satuan_teks(["Personel Polres Garut pada tahun 2024 sebanyak 350 orang di Kabupaten Garut."])
        b = satuan_teks(["Personel Polres Bolaang Mongondow Utara pada tahun 2025 sebanyak 41 orang di Kabupaten Bolmut."])
        self.assertEqual([u.samar for u in a], [u.samar for u in b])
        self.assertEqual([u.samar for u in a][:5], ["personel", "polres", "@", "pada", "tahun"])
        self.assertEqual(b[2].asli, "Bolaang Mongondow Utara")  # nama digabung, teks asli tetap tersimpan
        # nama dari kolom lokus disamarkan di mana pun muncul
        c = satuan_teks(["Masyarakat Garut dan pemuda Garut."], lokus="Polres Garut")
        self.assertEqual([u.samar for u in c], ["masyarakat", "@", "dan", "pemuda", "@"])

    def _naskah(self, judul, halaman, lokus, angkatan=None, **kw):
        return self.dokumen(judul, halaman, lokus=lokus, angkatan=angkatan or self.a71, **kw)

    def test_deteksi_ganti_lokus(self):
        from .models import Kemiripan

        asli_hlm = teks_acak(1)
        asli_hlm[2] = "Kondisi Polres Garut tahun 2023 menunjukkan Kabupaten Garut rawan konflik. " + asli_hlm[2]
        asli = self._naskah("Naskah Senior", asli_hlm, "Polres Garut", angkatan=self.a70)
        lain = self._naskah("Naskah Lain", teks_acak(2), "Polda Papua")

        salin_hlm = [t.replace("Garut", "Sumedang").replace("2023", "2025") for t in asli_hlm[:5]] + teks_acak(3, 1)
        salinan = self._naskah("Naskah Junior", salin_hlm, "Polres Sumedang")

        k = Kemiripan.objects.get(dokumen_a=asli, dokumen_b=salinan)  # dihitung otomatis saat unggah
        self.assertGreater(k.persen_b, 75)  # sebagian besar isi salinan berasal dari naskah senior
        self.assertGreater(k.kata_diganti, 0)
        self.assertEqual(k.tingkat[0], "tinggi")
        self.assertFalse(Kemiripan.objects.filter(dokumen_a=lain).exists())
        self.assertFalse(Kemiripan.objects.filter(dokumen_b=lain).exists())

        # Halaman perbandingan untuk reviewer
        self.client.force_login(self.reviewer)
        r = self.client.get(reverse("arsip:kemiripan_banding", args=[asli.pk, salinan.pk]))
        self.assertContains(r, '<mark class="beda">Sumedang</mark>')
        self.assertContains(r, "Garut → Sumedang")
        r = self.client.get(reverse("arsip:kemiripan"))
        self.assertContains(r, "Naskah Junior")
        self.assertContains(r, "Sangat mirip")
        self.assertContains(self.client.get(salinan.get_absolute_url()), "Kemiripan dengan naskah lain")

        # Pembaca biasa tidak melihat fitur ini
        self.client.force_login(self.pembaca)
        self.assertEqual(self.client.get(reverse("arsip:kemiripan")).status_code, 403)
        self.assertNotContains(self.client.get(asli.get_absolute_url()), "Kemiripan dengan naskah lain")

    def test_teks_templat_diabaikan(self):
        from .models import Kemiripan

        templat = (
            "Pernyataan keaslian yang bertanda tangan di bawah ini menyatakan bahwa naskah karya perseorangan "
            "yang saya tulis adalah asli dan apabila terbukti tidak asli saya bersedia dinyatakan tidak lulus pendidikan."
        )
        for i in range(6):
            self._naskah(f"Naskah {i}", [templat * 3] + teks_acak(100 + i, 3), f"Polres Contoh{i}")
        self.assertEqual(Kemiripan.objects.count(), 0)

    def test_perintah_cek_kemiripan_dan_antrean_review(self):
        from .models import Kemiripan

        hlm = teks_acak(7)
        a = self._naskah("Asli", hlm, "Polres Garut", angkatan=self.a70)
        b = self._naskah("Salinan", hlm[:4], "Polres Garut", terbit=False)
        Kemiripan.objects.all().delete()
        out = StringIO()
        call_command("cek_kemiripan", stdout=out)
        self.assertIn("1 pasangan mirip", out.getvalue())
        self.assertEqual(Kemiripan.objects.get().dokumen_b, b)
        self.client.force_login(self.reviewer)
        r = self.client.get(reverse("arsip:review"))
        self.assertContains(r, "Sangat mirip")
        self.assertContains(r, "Kemiripan tertinggi")
        a.delete()
        self.assertEqual(Kemiripan.objects.count(), 0)


class TanpaPengunggahTest(DasarTest):
    def test_halaman_tetap_tampil_untuk_dokumen_tanpa_pengunggah(self):
        # Dokumen hasil `impor_pdf` tanpa --pengunggah dan tanpa --terbit
        dok = Dokumen(judul="Hasil impor terminal", kategori=self.nkp, angkatan=self.a71, penulis="X")
        dok = layanan.simpan_dokumen_baru(dok, SimpleUploadedFile("t.pdf", buat_pdf(["isi naskah impor"])), None, False)
        self.client.force_login(self.reviewer)
        self.assertContains(self.client.get(reverse("arsip:review")), "Hasil impor terminal")
        self.assertContains(self.client.get(dok.get_absolute_url()), "Diunggah oleh -")
        TugasImpor.objects.create(link="https://drive.google.com/drive/folders/abcdefghijklmn", status="selesai")
        self.assertEqual(self.client.get(reverse("arsip:impor")).status_code, 200)


class CadanganTest(TransactionTestCase):
    """TransactionTestCase: backup SQLite tidak bisa berjalan di dalam transaksi pembungkus TestCase."""

    def test_cadangkan_database_dan_berkas(self):
        data = Path(tempfile.mkdtemp(prefix="data-", dir=TEMP))
        tujuan = data / "tujuan"
        penyimpanan = {
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": data / "berkas"}},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }
        with override_settings(DATA_DIR=data, STORAGES=penyimpanan, ARSIP_OCR_OTOMATIS=False):
            dok = Dokumen(
                judul="Naskah Dicadangkan", penulis="X", kategori=Kategori.objects.get(kode="NKP"),
                angkatan=Angkatan.objects.create(nomor=90, tahun=2030),
            )
            layanan.simpan_dokumen_baru(dok, SimpleUploadedFile("c.pdf", buat_pdf(["isi untuk dicadangkan"])), None, True)
            out1, out2 = StringIO(), StringIO()
            call_command("cadangkan", tujuan=str(tujuan), simpan=2, stdout=out1)
            call_command("cadangkan", tujuan=str(tujuan), simpan=2, stdout=out2)
        self.assertIn("1 PDF baru/berubah dari 1 PDF", out1.getvalue())
        self.assertIn("0 PDF baru/berubah dari 1 PDF", out2.getvalue())  # tidak menyalin ulang
        self.assertEqual(len(list((tujuan / "berkas").rglob("*.pdf"))), 1)
        db = sorted((tujuan / "database").glob("arsip-*.sqlite3"))
        import sqlite3

        with sqlite3.connect(db[-1]) as c:  # salinan database bisa dibuka dan berisi dokumen tadi
            self.assertEqual(c.execute("SELECT judul FROM arsip_dokumen").fetchone()[0], "Naskah Dicadangkan")
        self.assertEqual(len((tujuan / "cadangan.log").read_text(encoding="utf-8").splitlines()), 2)


def buat_pdf_scan(halaman: list[str]) -> bytes:
    """PDF 'hasil scan': setiap halaman hanya berupa gambar, tanpa lapisan teks."""
    asli = pymupdf.open(stream=buat_pdf(halaman), filetype="pdf")
    scan = pymupdf.open()
    for hal in asli:
        pix = hal.get_pixmap(dpi=150, colorspace=pymupdf.csGRAY)
        baru = scan.new_page(width=hal.rect.width, height=hal.rect.height)
        baru.insert_image(baru.rect, pixmap=pix)
    data = scan.tobytes()
    asli.close()
    scan.close()
    return data


ISI_SCAN = (
    "Pelaksanaan patroli dialogis di wilayah hukum Polres Contoh Jaya belum optimal karena jumlah personel "
    "terbatas dan koordinasi dengan tokoh masyarakat masih rendah. Penulis merekomendasikan jadwal patroli "
    "terpadu serta evaluasi bulanan bersama perangkat desa."
)


def _ocr_siap():
    from . import ocr

    return ocr.tersedia()


@override_settings(ARSIP_OCR_OTOMATIS=True, ARSIP_OCR_SINKRON=True)
class OcrTest(DasarTest):
    def setUp(self):
        super().setUp()
        if not _ocr_siap():
            self.skipTest("Model bahasa OCR belum terpasang (manage.py siapkan_ocr)")

    def test_pdf_scan_terdeteksi_tanpa_teks(self):
        self.assertTrue(pdf.ekstrak(buat_pdf_scan([ISI_SCAN])).perlu_ocr)

    def test_unggah_scan_tanpa_judul_dibaca_lewat_ocr(self):
        self.client.force_login(self.pengunggah)
        berkas = SimpleUploadedFile("scan.pdf", buat_pdf_scan([ascii(SAMPUL_NKP), PERNYATAAN, ISI_SCAN, ISI_SCAN]))
        r = self.client.post(
            reverse("arsip:unggah"), {"kategori": self.nkp.pk, "angkatan": self.a71.pk, "berkas": berkas}
        )
        dok = Dokumen.objects.get()
        self.assertRedirects(r, dok.get_absolute_url(), fetch_redirect_response=False)
        self.assertEqual(dok.status_ocr, "selesai", dok.ocr_pesan)
        self.assertFalse(dok.perlu_ocr)
        self.assertIn("Pengawasan Anggaran", dok.judul)  # judul dibaca dari sampul hasil scan
        self.assertIn("Andi", dok.penulis)
        self.assertEqual(dok.jumlah_halaman, 4)
        self.assertEqual([h.dokumen_id for h in pencarian.cari("patroli dialogis", hanya_terbit=False)[0]], [dok.pk])
        self.assertContains(self.client.get(dok.get_absolute_url()), "dibaca dengan <strong>OCR</strong>")

    def test_judul_sementara_bila_sampul_tidak_terbaca(self):
        with override_settings(ARSIP_OCR_SINKRON=False):  # antrean belum dikerjakan
            dok = Dokumen(kategori=self.nkp, angkatan=self.a71)
            dok = layanan.simpan_dokumen_baru(dok, SimpleUploadedFile("Laporan Lama.pdf", buat_pdf_scan(["", "", ""])))
        self.assertEqual(dok.judul, "[Menunggu OCR] Laporan Lama")
        self.assertEqual(Dokumen.objects.get(pk=dok.pk).status_ocr, "antre")
        self.client.force_login(self.reviewer)
        self.assertContains(self.client.get(dok.get_absolute_url()), "Menunggu antrean OCR")

    def test_model_belum_terpasang(self):
        kosong = Path(tempfile.mkdtemp(prefix="tessdata-", dir=TEMP))
        with override_settings(ARSIP_TESSDATA=str(kosong)):
            dok = Dokumen(judul="Scan Tanpa Model", penulis="X", kategori=self.nkp, angkatan=self.a71)
            dok = layanan.simpan_dokumen_baru(dok, SimpleUploadedFile("s.pdf", buat_pdf_scan([ISI_SCAN])), None, True)
            dok.refresh_from_db()
            self.assertEqual(dok.status_ocr, "gagal")
            self.assertIn("siapkan_ocr", dok.ocr_pesan)
            self.client.force_login(self.reviewer)
            self.assertContains(self.client.get(dok.get_absolute_url()), "Ulangi OCR")
        # Setelah model tersedia, tombol "Ulangi OCR" berhasil
        r = self.client.post(reverse("arsip:ocr_jalankan", args=[dok.pk]))
        self.assertRedirects(r, dok.get_absolute_url(), fetch_redirect_response=False)
        dok.refresh_from_db()
        self.assertEqual(dok.status_ocr, "selesai")
        status = self.client.get(reverse("arsip:ocr_status", args=[dok.pk])).json()
        self.assertEqual((status["status"], status["kemajuan"], status["total"]), ("selesai", 1, 1))

    def test_perintah_jalankan_ocr_untuk_dokumen_lama(self):
        with override_settings(ARSIP_OCR_OTOMATIS=False):  # dokumen lama yang belum pernah di-OCR
            dok = self.dokumen("Scan Lama", [""], terbit=True)
            dok.berkas.delete(save=False)
            dok.berkas.save("x.pdf", SimpleUploadedFile("x.pdf", buat_pdf_scan([ISI_SCAN])))
            dok.refresh_from_db()
            self.assertTrue(dok.perlu_ocr)
            self.assertEqual(dok.status_ocr, "")
        out = StringIO()
        call_command("jalankan_ocr", semua=True, stdout=out)
        self.assertIn("1 dokumen diproses", out.getvalue())
        dok.refresh_from_db()
        self.assertEqual(dok.status_ocr, "selesai")
        self.assertEqual([h.dokumen_id for h in pencarian.cari("perangkat desa")[0]], [dok.pk])

    def test_antrean_terputus_diambil_ulang(self):
        from datetime import timedelta

        from django.utils import timezone

        from . import ocr

        with override_settings(ARSIP_OCR_OTOMATIS=False):
            dok = self.dokumen("Macet", [""])
        Dokumen.objects.filter(pk=dok.pk).update(status_ocr="proses", ocr_diperbarui=timezone.now() - timedelta(hours=1))
        self.assertEqual(ocr._ambil_berikutnya().pk, dok.pk)
        self.assertEqual(Dokumen.objects.get(pk=dok.pk).status_ocr, "proses")
        self.assertIsNone(ocr._ambil_berikutnya())  # tidak diambil dua kali


class KunciPekerjaOcrTest(TestCase):
    @override_settings(DATA_DIR=Path(TEMP))
    def test_hanya_satu_pekerja_dan_kunci_basi_diambil_alih(self):
        import os
        import time

        from . import ocr

        ocr._lepas_kunci()
        self.assertTrue(ocr._ambil_kunci())
        self.assertTrue(ocr.pekerja_hidup())
        self.assertFalse(ocr._ambil_kunci())  # pekerja kedua ditolak
        self.assertIsNone(ocr.jalankan_pekerja())
        lama = time.time() - ocr.UMUR_KUNCI_MATI - 60
        os.utime(ocr._berkas_kunci(), (lama, lama))  # pekerja sebelumnya mati tanpa melepas kunci
        self.assertFalse(ocr.pekerja_hidup())
        self.assertEqual(ocr.jalankan_pekerja(), 0)  # kunci basi diambil alih, antrean kosong
        self.assertFalse(ocr._berkas_kunci().exists())  # kunci dilepas setelah selesai


class PeluncuranProsesTest(DasarTest):
    """Di mode normal, impor Drive dan OCR diluncurkan sebagai proses terpisah setelah transaksi tersimpan."""

    def test_impor_drive_diluncurkan_sebagai_proses(self):
        from unittest import mock

        from . import proses

        self.client.force_login(self.reviewer)
        with mock.patch.object(proses, "luncurkan") as luncur, self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("arsip:impor"), {"link": "https://drive.google.com/drive/folders/AbCdEfGhIjKlMnOp"})
        t = TugasImpor.objects.get()
        luncur.assert_called_once_with(["jalankan_impor_drive", str(t.pk)], "impor.log")

    def test_ocr_diluncurkan_sebagai_proses_hanya_sekali(self):
        from unittest import mock

        from . import ocr, proses

        dok = self.dokumen("Scan", ["isi"])
        with override_settings(DATA_DIR=Path(TEMP)), mock.patch.object(proses, "luncurkan") as luncur:
            ocr._lepas_kunci()
            with self.captureOnCommitCallbacks(execute=True):
                ocr.antrekan(dok)
            luncur.assert_called_once_with(["jalankan_ocr"], "ocr.log")
            self.assertTrue(ocr._ambil_kunci())  # seolah pekerja sedang hidup
            with self.captureOnCommitCallbacks(execute=True):
                ocr.antrekan(dok)
            self.assertEqual(luncur.call_count, 1)  # tidak meluncurkan pekerja kedua
            ocr._lepas_kunci()


class BatasLoginTest(DasarTest):
    url = "/akun/login/"

    def _login(self, sandi, **meta):
        return self.client.post(self.url, {"username": "80010001", "password": sandi}, **meta)

    def test_terkunci_setelah_5_kali_gagal(self):
        for _ in range(4):
            self.assertEqual(self._login("salah").status_code, 200)
        r = self._login("salah")  # kegagalan ke-5 -> terkunci
        self.assertEqual(r.status_code, 429)
        self.assertContains(r, "Terlalu banyak percobaan masuk", status_code=429)
        self.assertContains(r, "15 menit", status_code=429)
        # kata sandi benar pun ditolak selama terkunci
        self.assertEqual(self._login("rahasia-123").status_code, 429)
        # pengguna yang sama dari IP lain tidak ikut terkunci
        r = self._login("rahasia-123", REMOTE_ADDR="10.9.8.7")
        self.assertRedirects(r, "/", fetch_redirect_response=False)

    def test_login_berhasil_mereset_hitungan(self):
        for _ in range(4):
            self._login("salah")
        self.assertRedirects(self._login("rahasia-123"), "/", fetch_redirect_response=False)
        self.client.logout()
        for _ in range(4):
            self.assertEqual(self._login("salah").status_code, 200)  # hitungan mulai dari nol lagi

    @override_settings(ARSIP_DI_BELAKANG_PROXY=True)
    def test_ip_dari_proxy_tidak_bisa_dipalsukan(self):
        # Penyerang mengirim X-Forwarded-For palsu; Caddy menambahkan IP aslinya di akhir.
        for i in range(5):
            r = self._login("salah", HTTP_X_FORWARDED_FOR=f"1.2.3.{i}, 203.0.113.9")
        self.assertEqual(r.status_code, 429)  # tetap terkunci walau entri pertama berganti-ganti
        r = self._login("rahasia-123", HTTP_X_FORWARDED_FOR="198.51.100.4")
        self.assertRedirects(r, "/", fetch_redirect_response=False)


class PaketPindahTest(TransactionTestCase):
    def test_ekspor_berisi_database_pdf_dan_info(self):
        import json
        import sqlite3
        import zipfile

        data = Path(tempfile.mkdtemp(prefix="ekspor-", dir=TEMP))
        penyimpanan = {
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": data / "berkas"}},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }
        with override_settings(DATA_DIR=data, STORAGES=penyimpanan, ARSIP_OCR_OTOMATIS=False):
            dok = Dokumen(judul="Naskah Dipindah", penulis="X", kategori=Kategori.objects.get(kode="NKP"),
                          angkatan=Angkatan.objects.create(nomor=91, tahun=2031))
            layanan.simpan_dokumen_baru(dok, SimpleUploadedFile("p.pdf", buat_pdf(["isi naskah dipindah"])), None, True)
            call_command("ekspor_data", ke=str(data / "paket.zip"), stdout=StringIO())
        with zipfile.ZipFile(data / "paket.zip") as z:
            self.assertEqual(json.loads(z.read("paket.json"))["jumlah_dokumen"], 1)
            self.assertEqual(len([n for n in z.namelist() if n.startswith("berkas/")]), 1)
            (data / "db.sqlite3").write_bytes(z.read("arsip.sqlite3"))
        c = sqlite3.connect(data / "db.sqlite3")
        self.assertEqual(c.execute("SELECT judul FROM arsip_dokumen").fetchone()[0], "Naskah Dipindah")
        c.close()

    def test_impor_menolak_file_bukan_paket(self):
        import zipfile

        from django.core.management.base import CommandError

        palsu = Path(tempfile.mkdtemp(prefix="palsu-", dir=TEMP)) / "x.zip"
        with zipfile.ZipFile(palsu, "w") as z:
            z.writestr("lain.txt", "bukan paket")
        with self.assertRaisesMessage(CommandError, "bukan paket"):
            call_command("impor_data", str(palsu), stdout=StringIO())


class BatasUnggahTest(DasarTest):
    @override_settings(ARSIP_MAKS_UKURAN_MB=6)
    def test_batas_ukuran_unggahan_6_mb(self):
        self.client.force_login(self.pengunggah)
        self.assertContains(self.client.get(reverse("arsip:unggah")), "ukuran maksimal 6 MB")
        besar = b"%PDF-1.4\n" + b"0" * (6 * 1024 * 1024 + 10)
        r = self.client.post(
            reverse("arsip:unggah"),
            {"kategori": self.nkp.pk, "angkatan": self.a71.pk, "judul": "Besar", "penulis": "X",
             "berkas": SimpleUploadedFile("besar.pdf", besar)},
        )
        self.assertContains(r, "Ukuran file maksimal 6 MB")
        self.assertEqual(Dokumen.objects.count(), 0)


class WajibGantiSandiTest(DasarTest):
    def setUp(self):
        super().setUp()
        from .models import WajibGantiSandi

        self.pembaca.set_password("qwerty123")
        self.pembaca.save()
        WajibGantiSandi.objects.create(pengguna=self.pembaca)

    def test_diarahkan_ke_ganti_sandi_sampai_diganti(self):
        from .models import WajibGantiSandi

        self.client.post("/akun/login/", {"username": "80010001", "password": "qwerty123"})
        for url in ["/", "/cari/?q=x", "/unggahan-saya/"]:
            self.assertRedirects(self.client.get(url), "/akun/ganti-sandi/", fetch_redirect_response=False)
        r = self.client.get("/akun/ganti-sandi/")
        self.assertContains(r, "masih memakai kata sandi awal")
        # sandi umum ditolak
        r = self.client.post("/akun/ganti-sandi/", {"old_password": "qwerty123", "new_password1": "qwerty123", "new_password2": "qwerty123"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(WajibGantiSandi.objects.filter(pengguna=self.pembaca).exists())
        # sandi kuat diterima -> kewajiban hilang, situs bisa dipakai
        baru = "Bhayangkara-Presisi-2026"
        r = self.client.post("/akun/ganti-sandi/", {"old_password": "qwerty123", "new_password1": baru, "new_password2": baru})
        self.assertRedirects(r, "/", fetch_redirect_response=False)
        self.assertFalse(WajibGantiSandi.objects.filter(pengguna=self.pembaca).exists())
        self.assertEqual(self.client.get("/").status_code, 200)
        self.pembaca.refresh_from_db()
        self.assertTrue(self.pembaca.check_password(baru))

    def test_logout_tetap_bisa(self):
        self.client.force_login(self.pembaca)
        self.assertRedirects(self.client.post("/akun/logout/"), "/akun/login/", fetch_redirect_response=False)

    def test_aksi_admin_wajibkan_ganti_sandi(self):
        from .models import WajibGantiSandi

        admin = User.objects.create_superuser("admin", password="rahasia-123")
        self.client.force_login(admin)
        r = self.client.post(reverse("admin:auth_user_changelist"),
                             {"action": "wajibkan_ganti_sandi", "_selected_action": [self.reviewer.pk]})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(WajibGantiSandi.objects.filter(pengguna=self.reviewer).exists())


class BuatAkunDariNaskahTest(DasarTest):
    def test_buat_akun_dari_nrp_di_naskah(self):
        from .models import WajibGantiSandi

        self.dokumen("NKP A", ["isi a"], penulis="RITA CONTOH LESTARI, S.H", nrp_penulis="78040001")
        self.dokumen("PB A", ["isi b"], penulis="Rita Contoh Lestari, S.H")  # PB tanpa NRP, orang sama
        self.dokumen("NKP B", ["isi c"], penulis="ERIESTU RIZQI CONTOH, S.Sos.", nrp_penulis="93030001")
        self.dokumen("PB B", ["isi d"], penulis="ERIESTU R. CONTOH, S.Sos.")  # variasi nama orang yang sama
        self.dokumen("NKP C", ["isi e"], penulis="HANDOKO CONTOH")  # tidak ada NRP sama sekali

        out = StringIO()
        call_command("buat_akun_dari_naskah", sandi="qwerty123", kering=True, stdout=out)
        self.assertIn("2 akun akan dibuat", out.getvalue())
        self.assertFalse(User.objects.filter(username="78040001").exists())

        out = StringIO()
        call_command("buat_akun_dari_naskah", sandi="qwerty123", stdout=out)
        teks = out.getvalue()
        self.assertIn("2 akun dibuat", teks)
        self.assertIn("1 penulis tanpa NRP", teks)
        self.assertIn("Handoko Contoh", teks)
        self.assertNotIn("Eriestu R. Contoh", teks.split("tanpa NRP")[1])
        u = User.objects.get(username="78040001")
        self.assertEqual(u.first_name, "Rita Contoh Lestari, S.H")
        self.assertTrue(u.check_password("qwerty123"))
        self.assertTrue(WajibGantiSandi.objects.filter(pengguna=u).exists())
        self.assertFalse(u.groups.exists())  # Pembaca

        out = StringIO()
        call_command("buat_akun_dari_naskah", sandi="qwerty123", stdout=out)
        self.assertIn("0 akun dibuat, 2 sudah ada", out.getvalue())
