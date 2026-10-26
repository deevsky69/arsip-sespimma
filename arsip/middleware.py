from django.conf import settings
from django.contrib.auth.views import redirect_to_login


class WajibLoginMiddleware:
    """Seluruh situs hanya untuk pengguna yang sudah login."""

    BEBAS = ("/akun/login/", "/admin/login/", "/static/", "/favicon.ico", "/robots.txt")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated and not request.path.startswith(self.BEBAS):
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        return self.get_response(request)


class WajibGantiSandiMiddleware:
    """Pengguna yang masih memakai kata sandi awal diarahkan ke halaman ganti kata sandi sampai menggantinya."""

    BOLEH = ("/akun/ganti-sandi/", "/akun/logout/", "/static/", "/favicon.ico")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not request.path.startswith(self.BOLEH):
            from django.shortcuts import redirect

            from .models import WajibGantiSandi

            if WajibGantiSandi.objects.filter(pengguna=user).exists():
                return redirect("password_change")
        return self.get_response(request)
