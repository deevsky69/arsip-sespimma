from django.contrib import admin, messages
from django.utils.html import format_html

from . import layanan, pdf
from .models import Angkatan, Dokumen, HalamanDokumen, Kategori, LogAkses, TugasImpor, WajibGantiSandi, hitung_sha256


@admin.register(Kategori)
class KategoriAdmin(admin.ModelAdmin):
    list_display = ["kode", "nama", "urutan", "jumlah_dokumen"]
    list_editable = ["urutan"]

    @admin.display(description="Jumlah dokumen")
    def jumlah_dokumen(self, obj):
        return obj.dokumen.count()


@admin.register(Angkatan)
class AngkatanAdmin(admin.ModelAdmin):
    list_display = ["nomor", "tahun", "keterangan", "jumlah_dokumen"]
    search_fields = ["nomor", "tahun", "keterangan"]

    @admin.display(description="Jumlah dokumen")
    def jumlah_dokumen(self, obj):
        return obj.dokumen.count()


@admin.register(Dokumen)
class DokumenAdmin(admin.ModelAdmin):
    list_display = ["judul", "kategori", "angkatan", "penulis_singkat", "status", "jumlah_halaman", "perlu_ocr", "dibuat"]
    list_filter = ["status", "kategori", "angkatan", "nomor_tugas", "kelompok", "perlu_ocr", "status_ocr"]
    search_fields = ["judul", "penulis", "nrp_penulis", "nomor_serdik", "topik", "lokus", "kata_kunci", "nama_berkas_asli"]
    readonly_fields = [
        "lihat",
        "nama_berkas_asli",
        "ukuran_berkas",
        "sha256",
        "jumlah_halaman",
        "jumlah_kata",
        "perlu_ocr",
        "status_ocr",
        "ocr_kemajuan",
        "ocr_pesan",
        "diunggah_oleh",
        "direview_oleh",
        "direview_pada",
        "dibuat",
        "diubah",
    ]
    fieldsets = [
        (None, {"fields": ["lihat", "judul", "kategori", "nomor_tugas", "angkatan", "topik", "status", "catatan_review"]}),
        ("Penulis", {"fields": ["penulis", "nrp_penulis", "nomor_serdik", "kelompok", "pembimbing"]}),
        ("Isi", {"fields": ["lokus", "kata_kunci", "abstrak"]}),
        (
            "Berkas",
            {
                "fields": [
                    "berkas",
                    "nama_berkas_asli",
                    "ukuran_berkas",
                    "jumlah_halaman",
                    "jumlah_kata",
                    "perlu_ocr",
                    "status_ocr",
                    "ocr_kemajuan",
                    "ocr_pesan",
                    "sha256",
                ]
            },
        ),
        ("Riwayat", {"fields": ["diunggah_oleh", "dibuat", "direview_oleh", "direview_pada", "diubah"]}),
    ]
    actions = ["terbitkan", "proses_ulang", "antrekan_ocr"]
    list_per_page = 50

    @admin.display(description="Penulis")
    def penulis_singkat(self, obj):
        p = obj.daftar_penulis
        return f"{p[0]} +{len(p) - 1}" if len(p) > 1 else (p[0] if p else "")

    @admin.display(description="Halaman publik")
    def lihat(self, obj):
        if not obj.pk:
            return "-"
        return format_html('<a href="{}" target="_blank">Buka di situs arsip</a>', obj.get_absolute_url())

    def has_add_permission(self, request):
        # Dokumen baru ditambahkan lewat halaman Unggah atau perintah impor_pdf,
        # supaya ekstraksi teks dan cek duplikat selalu dijalankan.
        return False

    def save_model(self, request, obj, form, change):
        if "berkas" in form.changed_data:
            f = form.cleaned_data["berkas"]
            try:
                pdf.ekstrak(f.read())
            except pdf.PDFTidakValid as e:
                messages.error(request, f"Berkas tidak diganti: {e}")
                obj.berkas = Dokumen.objects.get(pk=obj.pk).berkas
                super().save_model(request, obj, form, change)
                return
            f.seek(0)
            obj.sha256 = hitung_sha256(f)
            obj.ukuran_berkas = f.size
            obj.nama_berkas_asli = f.name[-300:]
            lama = Dokumen.objects.get(pk=obj.pk).berkas
            super().save_model(request, obj, form, change)
            if lama and lama.name != obj.berkas.name:
                lama.delete(save=False)
            layanan.proses_teks(obj)
        else:
            super().save_model(request, obj, form, change)

    @admin.action(description="Terbitkan dokumen terpilih", permissions=["change"])
    def terbitkan(self, request, queryset):
        n = 0
        for dok in queryset.exclude(status=Dokumen.Status.TERBIT):
            layanan.putuskan_review(dok, request.user, True, dok.catatan_review)
            n += 1
        self.message_user(request, f"{n} dokumen diterbitkan.")

    @admin.action(description="Masukkan ke antrean OCR (PDF hasil scan)", permissions=["change"])
    def antrekan_ocr(self, request, queryset):
        from . import ocr

        if not ocr.tersedia():
            self.message_user(request, "Model bahasa OCR belum terpasang. Jalankan: manage.py siapkan_ocr", messages.ERROR)
            return
        for dok in queryset:
            ocr.antrekan(dok)
        self.message_user(request, f"{queryset.count()} dokumen masuk antrean OCR.")

    @admin.action(description="Ekstrak ulang teks PDF & perbarui indeks pencarian", permissions=["change"])
    def proses_ulang(self, request, queryset):
        for dok in queryset:
            layanan.proses_teks(dok)
        self.message_user(request, f"{queryset.count()} dokumen diproses ulang.")


@admin.register(HalamanDokumen)
class HalamanDokumenAdmin(admin.ModelAdmin):
    list_display = ["dokumen", "nomor"]
    search_fields = ["dokumen__judul"]
    readonly_fields = ["dokumen", "nomor", "teks"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(LogAkses)
class LogAksesAdmin(admin.ModelAdmin):
    list_display = ["waktu", "pengguna", "aksi", "dokumen", "keterangan", "alamat_ip"]
    list_filter = ["aksi", "waktu"]
    search_fields = ["pengguna__username", "pengguna__first_name", "dokumen__judul", "keterangan"]
    date_hierarchy = "waktu"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(TugasImpor)
class TugasImporAdmin(admin.ModelAdmin):
    list_display = ["pk", "dibuat", "dibuat_oleh", "status", "jumlah_total", "lihat"]
    list_filter = ["status"]
    readonly_fields = [f.name for f in TugasImpor._meta.fields]

    @admin.display(description="Detail")
    def lihat(self, obj):
        return format_html('<a href="{}">Buka halaman impor</a>', obj.get_absolute_url())

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(WajibGantiSandi)
class WajibGantiSandiAdmin(admin.ModelAdmin):
    list_display = ["pengguna", "nama", "dibuat"]
    search_fields = ["pengguna__username", "pengguna__first_name"]
    autocomplete_fields = ["pengguna"]

    @admin.display(description="Nama")
    def nama(self, obj):
        return obj.pengguna.get_full_name()


# Tambahkan aksi "wajib ganti kata sandi" pada daftar Pengguna bawaan Django.
from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.admin import UserAdmin  # noqa: E402

_User = get_user_model()
admin.site.unregister(_User)


@admin.register(_User)
class PenggunaAdmin(UserAdmin):
    actions = ["wajibkan_ganti_sandi"]
    list_display = ["username", "first_name", "last_name", "is_staff", "is_active", "last_login"]

    @admin.action(description="Wajibkan ganti kata sandi saat login berikutnya", permissions=["change"])
    def wajibkan_ganti_sandi(self, request, queryset):
        n = 0
        for u in queryset:
            _, baru = WajibGantiSandi.objects.get_or_create(pengguna=u)
            n += baru
        self.message_user(request, f"{n} pengguna wajib mengganti kata sandi saat login berikutnya.")
