# ARSIP SESPIMMA

Sistem arsip digital untuk NKP, NASKAP, Policy Brief, dan jenis naskah lain dari setiap angkatan.
Semua dokumen dapat dicari sampai ke **isi setiap halaman**, bukan hanya judulnya.

Sudah tersedia: unggah, pembacaan metadata otomatis dari sampul, pencarian isi berbahasa Indonesia, saringan, login & peran, review, watermark, impor massal dari Google Drive, **cek kemiripan antarnaskah (deteksi naskah yang hanya mengganti lokus)**, dan backup otomatis.

## Fitur

| Fitur | Keterangan |
|---|---|
| Pencarian isi | Mencari di judul, penulis, lokus, kata kunci, abstrak, dan teks setiap halaman PDF. Hasil menampilkan cuplikan bersorot beserta nomor halamannya. Klik cuplikan untuk langsung membuka halaman tersebut. |
| Saringan & urutan | Kategori, angkatan, tahun, topik, pokjar, lokus. Hasil bisa diurutkan menurut relevansi, terbaru, judul, angkatan, atau penulis. |
| Sintaks pencarian | `konflik sosial` (semua kata), `"restorative justice"` (frasa persis), `-narkoba` (kecualikan). Kata dicocokkan dengan **kata dasarnya** (Sastrawi): `menangani` juga menemukan `penanganan` dan `ditangani`. **Sinonim/singkatan** dikenali (`narkoba` = `narkotika`, `pungli` = `pungutan liar`, `polres` = `kepolisian resor`, dst.; daftarnya di `arsip/bahasa.py`). Isi **daftar pustaka** tidak mendominasi hasil; kata yang hanya ada di daftar pustaka tetap bisa ditemukan bila tidak ada di isi. Jika tidak ada dokumen yang memuat semua kata, ditampilkan dokumen yang memuat sebagian kata. |
| Kategori fleksibel | NKP, NASKAP, POLICY BRIEF sudah tersedia. Kategori lain bisa ditambah lewat Panel Admin, tanpa mengubah kode. |
| Wajib login | Seluruh situs tertutup untuk publik dan tidak diindeks Google. |
| Watermark | Setiap PDF yang dibuka diberi tanda nama + NRP pembaca serta waktu akses. |
| Log akses | Siapa mencari apa, membuka dokumen apa, dan kapan (Panel Admin → Log akses). |
| Alur review | Unggahan dari *Pengunggah* masuk antrean; *Reviewer* menyetujui atau menolak dengan catatan. |
| Cek duplikat persis | File yang sama persis dengan yang sudah ada di arsip ditolak otomatis. |
| OCR PDF hasil scan | PDF tanpa teks dibaca otomatis dengan OCR (Tesseract, bahasa Indonesia + Inggris). Sampulnya langsung dibaca saat diunggah/diimpor sehingga judul, penulis, kategori, dan angkatan terisi; sisa halaman dikerjakan di latar belakang (±1 detik/halaman) dengan bilah kemajuan di halaman dokumen. Setelah selesai, isinya bisa dicari dan ikut dicek kemiripannya. Teks OCR bisa mengandung salah baca. |
| Impor massal | Tempel link folder Google Drive di menu **Impor Drive**, atau impor folder lewat terminal. Metadata dibaca otomatis dari sampul. |
| Cek kemiripan | Setiap naskah dibandingkan dengan seluruh arsip saat diunggah. Nama tempat/satuan dan angka disamarkan dulu, sehingga naskah yang **hanya mengganti lokus** tetap terdeteksi. Teks templat (sampul, surat pernyataan, kalimat topik) diabaikan. Reviewer melihat persentase di antrean review, di halaman dokumen, dan di menu **Kemiripan**, lengkap dengan laporan berdampingan per halaman yang menyorot kata yang diganti. |
| Batas percobaan login | Akun+IP dikunci 15 menit setelah 5 kali salah kata sandi (django-axes); admin bisa membuka kunci lebih awal. |
| Edit metadata | Reviewer dapat memperbaiki metadata langsung dari halaman dokumen (tombol *Ubah metadata*). |

## Peran pengguna

| Peran | Bisa |
|---|---|
| Pembaca (default) | Mencari dan membaca dokumen yang sudah terbit |
| Pengunggah | + mengunggah dokumen (masuk antrean review) |
| Reviewer | + menyetujui/menolak, langsung menerbitkan, mengedit metadata, melihat **kemiripan**, impor Drive, melihat log |
| Admin Arsip | + mengelola kategori, angkatan, dan akun pengguna (centang *Staff status* agar bisa masuk Panel Admin) |
| Superuser | Semua akses (dibuat dengan `createsuperuser`) |

Peran diatur di Panel Admin → Users → pilih pengguna → *Groups*.

---

## 1. Menjalankan di komputer sendiri (Windows)

Python 3.12 sudah terpasang. Dari folder proyek:

```powershell
powershell -ExecutionPolicy Bypass -File .\jalankan.ps1
```

Lalu buka http://127.0.0.1:8000. Sebelum login pertama kali, buat akun admin di jendela PowerShell lain:

```powershell
$py = "$env:USERPROFILE\.venvs\arsip-sespimma\Scripts\python.exe"
& $py manage.py createsuperuser
```

> Database dan PDF disimpan di folder yang ditunjuk `ARSIP_DATA_DIR` di `.env`. Di laptop ini:
> `C:\Users\bikpr\ArsipSespimma\data`, **sengaja di luar OneDrive** karena sinkronisasi OneDrive dapat
> merusak database yang sedang dipakai. Tanpa pengaturan itu, data disimpan di folder `data\` proyek.
>
> **Backup otomatis**: tugas Windows *ArsipSespimma-Cadangan* (Task Scheduler) menjalankan `cadangkan.ps1`
> setiap hari pukul 20.00 (atau segera setelah laptop menyala bila terlewat). Salinan database (14 terakhir)
> dan semua PDF disimpan ke `OneDrive\ArsipSespimma-cadangan`, sehingga ikut tersimpan di cloud.
> Riwayatnya ada di `cadangan.log`. Backup manual: `powershell -ExecutionPolicy Bypass -File .\cadangkan.ps1`.

Semua contoh perintah di bawah memakai `$py` seperti di atas. Di server, ganti dengan
`docker compose exec app python`.

## 2. Memasukkan dokumen dari folder Google Drive

### Cara termudah: menu "Impor Drive" di situs

1. Login sebagai Reviewer atau Admin Arsip, lalu buka menu **Impor Drive**.
2. Tempel link folder Drive (mis. folder pengumpulan NKP-3), lalu klik **Mulai impor**.
3. Sistem mengunduh semua PDF (termasuk subfolder per serdik), membaca sampulnya untuk mengenali
   kategori, angkatan, dan metadata lain, lalu menyimpannya. Kemajuan tampil langsung, dan halaman boleh ditinggal.
4. Hasilnya berupa tabel per file: **Masuk**, **Sudah ada** (duplikat dilewati), **Gagal**, atau
   **Dilewati** (serdik hanya mengunggah file Word tanpa PDF).

Syarat: folder dibagikan sebagai **"Siapa saja yang memiliki link"**. Folder privat tidak bisa dibaca;
unduh manual lalu pakai cara di bawah. Hanya satu impor yang berjalan dalam satu waktu.

### Lewat terminal (folder yang sudah diunduh)

Metadata **dibaca otomatis dari halaman sampul** naskah Sespim: judul, topik, nomor NKP/PB, nama,
NRP, nomor serdik, pokjar, angkatan, tahun, serta abstrak dan kata kunci (Policy Brief). Lokus ditebak
dari judul atau abstrak (Polda/Polres/Polsek/satuan Mabes). Nama subfolder pengumpulan
(`01 - NAMA SERDIK`) menjadi cadangan nama penulis, dan subfolder `NKP-3` / `PB-3` menjadi cadangan kategori.
Hanya file PDF yang diambil; file `.docx` diabaikan.

1. **Unduh** folder dari Google Drive (klik kanan folder → *Download*), lalu ekstrak ZIP-nya,
   mis. ke `data\impor\NKP-4`.

2. **Uji coba** untuk melihat apa yang akan masuk, tanpa menyimpan apa pun:
   ```powershell
   & $py manage.py impor_pdf data\impor --kering
   ```

3. (Opsional) **Periksa di Excel.** Perintah berikut menulis hasil pembacaan ke CSV:
   ```powershell
   & $py manage.py impor_pdf data\impor --buat-csv data\impor\metadata.csv
   ```
   Perbaiki yang keliru (beberapa penulis dipisah dengan `|`), simpan tetap sebagai CSV, lalu tambahkan
   `--csv data\impor\metadata.csv` pada langkah 4. Kolom CSV yang diisi menimpa hasil pembacaan otomatis.

4. **Impor**:
   ```powershell
   & $py manage.py impor_pdf data\impor --terbit
   ```
   Tanpa `--terbit`, dokumen masuk antrean review. Perintah ini aman dijalankan ulang karena file yang
   sama persis dilewati sebagai duplikat. Bila sampul tidak memuat angkatan/kategori, tambahkan
   `--angkatan 76 --tahun 2026 --kategori NKP`.

Metadata yang keliru bisa diperbaiki kapan saja di Panel Admin → Dokumen.

Form **Unggah** di situs memakai pembaca sampul yang sama: cukup pilih file, kategori, dan angkatan.
Kolom lain yang dikosongkan akan terisi sendiri.

## 3. Membuat akun pengguna massal

Siapkan CSV (bisa dari Excel) dengan kolom `nrp;nama;peran;email` (`peran` dan `email` opsional):

```
nrp;nama;peran
80010001;Andi Pratama;
80010002;Rina Lestari;reviewer
```

```powershell
& $py manage.py impor_pengguna serdik71.csv --keluaran akun_serdik71.csv
```

Username setiap akun adalah NRP. Kata sandi awal acak ditulis ke `akun_serdik71.csv`. Bagikan secara pribadi,
lalu **hapus file itu**. Pengguna dapat mengganti kata sandi dengan mengklik namanya di pojok kanan atas.

---

## 4. Memasang di server (hosting + domain sendiri)

> **Panduan lengkap langkah demi langkah, termasuk memindahkan seluruh data dari laptop: lihat [PANDUAN-VPS.md](PANDUAN-VPS.md).**
> Ringkasan di bawah untuk pemasangan baru tanpa data lama.

**Yang dibutuhkan**
- VPS Ubuntu 22.04/24.04, minimal 2 GB RAM dan 40 GB disk. Pilih penyedia dengan data center di Indonesia, karena data pribadi (nama, NRP) tunduk pada UU PDP.
- Domain atau subdomain, mis. `arsip.domainanda.id`, dengan **A record** yang mengarah ke IP VPS.

**Langkah**

```bash
# 1. Pasang Docker
curl -fsSL https://get.docker.com | sh

# 2. Salin folder proyek ke server (mis. lewat git atau scp) ke /srv/arsip, lalu:
cd /srv/arsip
cp .env.example .env
nano .env          # isi DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, DJANGO_CSRF_TRUSTED_ORIGINS, DOMAIN

# 3. Folder data harus bisa ditulis oleh kontainer (uid 1000)
mkdir -p data && sudo chown 1000:1000 data

# 4. Jalankan. Caddy otomatis membuat sertifikat HTTPS.
docker compose up -d --build

# 5. Buat akun admin pertama
docker compose exec app python manage.py createsuperuser
```

Untuk mengimpor PDF di server, unggah folder PDF ke `/srv/arsip/data/impor/`, lalu jalankan
`docker compose exec app python manage.py impor_pdf /data/impor/... --csv /data/impor/metadata.csv ...`.

**Memperbarui aplikasi**: salin kode terbaru, lalu jalankan `docker compose up -d --build`. Migrasi database berjalan otomatis.

### Backup (wajib)

Semua data ada di satu folder `data/`: `arsip.sqlite3` (database), `berkas/` (PDF), dan `cadangan/`.

```bash
# Tambahkan ke crontab (crontab -e): cadangan database + PDF setiap jam 2 pagi
0 2 * * * cd /srv/arsip && docker compose exec -T app python manage.py cadangkan --tujuan /data/cadangan --simpan 14
```

Lalu salin folder `data/cadangan` ke tempat lain secara berkala (mis. `rclone sync` ke Google Drive kantor atau
ke disk lain). Backup yang hanya tersimpan di server yang sama belum bisa disebut backup.

**Memulihkan dari cadangan**: hentikan situs, salin `database/arsip-<terbaru>.sqlite3` menjadi
`<folder data>/arsip.sqlite3` dan folder `berkas` menjadi `<folder data>/berkas`, lalu jalankan situs kembali.

## Pengaturan (`.env`)

| Variabel | Default | Keterangan |
|---|---|---|
| `DJANGO_DEBUG` | `false` | `true` hanya di komputer sendiri |
| `DJANGO_SECRET_KEY` | — | wajib di server; buat dengan `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | domain situs |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | — | `https://domain-anda` |
| `ARSIP_WATERMARK` | `true` | watermark nama pembaca di PDF |
| `ARSIP_IZINKAN_UNDUH` | `false` | tombol unduh untuk semua pengguna (admin selalu bisa) |
| `ARSIP_MAKS_UKURAN_MB` | `50` | batas ukuran unggahan |
| `ARSIP_NAMA_SITUS` | ARSIP SESPIMMA | judul situs |
| `ARSIP_TESSDATA` | `<data>/tessdata` | folder model bahasa OCR (`*.traineddata`) |
| `ARSIP_OCR_BAHASA` | `ind+eng` | bahasa OCR |
| `ARSIP_OCR_DPI` | `300` | resolusi OCR; lebih tinggi = lebih teliti tetapi lebih lambat |
| `ARSIP_OCR_OTOMATIS` | `true` | PDF scan langsung dibaca sampulnya & masuk antrean OCR saat diunggah |
| `ARSIP_DATA_DIR` | `./data` | folder database + PDF (jangan di folder yang disinkronkan OneDrive/Drive) |
| `ARSIP_CADANGAN_DIR` | `<data>/cadangan` | tujuan `manage.py cadangkan` |

## Perintah lain

| Perintah | Fungsi |
|---|---|
| `manage.py bangun_ulang_indeks` | membangun ulang indeks pencarian (`--ekstrak-ulang` untuk membaca ulang semua PDF) |
| `manage.py cadangkan` | cadangan database (konsisten) + PDF ke `ARSIP_CADANGAN_DIR` |
| `manage.py siapkan_ocr` | unduh model bahasa OCR (ind, eng) ke `ARSIP_TESSDATA` (sekali saja; `jalankan.ps1` melakukannya otomatis) |
| `manage.py jalankan_ocr [--semua] [--dokumen ID]` | kerjakan antrean OCR; `--semua` mengantrekan semua PDF scan yang belum/gagal di-OCR. Log pekerja otomatis ada di `<folder data>/ocr.log` |
| `manage.py ekspor_data` / `impor_data <zip>` | bungkus database + PDF jadi satu ZIP / pasang di server lain (pindah server) |
| `manage.py periksa_sistem` | pemeriksaan kesehatan: data, PDF, indeks, OCR, cadangan, keamanan |
| `manage.py cek_kemiripan` | hitung ulang kemiripan seluruh arsip (disarankan setelah impor besar, karena teks templat dikenali dari banyak naskah) |
| `manage.py test arsip` | menjalankan test otomatis |

## Catatan penting

- **Watermark tidak sama dengan DRM.** Pembaca tetap bisa menyimpan PDF dari penampil browser. Watermark
  dan log akses berfungsi membuat setiap kebocoran bisa dilacak ke orangnya, dan itulah efek jeranya.
- **OCR** dikerjakan oleh satu proses pekerja terpisah agar situs tetap cepat; dokumen diproses bergiliran. Kualitas hasil bergantung pada kualitas scan (miring, buram, atau tulisan tangan akan banyak salah baca). Daftar dokumen per status OCR ada di Panel Admin → Dokumen → saring *status OCR*; dari sana juga bisa "Masukkan ke antrean OCR".
- **Kapasitas**: SQLite dan indeks FTS5 sanggup menangani puluhan ribu dokumen di satu server. Bila kelak
  dibutuhkan, modul `arsip/pencarian.py` bisa diganti ke PostgreSQL atau Meilisearch tanpa mengubah bagian lain.
- **Lisensi PyMuPDF** (pembaca PDF) adalah AGPL. Untuk situs internal milik sendiri hal ini tidak masalah.
  Jika kelak dijadikan layanan untuk pihak lain, kode sumber harus dibuka atau dibeli lisensi komersialnya.

## Struktur kode

```
config/               pengaturan Django
arsip/models.py       Kategori, Angkatan, Dokumen, HalamanDokumen, LogAkses
arsip/pdf.py          ekstraksi teks & watermark (PyMuPDF)
arsip/sampul.py       pembaca metadata dari halaman sampul NKP / Policy Brief
arsip/impor.py        mesin impor massal (dipakai terminal & web)
arsip/drive.py        pengunduh folder Google Drive publik
arsip/tugas.py        menjalankan impor Drive di latar belakang
arsip/pencarian.py    indeks & pencarian SQLite FTS5
arsip/bahasa.py       kata dasar (Sastrawi), sinonim/singkatan, pemisah daftar pustaka
arsip/kemiripan.py    sidik jari teks, deteksi ganti lokus, laporan berdampingan
arsip/ocr.py          OCR (Tesseract via PyMuPDF), antrean & pekerja latar belakang
arsip/layanan.py      simpan unggahan, cek duplikat, review
arsip/views.py        halaman web
arsip/management/     perintah impor_pdf, impor_pengguna, cadangkan, bangun_ulang_indeks
templates/, static/   tampilan
```

## Rencana berikutnya

| Fase | Isi |
|---|---|
| 2 | Integrasi Turnitin (API bila lisensi mengizinkan, atau input hasil manual) |
| 3 | Pencarian semantik / tanya-jawab berbasis AI atas isi arsip; deteksi parafrase (kemiripan makna) |

## Gambar & lambang

| File | Sumber / lisensi |
|---|---|
| `static/img/lambang-polri.png`, `favicon.ico`, `favicon-64.png`, `apple-touch-icon.png` | Lambang Polri dari Wikimedia Commons ([Insignia of the Indonesian National Police.svg](https://commons.wikimedia.org/wiki/File:Insignia_of_the_Indonesian_National_Police.svg)), berstatus domain publik |

Untuk mengganti dengan file resmi dari Sespim/Lemdiklat (mis. lambang beresolusi tinggi),
timpa file dengan nama yang sama di `static/img/`.
