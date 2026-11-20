param(
    [Parameter(Mandatory = $true)][string]$Pfx,
    [Parameter(Mandatory = $true)][string]$Path,
    [string]$Password = $env:CHECKMATE_PFX_PASSWORD
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Pfx)) { throw "certificat introuvable : $Pfx" }
if (-not (Test-Path $Path)) { throw "fichier a signer introuvable : $Path" }
if (-not $Password) { throw "definis CHECKMATE_PFX_PASSWORD" }

signtool sign /fd SHA256 /f $Pfx /p $Password /tr http://timestamp.digicert.com /td SHA256 $Path
if ($LASTEXITCODE -ne 0) { throw "signature echouee" }

signtool verify /pa $Path
if ($LASTEXITCODE -ne 0) { throw "verification de signature echouee" }

Write-Host "Signature verifiee : $Path" -ForegroundColor Green
