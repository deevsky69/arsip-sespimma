# Mengirim perubahan kode ke GitHub + server, membangun ulang aplikasi, lalu memeriksa kesehatannya.
# Pemakaian (dari folder proyek, setelah perubahan di-commit):
#   powershell -ExecutionPolicy Bypass -File .\perbarui_server.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (git status --porcelain) { throw "Masih ada perubahan yang belum di-commit. Commit dulu, lalu jalankan lagi." }
git push origin main;  if ($LASTEXITCODE -ne 0) { throw "Push ke GitHub gagal" }
git push server main;  if ($LASTEXITCODE -ne 0) { throw "Push ke server gagal" }
ssh -o BatchMode=yes arsip-vps "cd /srv/arsip && docker compose -f docker-compose.nginx.yml up -d --build && sleep 5 && docker compose -f docker-compose.nginx.yml exec -T app python manage.py periksa_sistem"
if ($LASTEXITCODE -ne 0) { throw "Ada masalah di server; lihat keluaran di atas." }
Write-Output "Server diperbarui: https://arsip-sespimma.awansurya.com"
