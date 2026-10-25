from django.urls import path

from . import views

app_name = "arsip"

urlpatterns = [
    path("", views.beranda, name="beranda"),
    path("cari/", views.cari, name="cari"),
    path("dokumen/<int:pk>/", views.detail, name="detail"),
    path("dokumen/<int:pk>/pdf/", views.baca, name="baca"),
    path("dokumen/<int:pk>/ubah/", views.ubah, name="ubah"),
    path("dokumen/<int:pk>/ocr/", views.ocr_jalankan, name="ocr_jalankan"),
    path("dokumen/<int:pk>/ocr/status/", views.ocr_status, name="ocr_status"),
    path("unggah/", views.unggah, name="unggah"),
    path("unggahan-saya/", views.unggahan_saya, name="unggahan_saya"),
    path("review/", views.review_daftar, name="review"),
    path("review/<int:pk>/", views.review_putus, name="review_putus"),
    path("kemiripan/", views.kemiripan_daftar, name="kemiripan"),
    path("kemiripan/<int:a>/<int:b>/", views.kemiripan_banding, name="kemiripan_banding"),
    path("impor/", views.impor_daftar, name="impor"),
    path("impor/<int:pk>/", views.impor_detail, name="impor_detail"),
    path("impor/<int:pk>/ulang/", views.impor_ulang, name="impor_ulang"),
]
