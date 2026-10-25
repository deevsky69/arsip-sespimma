from django.conf import settings


def ip_klien(request):
    """
    Alamat IP pengguna. Di belakang reverse proxy (Caddy), IP asli ada di X-Forwarded-For; entri
    terakhir ditambahkan oleh proxy kita sendiri sehingga bisa dipercaya (entri lain bisa dipalsukan).
    Dipakai untuk log akses dan untuk batas percobaan login (django-axes).
    """
    if getattr(settings, "ARSIP_DI_BELAKANG_PROXY", False):
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if xff:
            return xff.split(",")[-1].strip() or None
    return request.META.get("REMOTE_ADDR") or None
