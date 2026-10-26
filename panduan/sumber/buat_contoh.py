"""Isi situs CONTOH (data fiktif) untuk screenshot panduan. Hanya untuk ARSIP_DATA_DIR sementara."""
import os
import sys
from pathlib import Path

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
sys.path.insert(0, r"C:\Users\bikpr\OneDrive\Documents\PROJECT\arsip-sespimma")
assert "panduan" in os.environ["ARSIP_DATA_DIR"], "hanya untuk data contoh!"
import django  # noqa: E402

django.setup()

import pymupdf  # noqa: E402
from django.contrib.auth.models import Group, User  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402

from arsip import kemiripan, layanan  # noqa: E402
from arsip.models import Angkatan, Dokumen, Kategori  # noqa: E402

PARAGRAF = [
    "Kondisi faktual menunjukkan bahwa {tema} di wilayah hukum {lokus} belum berjalan optimal. Data tiga tahun "
    "terakhir memperlihatkan peningkatan jumlah laporan masyarakat yang belum tertangani secara tuntas, sementara "
    "jumlah personel yang tersedia relatif tetap.",
    "Permasalahan utama meliputi keterbatasan kemampuan personel, koordinasi lintas fungsi yang belum terpadu, "
    "serta pemanfaatan teknologi informasi yang masih rendah. Kondisi tersebut berdampak pada menurunnya "
    "kepercayaan masyarakat terhadap pelayanan kepolisian di {lokus}.",
    "Penulis merekomendasikan penguatan {tema} melalui pelatihan berjenjang, penyusunan standar operasional "
    "prosedur yang jelas, pemanfaatan aplikasi pelaporan elektronik, dan evaluasi kinerja bulanan yang melibatkan "
    "tokoh masyarakat serta pemerintah daerah.",
]

NASKAH = [
    # (kategori, angkatan, nomor, judul, topik, nama, lokus, tema)
    ("NKP", 76, 3, "OPTIMALISASI PATROLI DIALOGIS OLEH SAT SAMAPTA POLRES CONTOH RAYA GUNA MENINGKATKAN RASA AMAN MASYARAKAT",
     "PERAN KEPEMIMPINAN DALAM MEMBANGUN BUDAYA ADAPTIF", "ANDI PRATAMA, S.H.", "Polres Contoh Raya", "patroli dialogis"),
    ("NKP", 76, 3, "OPTIMALISASI PENANGANAN PENGADUAN MASYARAKAT BERBASIS APLIKASI OLEH SATRESKRIM POLRESTA MERDEKA",
     "MANAJEMEN PERUBAHAN DAN ADAPTASI ORGANISASI", "BUDI SANTOSO, S.I.K.", "Polresta Merdeka", "penanganan pengaduan masyarakat"),
    ("NKP", 76, 3, "PENINGKATAN KEMAMPUAN PENYIDIK SIBER POLDA NUSANTARA UTARA GUNA MENANGANI PENIPUAN DARING",
     "MANAJEMEN PERUBAHAN DAN ADAPTASI ORGANISASI", "CITRA LESTARI, S.Kom.", "Polda Nusantara Utara", "penyidikan kejahatan siber"),
    ("POLICY BRIEF", 76, 3, "PENGUATAN DETEKSI DINI KONFLIK LAHAN OLEH BHABINKAMTIBMAS POLSEK SUKAMAJU",
     "PENGARUH KOMPETISI SUMBER DAYA TERHADAP POTENSI KONFLIK SOSIAL", "DEDI KURNIAWAN, S.H.", "Polsek Sukamaju", "deteksi dini konflik lahan"),
    ("POLICY BRIEF", 76, 3, "PENGUATAN PENGAWASAN MELEKAT GUNA MENCEGAH PELANGGARAN DISIPLIN DI POLRES TELUK INDAH",
     "PENGARUH EFEKTIVITAS PENGAWASAN INTERNAL", "EKA PUTRI, S.Psi.", "Polres Teluk Indah", "pengawasan melekat"),
    ("NKP", 75, 2, "OPTIMALISASI PENCEGAHAN PEREDARAN NARKOBA DI KALANGAN PELAJAR OLEH SATRESNARKOBA POLRES BUKIT HIJAU",
     "SINERGI POLRI DAN PEMERINTAH DAERAH", "FAJAR NUGROHO, S.H., M.H.", "Polres Bukit Hijau", "pencegahan peredaran narkoba"),
    ("NKP", 75, 2, "OPTIMALISASI PELAYANAN SKCK BERBASIS DARING OLEH SATINTELKAM POLRES PADANG LUAS",
     "PELAYANAN PUBLIK YANG PRESISI", "GITA RAMADHANI, S.E.", "Polres Padang Luas", "pelayanan SKCK daring"),
]


def sampul(kat, angk, nomor, judul, topik, nama, tahun):
    jenis = "NASKAH KARYA PERSEORANGAN (NKP)" if kat == "NKP" else "POLICY BRIEF"
    return (f"SESPIM LEMDIKLAT POLRI\nSEKOLAH STAF DAN PIMPINAN PERTAMA      {'NKP' if kat == 'NKP' else 'PB'} : {nomor}\n"
            f"{jenis}\nTOPIK\n{topik}\nJUDUL :\n{judul}\nOLEH :\nNAMA : {nama}\nNO. SERDIK : 2026990000{nomor}\n"
            f"POKJAR : II (DUA)\nPESERTA DIDIK SEKOLAH STAF DAN PIMPINAN PERTAMA POLRI\nANGKATAN KE-{angk} T.A. {tahun}")


def pdf(halaman):
    d = pymupdf.open()
    for t in halaman:
        p = d.new_page()
        p.insert_textbox(pymupdf.Rect(60, 60, 540, 780), t, fontsize=11)
    return d.tobytes()


KALIMAT = {
    "patroli dialogis": [
        "Patroli dialogis yang dilaksanakan Sat Samapta baru menjangkau separuh kelurahan karena jadwal piket sering bentrok dengan pengamanan kegiatan masyarakat.",
        "Warga di permukiman padat menyampaikan bahwa kehadiran petugas berseragam pada malam hari membuat mereka lebih tenang dan berani melapor.",
        "Kapolres perlu menetapkan rute patroli berbasis peta kerawanan yang diperbarui setiap pekan bersama ketua rukun warga.",
        "Buku mutasi patroli belum dievaluasi secara rutin sehingga temuan lapangan jarang ditindaklanjuti oleh fungsi lain.",
        "Pelatihan komunikasi persuasif bagi anggota muda menjadi kunci agar dialog dengan warga tidak bersifat formal semata.",
    ],
    "penanganan pengaduan masyarakat": [
        "Aplikasi pengaduan daring sudah tersedia, namun banyak laporan menumpuk karena belum ada petugas khusus yang memverifikasi setiap hari.",
        "Pelapor mengeluhkan tidak adanya pemberitahuan perkembangan perkara setelah laporan diterima oleh penyidik pembantu.",
        "Satreskrim perlu menerapkan batas waktu tanggapan dua kali dua puluh empat jam untuk setiap aduan yang masuk melalui aplikasi.",
        "Dasbor sederhana yang memantau jumlah aduan, waktu tanggapan, dan status penyelesaian akan memudahkan pengawasan pimpinan.",
        "Keterlibatan bagian pengawasan penyidikan diperlukan agar kualitas penanganan tidak hanya diukur dari jumlah perkara selesai.",
    ],
    "penyidikan kejahatan siber": [
        "Penipuan daring melalui tautan palsu dan pesan berantai meningkat tajam, sementara jumlah penyidik bersertifikat forensik digital masih sangat terbatas.",
        "Peralatan ekstraksi data telepon genggam yang dimiliki subdit siber sudah usang dan belum mendukung sistem operasi terbaru.",
        "Kerja sama dengan penyedia layanan keuangan diperlukan untuk mempercepat pemblokiran rekening penampung hasil kejahatan.",
        "Program magang penyidik di laboratorium forensik digital pusat dapat mempercepat alih pengetahuan secara bertahap.",
        "Edukasi masyarakat tentang modus penipuan terbaru sebaiknya dilakukan bersama perguruan tinggi dan komunitas teknologi.",
    ],
    "deteksi dini konflik lahan": [
        "Sengketa batas kebun antara dua desa telah tiga kali memicu pengerahan massa dalam setahun terakhir.",
        "Bhabinkamtibmas sering mengetahui potensi konflik lebih awal tetapi laporan mereka belum masuk ke sistem informasi yang terpusat.",
        "Pemetaan bidang tanah bersama kantor pertanahan dan tokoh adat menjadi langkah awal mencegah klaim yang tumpang tindih.",
        "Forum musyawarah desa yang difasilitasi polsek terbukti meredakan ketegangan sebelum berubah menjadi bentrokan fisik.",
        "Indikator keberhasilan kebijakan adalah turunnya jumlah aksi pengerahan massa dan meningkatnya kesepakatan damai tertulis.",
    ],
    "pengawasan melekat": [
        "Pelanggaran disiplin yang paling sering terjadi adalah ketidakhadiran apel tanpa keterangan dan penyalahgunaan kewenangan saat bertugas di jalan.",
        "Atasan langsung belum memiliki format pencatatan perilaku anggota sehingga pembinaan bergantung pada ingatan pribadi.",
        "Supervisi mendadak oleh kepala bagian sumber daya manusia dapat dilakukan dua kali sebulan pada unit dengan riwayat pelanggaran tinggi.",
        "Pemberian penghargaan bagi anggota teladan sama pentingnya dengan penegakan sanksi agar budaya disiplin tumbuh dari dalam.",
        "Hasil pengawasan perlu dibahas dalam rapat analisa dan evaluasi bulanan bersama seksi profesi dan pengamanan.",
    ],
    "pencegahan peredaran narkoba": [
        "Survei di sejumlah sekolah menengah menunjukkan sebagian pelajar pernah ditawari pil koplo oleh orang yang tidak dikenal di sekitar sekolah.",
        "Satresnarkoba bersama dinas pendidikan menyusun modul penyuluhan yang disampaikan oleh guru bimbingan konseling setiap semester.",
        "Pengawasan terhadap warung dan tempat berkumpul di sekitar sekolah dilakukan dengan melibatkan satpam sekolah dan orang tua murid.",
        "Pelajar yang terindikasi pengguna diarahkan ke layanan rehabilitasi rawat jalan tanpa stigma agar tidak dikeluarkan dari sekolah.",
        "Keberhasilan program diukur dari menurunnya jumlah kasus pelajar dan meningkatnya laporan masyarakat tentang pengedar.",
    ],
    "pelayanan SKCK daring": [
        "Antrean pembuatan surat keterangan catatan kepolisian menumpuk setiap musim penerimaan pegawai dan pendaftaran sekolah kedinasan.",
        "Pemohon dapat mengisi formulir dan mengunggah dokumen melalui laman daring sehingga waktu tunggu di loket berkurang drastis.",
        "Petugas Satintelkam perlu dilatih memverifikasi berkas digital dan menjawab pertanyaan pemohon melalui pesan singkat resmi.",
        "Pembayaran penerimaan negara bukan pajak secara nontunai mengurangi peluang pungutan di luar ketentuan.",
        "Survei kepuasan setelah layanan menjadi dasar perbaikan berkelanjutan dan bahan laporan kepada pimpinan.",
    ],
    "pelayanan SPKT terpadu": [
        "Masyarakat yang datang ke sentra pelayanan sering dipingpong antar ruangan karena pembagian tugas antarfungsi belum jelas.",
        "Satu meja layanan terpadu dengan petugas piket gabungan memungkinkan laporan diterima dan diarahkan dalam satu kali kunjungan.",
        "Ruang tunggu ramah anak dan penyandang disabilitas perlu disediakan sesuai standar pelayanan publik.",
        "Rekaman kamera di ruang pelayanan membantu pimpinan menilai sikap petugas dan menindaklanjuti keluhan secara objektif.",
        "Waktu tanggap rata-rata menjadi indikator utama yang dipajang terbuka di ruang pelayanan setiap bulan.",
    ],
}


def isi(lokus, tema, n=5):
    k = KALIMAT[tema]
    return [f"BAB {i + 1}\n\nUraian di wilayah {lokus}.\n\n" + " ".join(k[(i + j) % len(k)] for j in range(3))
            for i in range(n)]


for kode, nama, urutan in [("NKP", "Naskah Karya Perorangan", 1)]:
    Kategori.objects.filter(kode=kode).update(nama=nama)
for nomor, tahun in [(76, 2026), (75, 2025)]:
    Angkatan.objects.get_or_create(nomor=nomor, defaults={"tahun": tahun})

admin = User.objects.create_superuser("admin", password="contoh12345", first_name="Admin", last_name="Arsip")
reviewer = User.objects.create_user("80010002", password="contoh12345", first_name="Rina", last_name="Wulandari")
reviewer.groups.add(Group.objects.get(name="Reviewer"))
pengunggah = User.objects.create_user("80010003", password="contoh12345", first_name="Hendra", last_name="Saputra")
pengunggah.groups.add(Group.objects.get(name="Pengunggah"))
User.objects.create_user("80010004", password="contoh12345", first_name="Joko", last_name="Prasetyo")

halaman_naskah = {}
for kat, angk, nomor, judul, topik, nama, lokus, tema in NASKAH:
    tahun = Angkatan.objects.get(nomor=angk).tahun
    hal = [sampul(kat, angk, nomor, judul, topik, nama, tahun)] + isi(lokus, tema)
    dok = Dokumen(kategori=Kategori.objects.get(kode=kat), angkatan=Angkatan.objects.get(nomor=angk), lokus=lokus,
                  kata_kunci=f"{tema}, kepercayaan masyarakat, {lokus}")
    dok = layanan.simpan_dokumen_baru(dok, SimpleUploadedFile(f"{kat}-{nama.split(',')[0]}.pdf", pdf(hal)), admin, True)
    halaman_naskah[judul] = (hal, lokus)
    print("naskah", dok.pk, dok.judul[:60])

# Naskah "ganti lokus" dari naskah senior angkatan 75 (menunggu review) -> contoh kemiripan
hal, lokus = halaman_naskah[NASKAH[5][3]]
tiruan = [t.replace("Bukit Hijau", "Lembah Damai").replace("BUKIT HIJAU", "LEMBAH DAMAI")
          .replace("FAJAR NUGROHO, S.H., M.H.", "HENDRA SAPUTRA, S.H.").replace("KE-75 T.A. 2025", "KE-76 T.A. 2026")
          .replace("NKP : 2", "NKP : 3") for t in hal]
dok = Dokumen(kategori=Kategori.objects.get(kode="NKP"), angkatan=Angkatan.objects.get(nomor=76), lokus="Polres Lembah Damai")
dok = layanan.simpan_dokumen_baru(dok, SimpleUploadedFile("NKP03-HENDRA.pdf", pdf(tiruan)), pengunggah, False)
print("tiruan (menunggu review)", dok.pk, dok.judul[:60])

# Satu unggahan lain menunggu review yang orisinal
hal2 = [sampul("NKP", 76, 3, "OPTIMALISASI PELAYANAN SPKT TERPADU DI POLRES SUNGAI BIRU GUNA MEWUJUDKAN PELAYANAN PRIMA",
               "PELAYANAN PUBLIK YANG PRESISI", "HENDRA SAPUTRA, S.H.", 2026)] + isi("Polres Sungai Biru", "pelayanan SPKT terpadu")
dok2 = layanan.simpan_dokumen_baru(Dokumen(kategori=Kategori.objects.get(kode="NKP"), angkatan=Angkatan.objects.get(nomor=76)),
                                   SimpleUploadedFile("NKP03-SPKT.pdf", pdf(hal2)), pengunggah, False)
print("unggahan menunggu", dok2.pk)
print("pasangan mirip:", kemiripan.hitung_semua())
