# Menarik salinan arsip dari SERVER ke OneDrive laptop (salinan di luar server).
# Dijalankan otomatis oleh Task Scheduler "ArsipSespimma-TarikCadangan", atau manual:
#   powershell -ExecutionPolicy Bypass -File .\tarik_cadangan.ps1
# Butuh akses SSH tanpa kata sandi ke server (Host "arsip-vps" di ~/.ssh/config).
$ErrorActionPreference = "Stop"
$tujuan = Join-Path $env:USERPROFILE "OneDrive\ArsipSespimma-cadangan-server"
$simpan = 7
New-Item -ItemType Directory -Force $tujuan | Out-Null
$nama = "paket-" + (Get-Date -Format "yyyyMMdd-HHmm") + ".zip"
$log = Join-Path $tujuan "tarik.log"

function Jalankan($perintah) {
    & ssh -o BatchMode=yes -o ConnectTimeout=20 arsip-vps $perintah
    if ($LASTEXITCODE -ne 0) { throw "Perintah di server gagal: $perintah" }
}

try {
    Jalankan "cd /srv/arsip && docker compose -f docker-compose.nginx.yml exec -T app python manage.py ekspor_data --ke /data/tarik-cadangan.zip"
    & scp -q -o BatchMode=yes arsip-vps:/srv/arsip/data/tarik-cadangan.zip (Join-Path $tujuan $nama)
    if ($LASTEXITCODE -ne 0) { throw "Gagal mengunduh paket dari server" }
    Jalankan "rm -f /srv/arsip/data/tarik-cadangan.zip"
    Get-ChildItem $tujuan -Filter "paket-*.zip" | Sort-Object Name -Descending | Select-Object -Skip $simpan | Remove-Item
    $mb = [math]::Round((Get-Item (Join-Path $tujuan $nama)).Length / 1MB, 1)
    Add-Content $log "$(Get-Date -Format s) OK $nama ($mb MB)"
    Write-Output "Cadangan server ditarik: $nama ($mb MB) -> $tujuan"
} catch {
    Add-Content $log "$(Get-Date -Format s) GAGAL $($_.Exception.Message)"
    throw
}
