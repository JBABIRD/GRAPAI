<#
  Starts GRAPAI: ComfyUI (the AI models) and the GRAPAI server, then opens the board in your browser.
  Both run inside this window. Close the window to stop GRAPAI. Logs are in the logs folder.
#>
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$GrapaiPort = 8000; $ComfyPort = 8188; $LowVram = 0; $ComfyProfile = "laptop"; $UpdateBranch = ""
$settings = Join-Path $Root "settings.ps1"
if (Test-Path $settings) { . $settings }

$Host.UI.RawUI.WindowTitle = "GRAPAI (close this window to stop)"
$Py = Join-Path $Root "ComfyUI_windows_portable\python_embeded\python.exe"
$Logs = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $Logs, (Join-Path $Root "data") | Out-Null
$url = "http://localhost:$GrapaiPort"

function Test-Up([string]$u) {
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 -Uri $u | Out-Null; return $true } catch { return $false }
}
function Wait-Up([string]$u, [int]$seconds, $proc, [string]$name, [string]$log) {
    for ($i = 0; $i -lt $seconds; $i += 2) {
        if (Test-Up $u) { return }
        if ($proc -and $proc.HasExited) {
            Write-Host "$name stopped while starting. Last lines of $log :" -ForegroundColor Red
            Get-Content -Tail 30 $log -ErrorAction SilentlyContinue
            Read-Host "Press Enter to close"; exit 1
        }
        Start-Sleep -Seconds 2
    }
    Write-Host "$name did not start within $seconds s. See $log" -ForegroundColor Red
    Read-Host "Press Enter to close"; exit 1
}

if (Test-Up "$url/api/health") {
    Write-Host "GRAPAI is already running. Opening $url"
    Start-Process $url; Start-Sleep -Seconds 2; exit 0
}

$procs = @()
try {
    # ComfyUI: loopback only (it has no login), its own Python, logs to a file.
    if (-not (Test-Up "http://127.0.0.1:$ComfyPort/system_stats")) {
        Write-Host "Starting ComfyUI (AI models) ..."
        $comfyArgs = @("-s", "ComfyUI\main.py", "--windows-standalone-build", "--listen", "127.0.0.1", "--port", "$ComfyPort", "--disable-auto-launch")
        if ($LowVram -eq 1) { $comfyArgs += "--lowvram" }
        $comfyLog = Join-Path $Logs "comfyui.log"
        $comfy = Start-Process -FilePath $Py -ArgumentList $comfyArgs -WorkingDirectory (Join-Path $Root "ComfyUI_windows_portable") `
            -NoNewWindow -PassThru -RedirectStandardOutput $comfyLog -RedirectStandardError "$comfyLog.err"
        $procs += $comfy
        Wait-Up "http://127.0.0.1:$ComfyPort/system_stats" 240 $comfy "ComfyUI" "$comfyLog.err"
    }

    Write-Host "Starting the GRAPAI server ..."
    $env:DUCTUS_PROVIDER = "comfy"
    $env:DUCTUS_COMFY_URL = "http://127.0.0.1:$ComfyPort"
    $env:DUCTUS_COMFY_PROFILE = $ComfyProfile
    $env:DUCTUS_DATA_DIR = Join-Path $Root "data"
    $env:DUCTUS_WEB_DIR = Join-Path $Root "app\frontend\dist"
    $env:HF_HUB_DISABLE_TELEMETRY = "1"
    $env:HF_HOME = Join-Path $Root "hf"
    # BiRefNet from the pinned local copy the installer downloaded (no network needed at run time).
    $bg = Join-Path $Root "data\models\BiRefNet"
    if (Test-Path (Join-Path $bg "model.safetensors")) { $env:DUCTUS_BG_MODEL = $bg }
    $vlm = Join-Path $Root "data\models\Qwen3-VL-2B-Instruct"
    if (Test-Path (Join-Path $vlm "model.safetensors")) { $env:DUCTUS_STYLE_VLM = $vlm }
    $apiLog = Join-Path $Logs "grapai.log"
    $api = Start-Process -FilePath $Py -ArgumentList @("-s", "-m", "uvicorn", "ductus.api:app", "--app-dir", "app\backend", "--host", "127.0.0.1", "--port", "$GrapaiPort") `
        -WorkingDirectory $Root -NoNewWindow -PassThru -RedirectStandardOutput $apiLog -RedirectStandardError "$apiLog.err"
    $procs += $api
    Wait-Up "$url/api/health" 120 $api "The GRAPAI server" "$apiLog.err"

    Write-Host ""
    Write-Host "GRAPAI is running at $url" -ForegroundColor Green
    Write-Host "Keep this window open while you work. Close it (or press Ctrl+C) to stop GRAPAI."
    Start-Process $url
    # Quietly say when a newer version is on GitHub (never blocks the start).
    try {
        $vf = Join-Path $Root "version.txt"
        $mf = Get-Content -Raw (Join-Path $Root "app\installer\manifest.json") | ConvertFrom-Json
        $branch = if ($UpdateBranch) { $UpdateBranch } else { $mf.update.branch }
        $latest = Invoke-RestMethod -UseBasicParsing -TimeoutSec 4 -Headers @{ "User-Agent" = "GRAPAI-updater" } `
            -Uri "https://api.github.com/repos/$($mf.update.repo)/commits/$branch"
        $have = if (Test-Path $vf) { (Get-Content -Raw $vf).Trim().Split(" ")[0] } else { "" }
        if ($latest.sha -and $latest.sha -ne $have) {
            Write-Host "An update is available. Close this window and run 'Update GRAPAI' from the Start menu." -ForegroundColor Yellow
        }
    } catch { }
    while ($true) {
        foreach ($p in $procs) {
            if ($p.HasExited) { Write-Host "A GRAPAI process stopped (exit $($p.ExitCode)). See $Logs" -ForegroundColor Red; Read-Host "Press Enter to close"; exit 1 }
        }
        Start-Sleep -Seconds 3
    }
} finally {
    foreach ($p in $procs) { if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } }
}
