"""Data awal yang dibuat otomatis setiap kali `migrate` dijalankan (idempotent)."""

KATEGORI_AWAL = [
    # (kode, nama, urutan) — nama lengkap bisa diubah di panel admin.
    ("NKP", "Naskah Karya Perorangan", 1),
    ("NASKAP", "NASKAP", 2),
    ("POLICY BRIEF", "Policy Brief", 3),
]

# Nama grup -> daftar permission "app_label.codename"
GRUP_PERAN = {
    "Pengunggah": [
        "arsip.add_dokumen",
        "arsip.view_dokumen",
    ],
    "Reviewer": [
        "arsip.add_dokumen",
        "arsip.view_dokumen",
        "arsip.change_dokumen",
        "arsip.review_dokumen",
        "arsip.impor_massal",
        "arsip.view_tugasimpor",
        "arsip.view_logakses",
    ],
    "Admin Arsip": [
        "arsip.add_dokumen",
        "arsip.view_dokumen",
        "arsip.change_dokumen",
        "arsip.delete_dokumen",
        "arsip.review_dokumen",
        "arsip.impor_massal",
        "arsip.view_tugasimpor",
        "arsip.add_kategori",
        "arsip.view_kategori",
        "arsip.change_kategori",
        "arsip.add_angkatan",
        "arsip.view_angkatan",
        "arsip.change_angkatan",
        "arsip.view_logakses",
        "arsip.view_halamandokumen",
        "auth.add_user",
        "auth.view_user",
        "auth.change_user",
        "auth.view_group",
        "arsip.view_wajibgantisandi",
        "arsip.add_wajibgantisandi",
        "arsip.delete_wajibgantisandi",
        "axes.view_accessattempt",
        "axes.delete_accessattempt",
        "axes.view_accesslog",
    ],
}


def siapkan_data_awal(sender=None, using="default", **kwargs):
    from django.contrib.auth.models import Group, Permission

    from .models import Kategori

    if not Kategori.objects.using(using).exists():
        for kode, nama, urutan in KATEGORI_AWAL:
            Kategori.objects.using(using).create(kode=kode, nama=nama, urutan=urutan)

    for nama_grup, daftar in GRUP_PERAN.items():
        grup, _ = Group.objects.using(using).get_or_create(name=nama_grup)
        perms = []
        for p in daftar:
            app_label, codename = p.split(".")
            perm = Permission.objects.using(using).filter(
                content_type__app_label=app_label, codename=codename
            ).first()
            if perm:
                perms.append(perm)
        grup.permissions.add(*perms)


def bangun_indeks_bila_kosong(sender=None, using="default", **kwargs):
    """Setelah migrasi yang membuat ulang tabel indeks, isi kembali indeks pencarian."""
    from . import pencarian
    from .models import Dokumen

    if Dokumen.objects.using(using).exists() and pencarian.indeks_kosong():
        n = pencarian.bangun_ulang_indeks()
        print(f"  Indeks pencarian dibangun ulang untuk {n} dokumen.")
