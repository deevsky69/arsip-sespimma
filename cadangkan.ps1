# Mencadangkan database + PDF arsip. Dijalankan otomatis oleh Task Scheduler (lihat README),
# atau manual:  powershell -ExecutionPolicy Bypass -File .\cadangkan.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = Join-Path $env:USERPROFILE ".venvs\arsip-sespimma\Scripts\python.exe"
& $python manage.py cadangkan --simpan 14
