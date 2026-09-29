# PocketSmart AI Launch Script for PowerShell
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "        Starting PocketSmart AI Budget Planner          " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$pythonExe = "$scriptDir\venv\Scripts\python.exe"
$pipExe = "$scriptDir\venv\Scripts\pip.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}

Write-Host "Activating virtual environment..." -ForegroundColor Green
if (Test-Path "$scriptDir\venv\Scripts\Activate.ps1") {
    try { & "$scriptDir\venv\Scripts\Activate.ps1" } catch {}
}

Write-Host "Verifying dependencies..." -ForegroundColor Yellow
& $pipExe install -r requirements.txt

Write-Host "`nStarting PocketSmart AI web server..." -ForegroundColor Green
& $pythonExe app.py

