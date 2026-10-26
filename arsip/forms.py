from django import forms
from django.conf import settings

from .models import Angkatan, Dokumen, Kategori


class FormUnggah(forms.ModelForm):
    berkas = forms.FileField(
        label="File PDF",
        widget=forms.ClearableFileInput(attrs={"accept": "application/pdf,.pdf"}),
    )
    terbitkan = forms.BooleanField(
        label="Langsung terbitkan (tanpa antrean review)",
        required=False,
        initial=True,
    )

    class Meta:
        model = Dokumen
        fields = [
            "judul",
            "kategori",
            "angkatan",
            "nomor_tugas",
            "topik",
            "penulis",
            "nrp_penulis",
            "nomor_serdik",
            "kelompok",
            "pembimbing",
            "lokus",
            "kata_kunci",
            "abstrak",
        ]
        widgets = {
            "judul": forms.Textarea(attrs={"rows": 2}),
            "topik": forms.Textarea(attrs={"rows": 2}),
            "penulis": forms.Textarea(attrs={"rows": 3}),
            "abstrak": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, boleh_terbitkan=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not boleh_terbitkan:
            del self.fields["terbitkan"]
        self.fields["berkas"].help_text = f"Format PDF, ukuran maksimal {settings.ARSIP_MAKS_UKURAN_MB} MB."
        self.fields["kategori"].queryset = Kategori.objects.all()
        self.fields["angkatan"].queryset = Angkatan.objects.all()
        self.fields["kategori"].empty_label = "— pilih kategori —"
        self.fields["angkatan"].empty_label = "— pilih angkatan —"
        # Kolom berikut boleh dikosongkan: akan diisi otomatis dari halaman sampul PDF.
        for nama in ("judul", "penulis"):
            self.fields[nama].required = False
        self.fields["judul"].help_text = "Kosongkan untuk diambil otomatis dari halaman sampul."
        self.fields["penulis"].help_text = (
            "Satu nama per baris. Kosongkan untuk diambil otomatis dari sampul (NKP/Policy Brief)."
        )

    def clean_berkas(self):
        f = self.cleaned_data["berkas"]
        if not f.name.lower().endswith(".pdf"):
            raise forms.ValidationError("Hanya file PDF yang diterima.")
        maks = settings.ARSIP_MAKS_UKURAN_MB * 1024 * 1024
        if f.size > maks:
            raise forms.ValidationError(f"Ukuran file maksimal {settings.ARSIP_MAKS_UKURAN_MB} MB.")
        kepala = f.read(5)
        f.seek(0)
        if kepala != b"%PDF-":
            raise forms.ValidationError("Isi file bukan PDF yang valid.")
        return f


class FormReview(forms.Form):
    keputusan = forms.ChoiceField(choices=[("setujui", "Setujui & terbitkan"), ("tolak", "Tolak")])
    catatan = forms.CharField(label="Catatan untuk pengunggah", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def clean(self):
        data = super().clean()
        if data.get("keputusan") == "tolak" and not data.get("catatan", "").strip():
            self.add_error("catatan", "Tuliskan alasan penolakan.")
        return data


class FormImporDrive(forms.Form):
    link = forms.CharField(
        label="Link folder Google Drive",
        widget=forms.URLInput(attrs={"placeholder": "https://drive.google.com/drive/folders/..."}),
        help_text="Folder harus dibagikan sebagai 'Siapa saja yang memiliki link'. Subfolder ikut dibaca.",
    )
    kategori_default = forms.ModelChoiceField(
        label="Kategori (bila tidak terbaca)",
        queryset=Kategori.objects.all(),
        required=False,
        empty_label="— baca otomatis dari sampul —",
    )
    angkatan_default = forms.IntegerField(
        label="Nomor angkatan (bila tidak terbaca)", required=False, min_value=1, max_value=999
    )
    tahun_default = forms.IntegerField(label="Tahun (bila tidak terbaca)", required=False, min_value=1990, max_value=2100)
    terbitkan = forms.BooleanField(label="Langsung terbitkan (tanpa antrean review)", required=False, initial=True)

    def clean_link(self):
        from .drive import GagalDrive, id_folder

        link = self.cleaned_data["link"].strip()
        try:
            id_folder(link)
        except GagalDrive as e:
            raise forms.ValidationError(str(e))
        return link


class FormUbahDokumen(forms.ModelForm):
    class Meta:
        model = Dokumen
        fields = [
            "judul",
            "kategori",
            "angkatan",
            "nomor_tugas",
            "kelompok",
            "topik",
            "penulis",
            "nrp_penulis",
            "nomor_serdik",
            "pembimbing",
            "lokus",
            "kata_kunci",
            "abstrak",
        ]
        widgets = {
            "judul": forms.Textarea(attrs={"rows": 2}),
            "topik": forms.Textarea(attrs={"rows": 2}),
            "penulis": forms.Textarea(attrs={"rows": 3}),
            "abstrak": forms.Textarea(attrs={"rows": 8}),
        }
