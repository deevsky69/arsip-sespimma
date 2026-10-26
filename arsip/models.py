import hashlib
import uuid
from pathlib import Path

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Kategori(models.Model):
    """Jenis dokumen (NKP, NASKAP, Policy Brief, ...). Dapat ditambah lewat admin."""

    kode = models.CharField(max_length=20, unique=True, help_text="Singkatan, mis. NKP")
    nama = models.CharField(max_length=120, help_text="Nama lengkap, mis. Naskah Karya Perorangan")
    deskripsi = models.TextField(blank=True)
    urutan = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name_plural = "kategori"
        ordering = ["urutan", "kode"]

    def __str__(self):
        return self.kode


class Angkatan(models.Model):
    nomor = models.PositiveIntegerField(unique=True, help_text="Nomor angkatan, mis. 71")
    tahun = models.PositiveIntegerField(help_text="Tahun pendidikan")
    keterangan = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name_plural = "angkatan"
        ordering = ["-nomor"]

    def __str__(self):
        return f"Angkatan {self.nomor} ({self.tahun})"

    def get_absolute_url(self):
        return reverse("arsip:jelajah") + f"?angkatan={self.nomor}"


def lokasi_berkas(instance, filename):
    # Nama file asli tidak dipakai sebagai path agar aman dari karakter aneh;
    # nama aslinya tetap disimpan di field nama_berkas_asli.
    return f"dokumen/{timezone.now():%Y/%m}/{uuid.uuid4().hex}.pdf"


class Dokumen(models.Model):
    class Status(models.TextChoices):
        MENUNGGU = "menunggu", "Menunggu review"
        TERBIT = "terbit", "Terbit"
        DITOLAK = "ditolak", "Ditolak"

    judul = models.CharField(max_length=500)
    kategori = models.ForeignKey(Kategori, on_delete=models.PROTECT, related_name="dokumen")
    angkatan = models.ForeignKey(Angkatan, on_delete=models.PROTECT, related_name="dokumen")
    nomor_tugas = models.PositiveSmallIntegerField(
        "tugas ke-", null=True, blank=True, help_text="Mis. 3 untuk NKP-3 / Policy Brief 3"
    )
    topik = models.CharField(max_length=500, blank=True, help_text="Topik yang ditetapkan untuk naskah ini")
    penulis = models.TextField(help_text="Satu nama per baris. Untuk naskah kelompok, tulis semua anggota.")
    nrp_penulis = models.CharField("NRP penulis", max_length=200, blank=True, help_text="Opsional, pisahkan dengan koma")
    nomor_serdik = models.CharField("nomor serdik", max_length=100, blank=True)
    kelompok = models.CharField(max_length=100, blank=True, help_text="Pokjar / kelompok, mis. Pokjar II")
    pembimbing = models.CharField(max_length=300, blank=True)
    lokus = models.CharField(
        max_length=300, blank=True, help_text="Wilayah/satuan yang dikaji, mis. Polres Garut, Polda Jabar"
    )
    kata_kunci = models.CharField(max_length=500, blank=True, help_text="Pisahkan dengan koma")
    abstrak = models.TextField(blank=True)

    berkas = models.FileField(
        upload_to=lokasi_berkas, validators=[FileExtensionValidator(["pdf"])], help_text="File PDF"
    )
    nama_berkas_asli = models.CharField(max_length=300, blank=True)
    ukuran_berkas = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, db_index=True, blank=True)
    jumlah_halaman = models.PositiveIntegerField(default=0)
    jumlah_kata = models.PositiveIntegerField(default=0)
    perlu_ocr = models.BooleanField(
        default=False, help_text="PDF hasil scan tanpa teks; isinya belum bisa dicari sampai di-OCR"
    )

    class StatusOCR(models.TextChoices):
        TIDAK = "", "Tidak perlu"
        ANTRE = "antre", "Menunggu antrean OCR"
        PROSES = "proses", "OCR sedang berjalan"
        SELESAI = "selesai", "Teks hasil OCR"
        GAGAL = "gagal", "OCR gagal"

    status_ocr = models.CharField(
        "status OCR", max_length=10, choices=StatusOCR.choices, default="", blank=True, db_index=True
    )
    ocr_kemajuan = models.PositiveIntegerField("halaman selesai di-OCR", default=0)
    ocr_pesan = models.CharField("catatan OCR", max_length=500, blank=True)
    ocr_diperbarui = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.MENUNGGU, db_index=True)
    catatan_review = models.TextField(blank=True)
    direview_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    direview_pada = models.DateTimeField(null=True, blank=True)

    diunggah_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="unggahan"
    )
    dibuat = models.DateTimeField(auto_now_add=True)
    diubah = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "dokumen"
        ordering = ["-angkatan__nomor", "kategori__urutan", "judul"]
        permissions = [
            ("review_dokumen", "Dapat menyetujui/menolak dokumen"),
            ("impor_massal", "Dapat mengimpor massal dari link Google Drive"),
        ]

    def __str__(self):
        return self.judul

    def get_absolute_url(self):
        return reverse("arsip:detail", args=[self.pk])

    @property
    def daftar_penulis(self):
        return [p.strip() for p in self.penulis.splitlines() if p.strip()]

    @property
    def daftar_kata_kunci(self):
        return [k.strip() for k in self.kata_kunci.split(",") if k.strip()]

    @property
    def path_berkas(self) -> Path:
        return Path(self.berkas.path)


class HalamanDokumen(models.Model):
    """Teks hasil ekstraksi per halaman. Dipakai untuk pencarian dan nanti untuk cek kemiripan."""

    dokumen = models.ForeignKey(Dokumen, on_delete=models.CASCADE, related_name="halaman")
    nomor = models.PositiveIntegerField()
    teks = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "halaman dokumen"
        ordering = ["dokumen", "nomor"]
        constraints = [models.UniqueConstraint(fields=["dokumen", "nomor"], name="halaman_unik")]

    def __str__(self):
        return f"{self.dokumen_id} hlm {self.nomor}"


class SidikJari(models.Model):
    """Hash rangkaian 5 kata (lokus/angka disamarkan) milik sebuah dokumen, untuk cek kemiripan."""

    dokumen = models.ForeignKey(Dokumen, on_delete=models.CASCADE, related_name="+")
    hash = models.BigIntegerField(db_index=True)

    class Meta:
        indexes = [models.Index(fields=["dokumen", "hash"])]


class Kemiripan(models.Model):
    """Hasil perbandingan dua dokumen. Disimpan dengan dokumen_a.pk < dokumen_b.pk."""

    dokumen_a = models.ForeignKey(Dokumen, on_delete=models.CASCADE, related_name="+")
    dokumen_b = models.ForeignKey(Dokumen, on_delete=models.CASCADE, related_name="+")
    persen_a = models.FloatField(help_text="Persentase isi dokumen A yang juga terdapat di dokumen B")
    persen_b = models.FloatField(help_text="Persentase isi dokumen B yang juga terdapat di dokumen A")
    kata_sama = models.PositiveIntegerField(default=0)
    kata_diganti = models.PositiveIntegerField(default=0, help_text="Kata yang berbeda hanya karena lokus/angka")
    jumlah_bagian = models.PositiveIntegerField(default=0)
    dihitung = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "kemiripan"
        constraints = [models.UniqueConstraint(fields=["dokumen_a", "dokumen_b"], name="pasangan_unik")]

    @property
    def tertinggi(self):
        return max(self.persen_a, self.persen_b)

    @property
    def tingkat(self):
        return tingkat_kemiripan(self.tertinggi)

    def dari_sisi(self, dok):
        """(dokumen lain, % isi `dok` yang ada di dokumen lain, % isi dokumen lain yang ada di `dok`)."""
        if dok.pk == self.dokumen_a_id:
            return self.dokumen_b, self.persen_a, self.persen_b
        return self.dokumen_a, self.persen_b, self.persen_a


def tingkat_kemiripan(persen: float) -> tuple[str, str]:
    """(kode, label) untuk tampilan."""
    if persen >= 40:
        return "tinggi", "Sangat mirip"
    if persen >= 20:
        return "sedang", "Perlu diperiksa"
    if persen >= 8:
        return "rendah", "Mirip sebagian"
    return "wajar", "Wajar"


class TugasImpor(models.Model):
    """Satu pekerjaan impor dari link folder Google Drive (berjalan di latar belakang)."""

    class Status(models.TextChoices):
        ANTRE = "antre", "Menunggu"
        MENGUNDUH = "mengunduh", "Mengunduh dari Drive"
        MEMPROSES = "memproses", "Membaca & menyimpan"
        SELESAI = "selesai", "Selesai"
        GAGAL = "gagal", "Gagal"

    link = models.URLField(max_length=500)
    kategori_default = models.ForeignKey(
        Kategori, null=True, blank=True, on_delete=models.SET_NULL, help_text="Dipakai bila tidak terbaca di sampul"
    )
    angkatan_default = models.PositiveIntegerField(null=True, blank=True)
    tahun_default = models.PositiveIntegerField(null=True, blank=True)
    terbitkan = models.BooleanField(default=False)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ANTRE)
    jumlah_total = models.PositiveIntegerField(default=0)
    jumlah_selesai = models.PositiveIntegerField(default=0)
    jumlah_bukan_pdf = models.PositiveIntegerField(default=0)
    hasil = models.JSONField(default=list, blank=True)  # daftar HasilFile.sebagai_dict()
    log = models.TextField(blank=True)
    pesan_galat = models.TextField(blank=True)

    dibuat_oleh = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    dibuat = models.DateTimeField(auto_now_add=True)
    diperbarui = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "tugas impor Drive"
        verbose_name_plural = "tugas impor Drive"
        ordering = ["-dibuat"]

    def __str__(self):
        return f"Impor #{self.pk} ({self.get_status_display()})"

    def get_absolute_url(self):
        return reverse("arsip:impor_detail", args=[self.pk])

    @property
    def berjalan(self):
        return self.status in (self.Status.ANTRE, self.Status.MENGUNDUH, self.Status.MEMPROSES)

    @property
    def terputus(self):
        """Berjalan tapi tidak ada kemajuan > 15 menit (mis. server sempat dimatikan)."""
        return self.berjalan and (timezone.now() - self.diperbarui).total_seconds() > 15 * 60

    @property
    def persen(self):
        if self.status == self.Status.SELESAI:
            return 100
        return int(100 * self.jumlah_selesai / self.jumlah_total) if self.jumlah_total else 0

    def ringkasan(self):
        j = {"berhasil": 0, "duplikat": 0, "gagal": 0, "dilewati": 0}
        for h in self.hasil:
            if h.get("status") in j:
                j[h["status"]] += 1
        return j


class WajibGantiSandi(models.Model):
    """Pengguna yang wajib mengganti kata sandi sebelum bisa memakai situs (mis. masih memakai sandi awal)."""

    pengguna = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wajib_ganti_sandi")
    dibuat = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "wajib ganti kata sandi"
        verbose_name_plural = "wajib ganti kata sandi"

    def __str__(self):
        return str(self.pengguna)


class LogAkses(models.Model):
    class Aksi(models.TextChoices):
        LIHAT = "lihat", "Melihat detail"
        BACA = "baca", "Membuka PDF"
        UNDUH = "unduh", "Mengunduh PDF"
        CARI = "cari", "Mencari"

    pengguna = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    dokumen = models.ForeignKey(Dokumen, null=True, blank=True, on_delete=models.SET_NULL)
    aksi = models.CharField(max_length=10, choices=Aksi.choices)
    keterangan = models.CharField(max_length=500, blank=True)
    alamat_ip = models.GenericIPAddressField(null=True, blank=True)
    waktu = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name_plural = "log akses"
        ordering = ["-waktu"]

    def __str__(self):
        return f"{self.waktu:%Y-%m-%d %H:%M} {self.pengguna} {self.aksi}"


def hitung_sha256(fileobj) -> str:
    h = hashlib.sha256()
    for chunk in fileobj.chunks() if hasattr(fileobj, "chunks") else iter(lambda: fileobj.read(1 << 20), b""):
        h.update(chunk)
    if hasattr(fileobj, "seek"):
        fileobj.seek(0)
    return h.hexdigest()
