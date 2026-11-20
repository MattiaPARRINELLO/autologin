param(
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

uv sync
uv run pyinstaller packaging\checkmate.spec --noconfirm --clean

$candidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup introuvable. Installe-le avec : choco install innosetup"
}

& $iscc "/DMyAppVersion=$Version" "packaging\checkmate.iss"
Write-Host "Installeur cree dans dist-installer" -ForegroundColor Green
