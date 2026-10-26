# Panduan Memindahkan ARSIP SESPIMMA ke VPS

Panduan ini memindahkan arsip dari laptop ke server sendiri (VPS + domain), **lengkap dengan seluruh
data** (dokumen, PDF, akun, kemiripan). Langkah 5–7 sudah digladikan di laptop dan berhasil.

Perkiraan waktu: 1–2 jam (sebagian besar menunggu unduhan/instalasi).

---

## 0. Yang perlu disiapkan

| Kebutuhan | Rekomendasi |
|---|---|
| VPS | Ubuntu 24.04, minimal **2 GB RAM, 2 vCPU, 40 GB disk**, data center di **Indonesia** (UU PDP) |
| Domain | mis. `arsip.domainanda.id`; buat **A record** yang mengarah ke IP VPS |
| Di laptop | Program untuk menyalin file ke server: **WinSCP** (gratis) atau perintah `scp` |
| Akun Git | Repositori **privat** berisi kode ini (GitHub/GitLab), lihat bagian 3 |

> Lakukan pemindahan saat tidak ada yang sedang mengunggah, supaya tidak ada dokumen yang tertinggal di laptop.

> **Server sudah dipakai situs lain dengan nginx** (port 80/443 terpakai)? Jangan pakai Caddy dan jangan
> menjalankan `ufw` sembarangan. Ikuti bagian **[Server bersama nginx](#server-bersama-nginx)** di bawah.

---

## 1. Amankan VPS

Login ke VPS (`ssh root@IP-VPS`), lalu:

```bash
apt update && apt upgrade -y
adduser arsip && usermod -aG sudo arsip        # akun harian, jangan pakai root terus
# PERHATIAN: bila SSH tidak di port 22, ganti 'OpenSSH' dengan port SSH Anda (mis. 'ufw allow 8998/tcp'),
# kalau tidak Anda akan terkunci dari server begitu ufw aktif.
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable
```

## 2. Pasang Docker

```bash
curl -fsSL https://get.docker.com | sh
usermod -aG docker arsip
```

Logout, lalu login lagi sebagai `arsip` (`ssh arsip@IP-VPS`).

## 3. Ambil kode

```bash
sudo mkdir -p /srv/arsip && sudo chown arsip:arsip /srv/arsip
git clone <URL-repositori-privat-anda> /srv/arsip
cd /srv/arsip
```

Untuk repositori privat GitHub, paling mudah memakai *Personal Access Token* (Settings → Developer
settings → Fine-grained tokens, akses *Contents: Read-only*) sebagai kata sandi saat `git clone`.

## 4. Isi pengaturan `.env`

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # salin hasilnya untuk DJANGO_SECRET_KEY
nano .env
```

Yang wajib diisi:

```
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=<hasil perintah di atas>
DJANGO_ALLOWED_HOSTS=arsip.domainanda.id
DJANGO_CSRF_TRUSTED_ORIGINS=https://arsip.domainanda.id
DOMAIN=arsip.domainanda.id
ARSIP_DI_BELAKANG_PROXY=true
```

Jangan isi `ARSIP_DATA_DIR` / `ARSIP_TESSDATA` (sudah diatur otomatis di Docker).

## 5. Buat paket data di laptop

Di PowerShell laptop, dari folder proyek:

```powershell
& "$env:USERPROFILE\.venvs\arsip-sespimma\Scripts\python.exe" manage.py ekspor_data --ke "$env:USERPROFILE\Desktop\paket-arsip.zip"
```

Hasilnya satu file ZIP (±65 MB untuk 49 naskah) berisi database dan semua PDF.

## 6. Kirim & pasang paket di VPS

Kirim file ke VPS (atau seret dengan WinSCP ke folder `/srv/arsip/data/`):

```powershell
ssh arsip@IP-VPS "mkdir -p /srv/arsip/data"
scp "$env:USERPROFILE\Desktop\paket-arsip.zip" arsip@IP-VPS:/srv/arsip/data/
```

Di VPS:

```bash
cd /srv/arsip
sudo chown -R 1000:1000 data                     # kontainer berjalan sebagai uid 1000
docker compose build
docker compose run --rm app python manage.py impor_data /data/paket-arsip.zip
```

`impor_data` menolak menimpa arsip yang sudah berisi dokumen (kecuali dengan `--timpa`), jadi aman bila
tidak sengaja dijalankan dua kali.

## 7. Jalankan & periksa

```bash
docker compose up -d
docker compose exec app python manage.py periksa_sistem
```

Semua baris harus `[OK]`; satu `[PERINGATAN]` soal cadangan wajar (diurus di langkah 8).
Buka `https://arsip.domainanda.id`. Sertifikat HTTPS dibuat otomatis oleh Caddy dalam 1–2 menit
pertama (pastikan A record domain sudah aktif). Login dengan akun admin yang sama seperti di laptop.

Bila situs belum bisa dibuka: `docker compose logs -f` (tekan Ctrl+C untuk keluar).

## 8. Cadangan otomatis (wajib)

```bash
crontab -e
```

Tambahkan baris:

```
0 2 * * * cd /srv/arsip && docker compose exec -T app python manage.py cadangkan --tujuan /data/cadangan --simpan 14 >> /srv/arsip/data/cadangan-cron.log 2>&1
```

Cadangan yang hanya ada di server yang sama belum cukup. Salin ke luar server, mis. ke Google Drive
memakai **rclone** (`sudo apt install rclone`, lalu `rclone config` untuk menghubungkan Google Drive
bernama `gdrive`), dan tambahkan di crontab:

```
30 2 * * * rclone sync /srv/arsip/data/cadangan gdrive:ArsipSespimma-cadangan
```

Periksa beberapa hari kemudian dengan `periksa_sistem` (baris "Cadangan terakhir").

## 9. Pemantauan

Daftar gratis di **UptimeRobot** (uptimerobot.com), tambahkan monitor HTTP(S) untuk
`https://arsip.domainanda.id/akun/login/`. Anda akan mendapat email bila situs mati.

## 10. Setelah pindah

- Mulai sekarang **server adalah satu-satunya tempat** mengunggah dokumen. Hentikan situs di laptop.
- Matikan backup terjadwal laptop: buka *Task Scheduler* → `ArsipSespimma-Cadangan` → *Disable*.
- Folder data di laptop (`C:\Users\bikpr\ArsipSespimma\data`) simpan dulu beberapa minggu sebagai cadangan, lalu boleh dihapus.

---

## Memperbarui aplikasi di kemudian hari

```bash
cd /srv/arsip
git pull
docker compose up -d --build        # migrasi database berjalan otomatis
docker compose exec app python manage.py periksa_sistem
```

## Pemecahan masalah

| Gejala | Tindakan |
|---|---|
| Situs tidak terbuka | `docker compose ps`, `docker compose logs -f app`, `docker compose logs -f caddy` |
| "CSRF verification failed" saat login | Periksa `DJANGO_CSRF_TRUSTED_ORIGINS=https://domain-anda` di `.env`, lalu `docker compose up -d` |
| Pengguna terkunci karena salah kata sandi | Tunggu 15 menit, atau Panel Admin → Axes → *Access attempts* → hapus; atau `docker compose exec app python manage.py axes_reset` |
| Lupa kata sandi pengguna | Panel Admin → Pengguna → pilih → *ubah kata sandi* |
| OCR tidak jalan | `docker compose exec app tail -50 /data/ocr.log`; ulangi dengan `docker compose exec app python manage.py jalankan_ocr` |
| Impor Drive gagal | `docker compose exec app tail -50 /data/impor.log`; Google kadang membatasi unduhan dari server, coba lagi beberapa jam kemudian atau unduh manual dan pakai `impor_pdf` |
| Memulihkan dari cadangan | `docker compose down`, salin `data/cadangan/database/arsip-<terbaru>.sqlite3` menjadi `data/arsip.sqlite3` dan folder `data/cadangan/berkas` menjadi `data/berkas`, lalu `docker compose up -d` |

---

## Server bersama nginx

Untuk server yang sudah menjalankan nginx untuk situs lain. Situs lain **tidak diubah**: hanya ditambah
satu file konfigurasi nginx untuk domain arsip, dan aplikasi hanya mendengarkan di `127.0.0.1`.

Ganti langkah 6–7 di atas dengan:

```bash
cd /srv/arsip
sudo chown -R 1000:1000 data
docker compose -f docker-compose.nginx.yml build
docker compose -f docker-compose.nginx.yml run --rm app python manage.py impor_data /data/paket-arsip.zip
docker compose -f docker-compose.nginx.yml up -d
curl -sI http://127.0.0.1:8010/akun/login/            # harus HTTP 200

sudo cp deploy/nginx-arsip-sespimma.conf /etc/nginx/sites-available/arsip-sespimma
sudo ln -s /etc/nginx/sites-available/arsip-sespimma /etc/nginx/sites-enabled/arsip-sespimma
sudo nginx -t && sudo systemctl reload nginx           # reload tidak memutus situs lain
sudo certbot --nginx -d arsip-sespimma.awansurya.com   # HTTPS; hanya mengubah file arsip-sespimma
docker compose -f docker-compose.nginx.yml exec app python manage.py periksa_sistem
```

Bila port 8010 sudah dipakai aplikasi lain, isi `ARSIP_PORT_LOKAL=<port lain>` di `.env` dan ganti angka
`8010` di file nginx. Untuk semua perintah lain di panduan ini, tambahkan `-f docker-compose.nginx.yml`
setelah `docker compose`.

---

## Pemasangan yang berjalan sekarang (Oktober 2026)

| | |
|---|---|
| Alamat | https://arsip-sespimma.awansurya.com |
| Server | `arsip-sespimma` (Ubuntu 22.04, IP lokal 192.168.111.247), SSH: `ssh arsip-vps` dari laptop (= `ssh -p 8998 surya@202.56.161.114`) |
| HTTPS | diurus **reverse proxy di router** (sertifikat Let's Encrypt ada di router); aplikasi melayani HTTP di port 80 |
| Menjalankan | `docker compose -f docker-compose.nginx.yml ...` di `/srv/arsip` (`.env`: `ARSIP_BIND=0.0.0.0`, `ARSIP_PORT_LOKAL=80`) |
| Kode | `/srv/arsip` adalah repositori git yang menerima push langsung dari laptop (`git push server main`) |
| Cadangan di server | cron akun `surya` pukul 02.00 → `/srv/arsip/data/cadangan` (14 terakhir) |
| Cadangan di luar server | Task Scheduler laptop `ArsipSespimma-TarikCadangan` pukul 21.00 → `OneDrive\ArsipSespimma-cadangan-server` (7 paket terakhir) |

**Memperbarui aplikasi** (dari laptop, setelah perubahan di-commit):

```powershell
powershell -ExecutionPolicy Bypass -File .\perbarui_server.ps1
```

Kebutuhan di reverse proxy router untuk domain ini: teruskan ke `http://192.168.111.247:80`, kirim header
`Host`, `X-Forwarded-For`, `X-Forwarded-Proto`, `client_max_body_size 60m`, `proxy_read_timeout 180s`,
dan alihkan `http://` ke `https://`.
