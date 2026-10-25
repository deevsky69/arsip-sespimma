# Menjalankan situs di komputer sendiri: http://127.0.0.1:8000
# Pemakaian:  powershell -ExecutionPolicy Bypass -File .\jalankan.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Virtualenv sengaja di luar OneDrive agar ribuan filenya tidak ikut tersinkron.
$venv = Join-Path $env:USERPROFILE ".venvs\arsip-sespimma"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $python)) {
    $pyDasar = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (-not (Test-Path $pyDasar)) { throw "Python 3.12 belum terpasang. Jalankan: winget install Python.Python.3.12" }
    Write-Host "Membuat virtualenv di $venv ..."
    & $pyDasar -m venv $venv
    & $python -m pip install --upgrade pip
}
& $python -m pip install -q -r requirements.txt
if (-not (Test-Path ".env")) {
    # Tanpa BOM agar terbaca benar oleh python-dotenv.
    [IO.File]::WriteAllText((Join-Path $PSScriptRoot ".env"), "DJANGO_DEBUG=true`n")
}
& $python manage.py migrate
& $python manage.py siapkan_ocr   # model bahasa OCR; dilewati bila sudah ada
& $python manage.py runserver 127.0.0.1:8000
