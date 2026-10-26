from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import layanan, pdf, pencarian
from .forms import FormReview, FormUnggah
from .models import Angkatan, Dokumen, Kategori, LogAkses

PER_HALAMAN = 20


def _ip(request):
    from .keamanan import ip_klien

    return ip_klien(request)


def _catat(request, aksi, dokumen=None, keterangan=""):
    LogAkses.objects.create(
        pengguna=request.user, dokumen=dokumen, aksi=aksi, keterangan=keterangan[:500], alamat_ip=_ip(request)
    )


def _boleh_lihat(user, dok):
    return (
        dok.status == Dokumen.Status.TERBIT
        or (dok.diunggah_oleh_id and dok.diunggah_oleh_id == user.pk)
        or user.has_perm("arsip.review_dokumen")
    )


def _int_atau_none(nilai):
    try:
        return int(nilai)
    except (TypeError, ValueError):
        return None


def beranda(request):
    terbit = Dokumen.objects.filter(status=Dokumen.Status.TERBIT)
    konteks = {
        "total": terbit.count(),
        "per_kategori": Kategori.objects.annotate(
            jumlah=Count("dokumen", filter=Q(dokumen__status=Dokumen.Status.TERBIT))
        ),
        "per_angkatan": Angkatan.objects.annotate(
            jumlah=Count("dokumen", filter=Q(dokumen__status=Dokumen.Status.TERBIT))
        ).filter(jumlah__gt=0),
        "terbaru": [
            pencarian.Hasil(dokumen_id=d.pk, skor=0, dokumen=d)
            for d in terbit.select_related("kategori", "angkatan").order_by("-dibuat")[:8]
        ],
    }
    return render(request, "arsip/beranda.html", konteks)


URUTAN = {
    # kode: (label, kunci pengurutan untuk queryset)
    "relevansi": ("Paling relevan", None),
    "terbaru": ("Terbaru ditambahkan", ["-dibuat"]),
    "judul": ("Judul A–Z", ["judul"]),
    "angkatan": ("Angkatan terbaru", ["-angkatan__nomor", "kategori__urutan", "judul"]),
    "penulis": ("Penulis A–Z", ["penulis"]),
}


def cari(request):
    g = request.GET
    q = g.get("q", "").strip()[:300]
    saringan = pencarian.Saringan(
        kategori=g.get("kategori", "").strip(),
        angkatan=_int_atau_none(g.get("angkatan")),
        tahun=_int_atau_none(g.get("tahun")),
        topik=g.get("topik", "").strip(),
        kelompok=g.get("kelompok", "").strip(),
        lokus=g.get("lokus", "").strip()[:100],
    )
    urutan = g.get("urut", "")
    if urutan not in URUTAN or (urutan == "relevansi" and not q):
        urutan = "relevansi" if q else "angkatan"
    mode = "AND"

    if q:
        hasil, mode = pencarian.cari(q, saringan)
        if URUTAN[urutan][1]:
            posisi = {pk: i for i, pk in enumerate(
                Dokumen.objects.filter(pk__in=[h.dokumen_id for h in hasil])
                .order_by(*URUTAN[urutan][1]).values_list("pk", flat=True)
            )}
            hasil.sort(key=lambda h: posisi.get(h.dokumen_id, 0))
        halaman = Paginator(hasil, PER_HALAMAN).get_page(g.get("hal"))
        dok_map = Dokumen.objects.select_related("kategori", "angkatan").in_bulk(
            [h.dokumen_id for h in halaman.object_list]
        )
        for h in halaman.object_list:
            h.dokumen = dok_map.get(h.dokumen_id)
        daftar = pencarian.isi_cuplikan([h for h in halaman.object_list if h.dokumen], q)
        if halaman.number == 1:
            _catat(request, LogAkses.Aksi.CARI, keterangan=q)
    else:
        qs = saringan.queryset().select_related("kategori", "angkatan").order_by(*URUTAN[urutan][1])
        halaman = Paginator(qs, PER_HALAMAN).get_page(g.get("hal"))
        daftar = [pencarian.Hasil(dokumen_id=d.pk, skor=0, dokumen=d) for d in halaman.object_list]

    parameter = g.copy()
    parameter.pop("hal", None)
    terbit = Dokumen.objects.filter(status=Dokumen.Status.TERBIT)
    konteks = {
        "q": q,
        "s": saringan,
        "ada_saringan": any([saringan.kategori, saringan.angkatan, saringan.tahun, saringan.topik,
                             saringan.kelompok, saringan.lokus]),
        "urutan": urutan,
        "pilihan_urutan": [(k, v[0]) for k, v in URUTAN.items() if q or k != "relevansi"],
        "mode": mode,
        "daftar": daftar,
        "halaman": halaman,
        "total": halaman.paginator.count,
        "parameter_tanpa_hal": parameter.urlencode(),
        "semua_kategori": Kategori.objects.all(),
        "semua_angkatan": Angkatan.objects.all(),
        "semua_tahun": Angkatan.objects.order_by("-tahun").values_list("tahun", flat=True).distinct(),
        "semua_topik": terbit.exclude(topik="").order_by("topik").values_list("topik", flat=True).distinct(),
        "semua_kelompok": terbit.exclude(kelompok="").order_by("kelompok").values_list("kelompok", flat=True).distinct(),
        "semua_lokus": terbit.exclude(lokus="").order_by("lokus").values_list("lokus", flat=True).distinct(),
    }
    return render(request, "arsip/cari.html", konteks)


@permission_required("arsip.change_dokumen", raise_exception=True)
def ubah(request, pk):
    from .forms import FormUbahDokumen

    dok = get_object_or_404(Dokumen, pk=pk)
    if request.method == "POST":
        form = FormUbahDokumen(request.POST, instance=dok)
        if form.is_valid():
            form.save()  # sinyal post_save memperbarui indeks pencarian
            messages.success(request, "Metadata dokumen disimpan.")
            return redirect(dok)
    else:
        form = FormUbahDokumen(instance=dok)
    return render(request, "arsip/ubah.html", {"form": form, "dok": dok})


def detail(request, pk):
    dok = get_object_or_404(Dokumen.objects.select_related("kategori", "angkatan", "diunggah_oleh"), pk=pk)
    if not _boleh_lihat(request.user, dok):
        raise PermissionDenied
    q = request.GET.get("q", "").strip()[:300]
    cuplikan = pencarian.cari_dalam_dokumen(dok.pk, q) if q else []
    hlm_awal = _int_atau_none(request.GET.get("hlm")) or (cuplikan[0].halaman if cuplikan else 1)
    _catat(request, LogAkses.Aksi.LIHAT, dok)
    konteks = {
        "dok": dok,
        "q": q,
        "cuplikan": cuplikan,
        "hlm_awal": hlm_awal,
        "izinkan_unduh": settings.ARSIP_IZINKAN_UNDUH or request.user.is_staff,
        "boleh_review": request.user.has_perm("arsip.review_dokumen") and dok.status == Dokumen.Status.MENUNGGU,
        "kemiripan": _kemiripan_dokumen(dok) if request.user.has_perm("arsip.review_dokumen") else None,
        "form_review": FormReview(),
    }
    return render(request, "arsip/detail.html", konteks)


def baca(request, pk):
    """Sajikan PDF (dengan watermark nama pembaca) langsung dari folder privat."""
    dok = get_object_or_404(Dokumen, pk=pk)
    if not _boleh_lihat(request.user, dok):
        raise PermissionDenied
    unduh = request.GET.get("unduh") == "1"
    if unduh and not (settings.ARSIP_IZINKAN_UNDUH or request.user.is_staff):
        raise PermissionDenied

    if settings.ARSIP_WATERMARK:
        u = request.user
        nama = u.get_full_name() or u.username
        waktu = timezone.localtime().strftime("%d-%m-%Y %H:%M")
        isi = pdf.beri_watermark(
            dok.path_berkas,
            f"{nama} - {u.username}",
            f"Diakses oleh {nama} ({u.username}) pada {waktu} WIB melalui {settings.ARSIP_NAMA_SITUS}. "
            "Dilarang menyebarluaskan tanpa izin.",
        )
    else:
        with open(dok.path_berkas, "rb") as f:
            isi = f.read()

    _catat(request, LogAkses.Aksi.UNDUH if unduh else LogAkses.Aksi.BACA, dok)
    nama_file = f"{dok.kategori.kode} Angkatan {dok.angkatan.nomor} - {dok.judul[:80]}.pdf"
    nama_file = "".join(c for c in nama_file if c not in '\\/:*?"<>|\r\n')
    respons = HttpResponse(isi, content_type="application/pdf")
    respons["Content-Disposition"] = (
        f"{'attachment' if unduh else 'inline'}; filename=\"dokumen-{dok.pk}.pdf\"; "
        f"filename*=UTF-8''{quote(nama_file)}"
    )
    respons["Cache-Control"] = "private, no-store"
    respons["X-Content-Type-Options"] = "nosniff"
    return respons


@permission_required("arsip.add_dokumen", raise_exception=True)
def unggah(request):
    boleh_terbitkan = request.user.has_perm("arsip.review_dokumen")
    if request.method == "POST":
        form = FormUnggah(request.POST, request.FILES, boleh_terbitkan=boleh_terbitkan)
        if form.is_valid():
            dok = form.save(commit=False)
            terbitkan = boleh_terbitkan and form.cleaned_data.get("terbitkan")
            try:
                dok = layanan.simpan_dokumen_baru(dok, form.cleaned_data["berkas"], request.user, terbitkan)
            except layanan.DokumenDuplikat as e:
                form.add_error(
                    "berkas",
                    f"File yang sama persis sudah ada di arsip: \"{e.dokumen_lama.judul}\" "
                    f"({e.dokumen_lama.kategori}, {e.dokumen_lama.angkatan}).",
                )
            except pdf.PDFTidakValid as e:
                form.add_error("berkas", str(e))
            except layanan.MetadataKurang as e:
                form.add_error(None, str(e))
            else:
                if dok.perlu_ocr:
                    messages.warning(
                        request,
                        "PDF ini tampaknya hasil scan (tidak ada teks), sehingga isinya belum bisa dicari. "
                        "Dokumen tetap tersimpan dan ditandai 'perlu OCR'.",
                    )
                if dok.status == Dokumen.Status.TERBIT:
                    messages.success(request, "Dokumen berhasil diunggah dan diterbitkan.")
                else:
                    messages.success(request, "Dokumen berhasil diunggah dan menunggu review.")
                return redirect(dok)
    else:
        form = FormUnggah(boleh_terbitkan=boleh_terbitkan)
    return render(request, "arsip/unggah.html", {"form": form})


def unggahan_saya(request):
    daftar = (
        Dokumen.objects.filter(diunggah_oleh=request.user)
        .select_related("kategori", "angkatan")
        .order_by("-dibuat")
    )
    return render(request, "arsip/unggahan_saya.html", {"daftar": daftar})


@permission_required("arsip.review_dokumen", raise_exception=True)
def review_daftar(request):
    daftar = list(
        Dokumen.objects.filter(status=Dokumen.Status.MENUNGGU)
        .select_related("kategori", "angkatan", "diunggah_oleh")
        .order_by("dibuat")
    )
    for d in daftar:
        teratas = _kemiripan_dokumen(d, batas=1)
        d.mirip = teratas[0] if teratas else None
    return render(request, "arsip/review_daftar.html", {"daftar": daftar})


@require_POST
@permission_required("arsip.review_dokumen", raise_exception=True)
def review_putus(request, pk):
    dok = get_object_or_404(Dokumen, pk=pk, status=Dokumen.Status.MENUNGGU)
    form = FormReview(request.POST)
    if not form.is_valid():
        for kesalahan in form.errors.values():
            messages.error(request, " ".join(kesalahan))
        return redirect(dok)
    setujui = form.cleaned_data["keputusan"] == "setujui"
    layanan.putuskan_review(dok, request.user, setujui, form.cleaned_data["catatan"])
    messages.success(request, "Dokumen diterbitkan." if setujui else "Dokumen ditolak.")
    return redirect(reverse("arsip:review"))


# ---------------------------------------------------------------------------
# Impor dari Google Drive
# ---------------------------------------------------------------------------


@permission_required("arsip.impor_massal", raise_exception=True)
def impor_daftar(request):
    from . import tugas as tugas_impor
    from .forms import FormImporDrive
    from .models import TugasImpor

    if request.method == "POST":
        form = FormImporDrive(request.POST)
        if form.is_valid():
            berjalan = tugas_impor.tugas_berjalan()
            if berjalan:
                messages.error(request, "Masih ada impor yang berjalan. Tunggu sampai selesai, lalu coba lagi.")
                return redirect(berjalan[0])
            d = form.cleaned_data
            t = TugasImpor.objects.create(
                link=d["link"],
                kategori_default=d["kategori_default"],
                angkatan_default=d["angkatan_default"],
                tahun_default=d["tahun_default"],
                terbitkan=d["terbitkan"],
                dibuat_oleh=request.user,
            )
            tugas_impor.mulai(t)
            return redirect(t)
    else:
        form = FormImporDrive()
    riwayat = TugasImpor.objects.select_related("dibuat_oleh")[:20]
    return render(request, "arsip/impor.html", {"form": form, "riwayat": riwayat})


@permission_required("arsip.impor_massal", raise_exception=True)
def impor_detail(request, pk):
    from .models import TugasImpor

    t = get_object_or_404(TugasImpor.objects.select_related("dibuat_oleh", "kategori_default"), pk=pk)
    urutan = {"gagal": 0, "dilewati": 1, "duplikat": 2, "berhasil": 3}
    hasil = sorted(t.hasil, key=lambda h: (urutan.get(h.get("status"), 9), h.get("nama_file", "")))
    return render(request, "arsip/impor_detail.html", {"t": t, "hasil": hasil, "jumlah": t.ringkasan()})


@require_POST
@permission_required("arsip.impor_massal", raise_exception=True)
def impor_ulang(request, pk):
    from . import tugas as tugas_impor
    from .models import TugasImpor

    t = get_object_or_404(TugasImpor, pk=pk)
    if t.berjalan and not t.terputus:
        messages.info(request, "Impor ini masih berjalan.")
    elif tugas_impor.tugas_berjalan():
        messages.error(request, "Masih ada impor lain yang berjalan.")
    else:
        # Dokumen yang sudah masuk pada percobaan sebelumnya otomatis terlewati sebagai duplikat.
        t.status, t.log = TugasImpor.Status.ANTRE, t.log + "--- diulang ---\n"
        t.save(update_fields=["status", "log", "diperbarui"])
        tugas_impor.mulai(t)
    return redirect(t)


# ---------------------------------------------------------------------------
# Cek kemiripan
# ---------------------------------------------------------------------------


def _kemiripan_dokumen(dok, batas=5):
    from .models import Kemiripan

    baris = Kemiripan.objects.filter(Q(dokumen_a=dok) | Q(dokumen_b=dok)).select_related(
        "dokumen_a__kategori", "dokumen_a__angkatan", "dokumen_b__kategori", "dokumen_b__angkatan"
    )
    hasil = []
    for k in baris:
        lain, persen_ini, persen_lain = k.dari_sisi(dok)
        hasil.append({"k": k, "lain": lain, "persen_ini": persen_ini, "persen_lain": persen_lain})
    hasil.sort(key=lambda x: -max(x["persen_ini"], x["persen_lain"]))
    return hasil[:batas]


@permission_required("arsip.review_dokumen", raise_exception=True)
def kemiripan_daftar(request):
    from django.db.models.functions import Greatest

    from .models import Kemiripan

    minimal = _int_atau_none(request.GET.get("min"))
    minimal = 8 if minimal is None else max(0, min(minimal, 100))
    angkatan = _int_atau_none(request.GET.get("angkatan"))
    qs = (
        Kemiripan.objects.annotate(maks=Greatest("persen_a", "persen_b"))
        .filter(maks__gte=minimal)
        .select_related("dokumen_a__kategori", "dokumen_a__angkatan", "dokumen_b__kategori", "dokumen_b__angkatan")
        .order_by("-maks")
    )
    if angkatan:
        qs = qs.filter(Q(dokumen_a__angkatan__nomor=angkatan) | Q(dokumen_b__angkatan__nomor=angkatan))
    halaman = Paginator(qs, 50).get_page(request.GET.get("hal"))
    return render(
        request,
        "arsip/kemiripan_daftar.html",
        {"halaman": halaman, "minimal": minimal, "angkatan": angkatan, "semua_angkatan": Angkatan.objects.all()},
    )


@permission_required("arsip.review_dokumen", raise_exception=True)
def kemiripan_banding(request, a, b):
    from . import kemiripan
    from .models import tingkat_kemiripan

    dok_a = get_object_or_404(Dokumen.objects.select_related("kategori", "angkatan"), pk=a)
    dok_b = get_object_or_404(Dokumen.objects.select_related("kategori", "angkatan"), pk=b)
    hasil = kemiripan.bandingkan(dok_a, dok_b)
    contoh = []
    for bagian in hasil.bagian:
        for pasangan in bagian.contoh_diganti:
            if pasangan not in contoh:
                contoh.append(pasangan)
    return render(
        request,
        "arsip/kemiripan_banding.html",
        {
            "a": dok_a,
            "b": dok_b,
            "hasil": hasil,
            "tingkat": tingkat_kemiripan(max(hasil.persen_a, hasil.persen_b)),
            "contoh_diganti": contoh[:12],
        },
    )


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------


@require_POST
@permission_required("arsip.change_dokumen", raise_exception=True)
def ocr_jalankan(request, pk):
    from . import ocr

    dok = get_object_or_404(Dokumen, pk=pk)
    if not ocr.tersedia():
        messages.error(
            request,
            "Model bahasa OCR belum terpasang di server. Jalankan perintah: python manage.py siapkan_ocr",
        )
    elif dok.status_ocr in (Dokumen.StatusOCR.ANTRE, Dokumen.StatusOCR.PROSES):
        messages.info(request, "Dokumen ini sudah ada di antrean OCR.")
    else:
        ocr.antrekan(dok)
        messages.success(request, "Dokumen dimasukkan ke antrean OCR. Halaman ini akan diperbarui otomatis.")
    return redirect(dok)


def ocr_status(request, pk):
    from django.http import JsonResponse

    dok = get_object_or_404(Dokumen, pk=pk)
    if not _boleh_lihat(request.user, dok):
        raise PermissionDenied
    return JsonResponse(
        {
            "status": dok.status_ocr,
            "label": dok.get_status_ocr_display(),
            "kemajuan": dok.ocr_kemajuan,
            "total": dok.jumlah_halaman,
            "pesan": dok.ocr_pesan,
        }
    )


# ---------------------------------------------------------------------------
# Ganti kata sandi
# ---------------------------------------------------------------------------

from django.contrib.auth.views import PasswordChangeView  # noqa: E402
from django.urls import reverse_lazy  # noqa: E402


class GantiSandiView(PasswordChangeView):
    """Ganti kata sandi; sekaligus menghapus kewajiban ganti sandi (akun baru dengan sandi awal)."""

    success_url = reverse_lazy("arsip:beranda")

    def get_context_data(self, **kwargs):
        from .models import WajibGantiSandi

        konteks = super().get_context_data(**kwargs)
        konteks["wajib_ganti"] = WajibGantiSandi.objects.filter(pengguna=self.request.user).exists()
        return konteks

    def form_valid(self, form):
        from .models import WajibGantiSandi

        respons = super().form_valid(form)
        WajibGantiSandi.objects.filter(pengguna=self.request.user).delete()
        messages.success(self.request, "Kata sandi berhasil diganti. Selamat menggunakan ARSIP SESPIMMA.")
        return respons
