from django.apps import AppConfig
from django.db.models.signals import post_migrate


class ArsipConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "arsip"
    verbose_name = "Arsip Naskah"

    def ready(self):
        from . import signals  # noqa: F401
        from .data_awal import bangun_indeks_bila_kosong, siapkan_data_awal

        post_migrate.connect(siapkan_data_awal, sender=self)
        post_migrate.connect(bangun_indeks_bila_kosong, sender=self)
