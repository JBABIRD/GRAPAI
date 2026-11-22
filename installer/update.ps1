<#
  Updates GRAPAI to the latest version on GitHub, for this user only (no admin rights).

  Downloads the newest code of the update branch (settings.ps1: $UpdateBranch, default from the installer's
  manifest), then runs that version's installer over this installation. Boards, settings and models stay;
  only models that are new or changed are downloaded, and every model is checked against its SHA-256.

  Options:
    -Force    reinstall even if this version is already the latest
    -Check    only say whether an update is available (exit code 10 = update available)
#>
[CmdletBinding()]
param([switch]$Force, [switch]$Check)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Root = $PSScriptRoot
$Manifest = Get-Content -Raw (Join-Path $Root "app\installer\manifest.json") | ConvertFrom-Json
$Repo = $Manifest.update.repo
$UpdateBranch = $Manifest.update.branch
$GrapaiPort = 8000
$settings = Join-Path $Root "settings.ps1"
if (Test-Path $settings) { . $settings }
$versionFile = Join-Path $Root "version.txt"
$installed = if (Test-Path $versionFile) { (Get-Content -Raw $versionFile).Trim().Split(" ")[0] } else { "" }

function Done([int]$code) { if (-not $Check) { Read-Host "Press Enter to close" | Out-Null }; exit $code }

try {
    $latest = Invoke-RestMethod -UseBasicParsing -TimeoutSec 20 -Headers @{ "User-Agent" = "GRAPAI-updater" } `
        -Uri "https://api.github.com/repos/$Repo/commits/$UpdateBranch"
} catch {
    Write-Host "Could not reach GitHub to check for updates: $($_.Exception.Message)" -ForegroundColor Red
    Done 1
}
$sha = $latest.sha
$when = ([datetime]$latest.commit.committer.date).ToLocalTime().ToString("yyyy-MM-dd HH:mm")
$title = ($latest.commit.message -split "`n")[0]
$short = $sha.Substring(0, 7)

if ($installed -eq $sha -and -not $Force) {
    Write-Host "GRAPAI is up to date ($UpdateBranch, $short, $when)." -ForegroundColor Green
    Done 0
}
if ($Check) {
    Write-Host "Update available: $short ($when) $title"
    exit 10
}

Write-Host "Updating GRAPAI to $short from $when on '$UpdateBranch':" -ForegroundColor Cyan
Write-Host "  $title"
if ($installed) { Write-Host "  (installed: $($installed.Substring(0, [math]::Min(7, $installed.Length))))" }

# GRAPAI must not be running while its files are replaced.
$running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($Root, [StringComparison]::OrdinalIgnoreCase) })
if ($running.Count) {
    $a = Read-Host "GRAPAI is running. Stop it now to update? [Y/n]"
    if ($a -ne "" -and $a -notmatch "^[yYjJ]") { Write-Host "Nothing changed."; Done 0 }
    $running | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

$dl = Join-Path $Root "downloads"
$src = Join-Path $dl "update-src"
New-Item -ItemType Directory -Force -Path $dl | Out-Null
if (Test-Path $src) { Remove-Item -Recurse -Force $src }
New-Item -ItemType Directory -Force -Path $src | Out-Null
$zip = Join-Path $dl "grapai-$short.zip"
& curl.exe -L --fail --silent --show-error --retry 5 -o $zip "https://codeload.github.com/$Repo/zip/$sha"
if ($LASTEXITCODE -ne 0) { Write-Host "Download failed (curl $LASTEXITCODE)." -ForegroundColor Red; Done 1 }
& tar.exe -xf $zip -C $src
if ($LASTEXITCODE -ne 0) { Write-Host "Unpacking failed." -ForegroundColor Red; Done 1 }
$code = Get-ChildItem -Directory $src | Select-Object -First 1
$installer = Join-Path $code.FullName "installer\install.ps1"
if (-not (Test-Path $installer)) { Write-Host "That version has no installer (branch '$UpdateBranch')." -ForegroundColor Red; Done 1 }

# Keep the choices of the first install: no video models if none are installed, same model set (from settings).
$argv = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $installer, "-InstallDir", $Root, "-Yes")
$video = Get-ChildItem -ErrorAction SilentlyContinue (Join-Path $Root "ComfyUI_windows_portable\ComfyUI\models\unet") -Filter "Wan2.2-*"
if (-not $video) { $argv += "-NoVideo" }
if ($ComfyProfile -eq "gpu12,laptop") { $argv += @("-Mode", "gpu12") } elseif ($ComfyProfile -eq "laptop") { $argv += @("-Mode", "8gb") }
& (Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe") @argv
$ok = $LASTEXITCODE -eq 0
Remove-Item -Recurse -Force $src, $zip -ErrorAction SilentlyContinue
if (-not $ok) { Write-Host "The update stopped. Run Update GRAPAI again to continue." -ForegroundColor Red; Done 1 }

Set-Content -Path $versionFile -Value "$sha $when $UpdateBranch"
Write-Host ""
Write-Host "GRAPAI is updated to $short ($when)." -ForegroundColor Green
$a = Read-Host "Start GRAPAI now? [Y/n]"
if ($a -eq "" -or $a -match "^[yYjJ]") {
    Start-Process -FilePath (Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe") `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$(Join-Path $Root 'Start-GRAPAI.ps1')`"")
}
exit 0
