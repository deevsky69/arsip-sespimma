from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import HttpResponse, HttpResponsePermanentRedirect
from django.templatetags.static import static
from django.urls import include, path

from arsip.views import GantiSandiView

admin.site.site_header = settings.ARSIP_NAMA_SITUS
admin.site.site_title = settings.ARSIP_NAMA_SITUS
admin.site.index_title = "Panel Admin"


def favicon(request):
    # Alamat file statis dihitung saat diminta (bukan saat modul dimuat), agar situs tetap bisa
    # start meskipun manifest file statis produksi belum dibuat.
    return HttpResponsePermanentRedirect(static("img/favicon.ico"))

urlpatterns = [
    path("admin/", admin.site.urls),
    path("akun/login/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("akun/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("akun/ganti-sandi/", GantiSandiView.as_view(), name="password_change"),
    path(
        "akun/ganti-sandi/selesai/",
        auth_views.PasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
    path("favicon.ico", favicon),
    path("robots.txt", lambda r: HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")),
    path("", include("arsip.urls")),
]
