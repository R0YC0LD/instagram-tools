<#
  Builds dist\IGDMTool.exe (single file, no console window, Pacman icon).
  Usage:  .\build.ps1            # run tests, then build
          .\build.ps1 -SkipTests
  Works in Windows PowerShell 5.1 and PowerShell 7 (native tools write progress to stderr, so we check
  exit codes ourselves instead of relying on $ErrorActionPreference).
#>
param([switch]$SkipTests)
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

function Run($what, [scriptblock]$cmd) {
    & $cmd
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" }
}

if (-not (Test-Path .venv)) { Run "venv creation" { python -m venv .venv } }
$py = ".\.venv\Scripts\python.exe"
Run "dependency install" { & $py -m pip install --quiet --disable-pip-version-check -r requirements-dev.txt }

Run "icon generation" { & $py tools\make_icon.py }          # (re)draw the icon + embedded assets
if (-not $SkipTests) { Run "tests" { & $py tests\run_all.py } }

Run "PyInstaller" {
    & ".\.venv\Scripts\pyinstaller.exe" --noconfirm --clean --onefile --windowed `
        --name IGDMTool --icon assets\app.ico --paths src `
        --collect-all instagrapi --collect-submodules curl_cffi `
        src\igdm_launcher.py
}

$hash = (Get-FileHash dist\IGDMTool.exe -Algorithm SHA256).Hash
"SHA256  IGDMTool.exe  $hash" | Set-Content dist\SHA256.txt
$mb = [math]::Round((Get-Item dist\IGDMTool.exe).Length / 1MB, 1)
Write-Host ""
Write-Host "Built dist\IGDMTool.exe ($mb MB)"
Write-Host "SHA256 $hash"