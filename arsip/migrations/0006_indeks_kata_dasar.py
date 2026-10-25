from django.db import migrations

from arsip.pencarian import SQL_BUAT_INDEKS, SQL_HAPUS_INDEKS

# Indeks pencarian dibuat ulang dengan kolom tambahan `akar` (kata dasar) dan `pustaka`.
# Isinya dibangun kembali otomatis setelah migrate (lihat arsip/data_awal.py).
SQL_INDEKS_LAMA = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS arsip_fts USING fts5("
    "judul, meta, isi, tokenize = 'unicode61 remove_diacritics 2')"
)


class Migration(migrations.Migration):
    dependencies = [("arsip", "0005_nama_halaman")]

    operations = [
        migrations.RunSQL([SQL_HAPUS_INDEKS, SQL_BUAT_INDEKS], [SQL_HAPUS_INDEKS, SQL_INDEKS_LAMA]),
    ]
