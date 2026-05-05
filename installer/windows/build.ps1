# installer/windows/build.ps1
# Build pipeline: PyInstaller bundle → Inno Setup → installer/windows/dist/<file>.exe
# Run from repo root in PowerShell:
#   .\installer\windows\build.ps1

$ErrorActionPreference = "Stop"
$PROJECT_ROOT = (Get-Item $PSScriptRoot).Parent.Parent.FullName
Set-Location $PROJECT_ROOT

Write-Host "[build] PyInstaller bundle..." -ForegroundColor Cyan
& "$env:USERPROFILE\pipx\venvs\claude-mnemos\Scripts\python.exe" -m PyInstaller installer/pyinstaller/mnemos.spec --noconfirm

Write-Host "[build] Inno Setup compile..." -ForegroundColor Cyan
$ISCC = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $ISCC)) {
    throw "Inno Setup 6 not found at $ISCC. Install from https://jrsoftware.org/isinfo.php"
}
& $ISCC installer/windows/mnemos.iss

$out = Join-Path $PROJECT_ROOT "installer\windows\dist\claude-mnemos-setup-x64.exe"
if (Test-Path $out) {
    Write-Host "[ok] Installer at $out" -ForegroundColor Green
} else {
    throw "ISCC ran but installer was not produced at $out"
}
