from django.conf import settings

from .models import Dokumen


def navigasi(request):
    data = {"NAMA_SITUS": settings.ARSIP_NAMA_SITUS, "LOGIN_KUNCI_MENIT": settings.LOGIN_KUNCI_MENIT}
    user = getattr(request, "user", None)
    if user and user.is_authenticated and user.has_perm("arsip.review_dokumen"):
        data["jumlah_menunggu_review"] = Dokumen.objects.filter(status=Dokumen.Status.MENUNGGU).count()
    return data
