from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from . import pencarian
from .models import Dokumen


@receiver(post_save, sender=Dokumen)
def perbarui_indeks_metadata(sender, instance, raw=False, **kwargs):
    if not raw:
        pencarian.indeks_metadata(instance)


@receiver(post_delete, sender=Dokumen)
def bersihkan_dokumen(sender, instance, **kwargs):
    pencarian.hapus_dari_indeks(instance.pk)
    if instance.berkas:
        instance.berkas.delete(save=False)
