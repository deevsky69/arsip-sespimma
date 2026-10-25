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
