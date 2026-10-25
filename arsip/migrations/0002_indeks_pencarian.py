from django.db import migrations

from arsip.pencarian import SQL_BUAT_INDEKS, SQL_HAPUS_INDEKS


class Migration(migrations.Migration):
    dependencies = [("arsip", "0001_awal")]

    operations = [migrations.RunSQL(SQL_BUAT_INDEKS, SQL_HAPUS_INDEKS)]
