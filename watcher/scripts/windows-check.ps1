param(
    [string]$Config = "$env:APPDATA\checkmate-watcher\config.toml",
    [string]$Exe = "",
    [switch]$SkipNotification,
    [switch]$SkipAutostart
)

$ErrorActionPreference = "Continue"
$failures = 0

function Report {
    param([string]$Name, [bool]$Ok, [string]$Detail = "")
    if ($Ok) {
        Write-Host "[OK  ] $Name $Detail" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] $Name $Detail" -ForegroundColor Red
        $script:failures += 1
    }
}

if (-not $Exe) {
    $installed = Join-Path $env:LOCALAPPDATA "Programs\CheckMate\CheckMate.exe"
    $venvExe = Join-Path (Resolve-Path "..").Path ".venv\Scripts\checkmate-watcher.exe"
    $command = Get-Command checkmate-watcher -ErrorAction SilentlyContinue

    if (Test-Path $installed) {
        $Exe = $installed
    } elseif ($command) {
        $Exe = $command.Source
    } elseif (Test-Path $venvExe) {
        $Exe = $venvExe
    }
}

if (-not $Exe -or -not (Test-Path $Exe)) {
    Write-Host "checkmate-watcher introuvable. Passe -Exe <chemin>." -ForegroundColor Red
    exit 1
}

Write-Host "Binaire : $Exe"
Write-Host "Config  : $Config"
Write-Host ""

$version = & $Exe --version 2>&1
Report "version" ($LASTEXITCODE -eq 0) ($version -join " ")

$cliArgs = @("--config", $Config, "self-test")
if (-not $SkipNotification) {
    $cliArgs += "--notify"
}
$selfTest = & $Exe @cliArgs 2>&1
Report "self-test" ($LASTEXITCODE -eq 0) ""
$selfTest | ForEach-Object { Write-Host "    $_" }

if (-not $SkipAutostart) {
    & $Exe --config $Config install-autostart | Out-Null
    $createOk = $LASTEXITCODE -eq 0
    Report "installation demarrage auto" $createOk

    $task = schtasks /Query /TN CheckMate 2>&1
    Report "tache planifiee visible" ($LASTEXITCODE -eq 0) ($task | Select-Object -First 1)
}

Write-Host ""
if ($failures -eq 0) {
    Write-Host "Validation Windows : OK" -ForegroundColor Green
    exit 0
}
Write-Host "Validation Windows : $failures echec(s)" -ForegroundColor Red
exit 1
