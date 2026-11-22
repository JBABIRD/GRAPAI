<#
  GRAPAI (Ductus) one-click installer for Windows 10/11 with an NVIDIA GPU (8 GB VRAM or more).

  Per-user only, no admin rights: everything goes to %LOCALAPPDATA%\GRAPAI (or -InstallDir), with
  portable ComfyUI (its own embedded Python), a portable Node.js used only to build the web app,
  and shortcuts in the user's own Desktop and Start menu folders. Nothing is written to Program Files,
  HKLM, PATH or services, and nothing asks for UAC.

  Run it again at any time: finished steps are skipped, the app code is updated, and every model file
  is re-checked against its SHA-256.

  Options:
    -InstallDir <path>   install somewhere else (must be a folder you can write to)
    -NoVideo             skip the local video model (about 8 GB less to download)
    -SkipModels          install the app only (models are copied in by hand)
    -NoShortcuts         do not create Desktop / Start menu shortcuts
    -Yes                 do not ask questions (accept warnings, do not start the app at the end)
#>
[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "GRAPAI"),
    [switch]$NoVideo,
    [switch]$SkipModels,
    [switch]$NoShortcuts,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest / Expand-Archive are 10x slower with the progress bar
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Manifest = Get-Content -Raw -Path (Join-Path $PSScriptRoot "manifest.json") | ConvertFrom-Json

$Tools     = Join-Path $InstallDir "tools"
$Downloads = Join-Path $InstallDir "downloads"
$Logs      = Join-Path $InstallDir "logs"
$App       = Join-Path $InstallDir "app"
$Comfy     = Join-Path $InstallDir "ComfyUI_windows_portable"
$Py        = Join-Path $Comfy "python_embeded\python.exe"
$NodeDir   = Join-Path $Tools "node"

function Say([string]$text, [string]$color = "Gray") { Write-Host $text -ForegroundColor $color }
function Step([string]$text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Fail([string]$text) { Write-Host ""; Write-Host "ERROR: $text" -ForegroundColor Red; throw $text }
function Ask([string]$question) {
    if ($Yes) { return $true }
    $a = Read-Host "$question [Y/n]"
    return ($a -eq "" -or $a -match "^[yYjJ]")
}

function Run([string]$exe, [string[]]$argv, [string]$what) {
    & $exe @argv
    if ($LASTEXITCODE -ne 0) { Fail "$what failed (exit code $LASTEXITCODE). See the log in $Logs." }
}

function Test-Sha256([string]$path, [string]$sha256) {
    if (-not $sha256) { return $true }
    $marker = "$path.sha256-ok"
    $item = Get-Item $path
    $stamp = "$($item.Length)|$($item.LastWriteTimeUtc.Ticks)|$sha256"
    if ((Test-Path $marker) -and ((Get-Content -Raw $marker).Trim() -eq $stamp)) { return $true }
    Say "    checking SHA-256 of $($item.Name) ..."
    $actual = (Get-FileHash -Algorithm SHA256 -Path $path).Hash.ToLower()
    if ($actual -ne $sha256.ToLower()) { return $false }
    Set-Content -Path $marker -Value $stamp -NoNewline
    return $true
}

# Downloads go in 128 MB ranged chunks, each size-checked and retried, then the whole file is checked against
# its SHA-256. Tested on the reference laptop: plain resumed downloads from Hugging Face came back corrupted
# (right size, wrong hash: the model then produced pure noise), and hf_hub_download stalled.
$ChunkSize = 128MB
function Get-Chunk([string]$url, [string]$out, [long]$from, [long]$to) {
    for ($try = 1; $try -le 8; $try++) {
        & curl.exe -L --fail --silent --show-error --connect-timeout 30 --speed-limit 200000 --speed-time 20 `
            -r "$from-$to" -o $out $url
        if ($LASTEXITCODE -eq 0 -and (Test-Path $out) -and ((Get-Item $out).Length -eq ($to - $from + 1))) { return }
        Start-Sleep -Seconds ([math]::Min(60, 3 * $try))
    }
    Fail "Download keeps failing: $url (bytes $from-$to). Check the internet connection and run the installer again."
}

function Get-File([string]$url, [string]$dest, [string]$sha256 = "", [long]$size = 0) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
    $name = Split-Path -Leaf $dest
    if ((Test-Path $dest) -and (($size -le 0) -or ((Get-Item $dest).Length -eq $size)) -and (Test-Sha256 $dest $sha256)) { Say "    $name ok"; return }
    if (Test-Path $dest) { Say "    $name is incomplete or damaged, downloading it again" "Yellow"; Remove-Item -Force $dest }
    $part = "$dest.part"; $chunk = "$dest.chunk"
    for ($attempt = 1; $attempt -le 2; $attempt++) {
        if ($size -le 0) {
            Say "    downloading $name"
            & curl.exe -L --fail --silent --show-error --retry 5 --retry-delay 5 -o $part $url
            if ($LASTEXITCODE -ne 0) { Remove-Item -Force $part -ErrorAction SilentlyContinue; continue }
        } else {
            # Resume from the last whole chunk of an earlier run.
            $have = 0
            if (Test-Path $part) { $have = (Get-Item $part).Length }
            $have = [long]([math]::Floor($have / $ChunkSize)) * $ChunkSize
            $fs = [IO.File]::Open($part, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::Write)
            try {
                $fs.SetLength($have); $fs.Position = $have
                for ($from = $have; $from -lt $size; $from += $ChunkSize) {
                    $to = [math]::Min($from + $ChunkSize, $size) - 1
                    Write-Host ("`r    downloading {0}: {1:N1} of {2:N1} GB   " -f $name, ($from / 1GB), ($size / 1GB)) -NoNewline
                    Get-Chunk $url $chunk $from $to
                    $bytes = [IO.File]::ReadAllBytes($chunk)
                    $fs.Write($bytes, 0, $bytes.Length); $fs.Flush()
                }
                Write-Host ("`r    downloaded {0}: {1:N1} GB                    " -f $name, ($size / 1GB))
            } finally { $fs.Close(); Remove-Item -Force $chunk -ErrorAction SilentlyContinue }
        }
        Move-Item -Force $part $dest
        if (Test-Sha256 $dest $sha256) { return }
        Say "    $name failed its SHA-256 check, downloading it again from scratch" "Yellow"
        Remove-Item -Force $dest
    }
    Fail "Could not download $name from $url"
}

New-Item -ItemType Directory -Force -Path $InstallDir, $Tools, $Downloads, $Logs | Out-Null
Start-Transcript -Path (Join-Path $Logs ("install-{0:yyyyMMdd-HHmmss}.log" -f (Get-Date))) | Out-Null

try {
    Say ""
    Say "GRAPAI installer" "White"
    Say "Installing for $env:USERNAME into $InstallDir (no admin rights needed)."

    # ---------------------------------------------------------------- checks
    Step "Checking this computer"
    if (-not [Environment]::Is64BitOperatingSystem) { Fail "GRAPAI needs 64-bit Windows." }
    if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) { Fail "curl.exe is missing. Windows 10 (1803 or newer) or Windows 11 is needed." }
    if (-not (Get-Command tar.exe -ErrorAction SilentlyContinue)) { Fail "tar.exe is missing. Windows 10 (1803 or newer) or Windows 11 is needed." }

    $smi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
    if (-not $smi) {
        Fail "No NVIDIA driver found (nvidia-smi). Install the latest NVIDIA driver (it does not need this installer to run as admin), then run this again."
    }
    $gpu = (& nvidia-smi.exe --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits | Select-Object -First 1).Split(",") | ForEach-Object { $_.Trim() }
    $vramGb = [math]::Round([double]$gpu[1] / 1024, 1)
    Say "    GPU: $($gpu[0]), $vramGb GB VRAM, driver $($gpu[2])"
    if ([double]$gpu[1] -lt 7800) {
        Say "    GRAPAI is tuned for 8 GB of VRAM or more. With less, tools may run out of memory." "Yellow"
        if (-not (Ask "Continue anyway?")) { Fail "Stopped by the user." }
    }
    if ([double]$gpu[2] -lt [double]$Manifest.min_driver) {
        Say "    Your NVIDIA driver is older than $($Manifest.min_driver). Please update it from nvidia.com (no admin rights are needed for this installer, but the driver update itself may ask)." "Yellow"
        if (-not (Ask "Continue anyway?")) { Fail "Stopped by the user." }
    }
    $ramGb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
    Say "    RAM: $ramGb GB"
    if ($ramGb -lt 16) { Say "    16 GB of RAM or more is recommended; 32 GB for video." "Yellow" }

    $models = @($Manifest.models | Where-Object { -not ($NoVideo -and $_.group -eq "video") })
    $needGb = 12
    if (-not $SkipModels) { $needGb += [math]::Ceiling((($models | Measure-Object -Property size -Sum).Sum) / 1GB) }
    $drive = Get-PSDrive -Name ((Resolve-Path $InstallDir).Path.Substring(0, 1))
    $freeGb = [math]::Floor($drive.Free / 1GB)
    Say "    Free space on drive $($drive.Name): $freeGb GB (needs about $needGb GB, less if this is an update)"
    if ($freeGb -lt $needGb) {
        Say "    There may not be enough free space." "Yellow"
        if (-not (Ask "Continue anyway?")) { Fail "Stopped by the user." }
    }

    # ---------------------------------------------------------------- ComfyUI (portable, own Python)
    Step "ComfyUI $($Manifest.comfyui.version) (portable, with its own Python)"
    if (Test-Path $Py) {
        Say "    already installed"
    } else {
        $archive = Join-Path $Downloads $Manifest.comfyui.asset
        Get-File $Manifest.comfyui.url $archive $Manifest.comfyui.sha256 $Manifest.comfyui.size
        $tmp = Join-Path $InstallDir "comfy-unpack"
        if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
        New-Item -ItemType Directory -Force -Path $tmp | Out-Null
        Run tar.exe @("-xf", $archive, "-C", $tmp) "Unpacking ComfyUI"   # Windows tar (bsdtar) reads .7z
        $inner = Get-ChildItem -Directory $tmp | Select-Object -First 1
        if (Test-Path $Comfy) { Remove-Item -Recurse -Force $Comfy }
        Move-Item $inner.FullName $Comfy
        Remove-Item -Recurse -Force $tmp
        Remove-Item -Force $archive
    }

    Step "ComfyUI-GGUF node (loads the small GGUF models)"
    $ggufDir = Join-Path $Comfy "ComfyUI\custom_nodes\ComfyUI-GGUF"
    $ggufStamp = Join-Path $ggufDir ".grapai-commit"
    if ((Test-Path $ggufStamp) -and ((Get-Content -Raw $ggufStamp).Trim() -eq $Manifest.gguf_node.commit)) {
        Say "    already installed"
    } else {
        $zip = Join-Path $Downloads "ComfyUI-GGUF.zip"
        Get-File $Manifest.gguf_node.url $zip $Manifest.gguf_node.sha256
        $tmp = Join-Path $Downloads "gguf-unpack"
        if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
        New-Item -ItemType Directory -Force -Path $tmp | Out-Null
        Run tar.exe @("-xf", $zip, "-C", $tmp) "Unpacking ComfyUI-GGUF"
        if (Test-Path $ggufDir) { Remove-Item -Recurse -Force $ggufDir }
        Move-Item (Get-ChildItem -Directory $tmp | Select-Object -First 1).FullName $ggufDir
        Remove-Item -Recurse -Force $tmp, $zip
        Run $Py @("-s", "-m", "pip", "install", "--no-warn-script-location", "-r", (Join-Path $ggufDir "requirements.txt")) "Installing ComfyUI-GGUF requirements"
        Set-Content -Path $ggufStamp -Value $Manifest.gguf_node.commit -NoNewline
    }

    # ---------------------------------------------------------------- app code
    Step "GRAPAI app code"
    if (-not (Test-Path (Join-Path $RepoRoot "backend\ductus"))) { Fail "Run Install-GRAPAI.cmd from inside the unpacked GRAPAI folder." }
    foreach ($part in @("backend", "frontend", "installer")) {
        $null = & robocopy.exe (Join-Path $RepoRoot $part) (Join-Path $App $part) /MIR /NFL /NDL /NJH /NJS /NP `
            /XD node_modules dist data __pycache__ .venv venv .pytest_cache /XF *.pyc *.tsbuildinfo
        if ($LASTEXITCODE -ge 8) { Fail "Copying the app code failed (robocopy $LASTEXITCODE)." }
    }
    $global:LASTEXITCODE = 0

    Step "Python packages for the GRAPAI server (into ComfyUI's own Python)"
    # ComfyUI's Python already has torch with CUDA, transformers, spandrel, kornia and einops; this adds the
    # web server and the few extras without touching torch.
    Run $Py @("-s", "-m", "pip", "install", "--no-warn-script-location", "--upgrade-strategy", "only-if-needed",
              "-e", ((Join-Path $App "backend") + "[local]")) "Installing the GRAPAI server packages"

    Step "Building the web app (portable Node.js $($Manifest.node.version), used only for this build)"
    if (-not (Test-Path (Join-Path $NodeDir "node.exe"))) {
        $zip = Join-Path $Downloads $Manifest.node.asset
        Get-File $Manifest.node.url $zip $Manifest.node.sha256
        Run tar.exe @("-xf", $zip, "-C", $Tools) "Unpacking Node.js"
        if (Test-Path $NodeDir) { Remove-Item -Recurse -Force $NodeDir }
        Rename-Item (Join-Path $Tools ($Manifest.node.asset -replace "\.zip$", "")) "node"
        Remove-Item -Force $zip
    }
    $env:Path = "$NodeDir;$env:Path"
    $env:npm_config_cache = Join-Path $Tools "npm-cache"
    $env:npm_config_update_notifier = "false"
    Push-Location (Join-Path $App "frontend")
    try {
        Run (Join-Path $NodeDir "npm.cmd") @("ci", "--no-audit", "--no-fund", "--loglevel=error") "npm ci"
        Run (Join-Path $NodeDir "npm.cmd") @("run", "build") "Building the web app"
    } finally { Pop-Location }

    # ---------------------------------------------------------------- models
    if ($SkipModels) {
        Step "Models skipped (-SkipModels)"
    } else {
        $total = ($models | Measure-Object -Property size -Sum).Sum
        Step ("Models ({0} files, {1:N1} GB; a first install takes a while)" -f $models.Count, ($total / 1GB))
        foreach ($m in $models) {
            $dest = Join-Path $Comfy ("ComfyUI\models\{0}\{1}" -f $m.folder, $m.file)
            Get-File $m.url $dest $m.sha256 ([long]$m.size)
        }
    }

    Step "Background removal (BiRefNet) and upscaler (Real-ESRGAN) weights"
    foreach ($f in $Manifest.birefnet.files) {
        $size = 0; if ($f.size) { $size = [long]$f.size }
        Get-File $f.url (Join-Path $InstallDir ("data\{0}\{1}" -f $Manifest.birefnet.folder, $f.file)) $f.sha256 $size
    }
    $esrgan = Join-Path $InstallDir ("data\models\" + (Split-Path -Leaf $Manifest.esrgan.url))
    Get-File $Manifest.esrgan.url $esrgan $Manifest.esrgan.sha256 ([long]$Manifest.esrgan.size)

    # ---------------------------------------------------------------- launcher and shortcuts
    Step "Launcher and shortcuts"
    Copy-Item -Force (Join-Path $PSScriptRoot "start.ps1") (Join-Path $InstallDir "Start-GRAPAI.ps1")
    Copy-Item -Force (Join-Path $PSScriptRoot "uninstall.ps1") (Join-Path $InstallDir "Uninstall-GRAPAI.ps1")
    $settingsFile = Join-Path $InstallDir "settings.ps1"
    if (-not (Test-Path $settingsFile)) {
        @"
# GRAPAI settings. The installer keeps this file when it updates GRAPAI.
`$GrapaiPort = 8000
`$ComfyPort = 8188
# Set to 1 if ComfyUI runs out of GPU memory (slower, but needs less VRAM). 8 GB works without it.
`$LowVram = 0
"@ | Set-Content -Path $settingsFile
    }
    $GrapaiPort = 8000
    . $settingsFile

    if (-not $NoShortcuts) {
        $shell = New-Object -ComObject WScript.Shell
        $ps = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
        $icon = Join-Path $App "installer\grapai.ico"
        $targets = @(
            @{ Path = (Join-Path ([Environment]::GetFolderPath("Desktop")) "GRAPAI.lnk"); Script = "Start-GRAPAI.ps1"; Desc = "Start GRAPAI" },
            @{ Path = (Join-Path ([Environment]::GetFolderPath("Programs")) "GRAPAI\GRAPAI.lnk"); Script = "Start-GRAPAI.ps1"; Desc = "Start GRAPAI" },
            @{ Path = (Join-Path ([Environment]::GetFolderPath("Programs")) "GRAPAI\Uninstall GRAPAI.lnk"); Script = "Uninstall-GRAPAI.ps1"; Desc = "Remove GRAPAI" }
        )
        foreach ($t in $targets) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $t.Path) | Out-Null
            $lnk = $shell.CreateShortcut($t.Path)
            $lnk.TargetPath = $ps
            $lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $InstallDir $t.Script)`""
            $lnk.WorkingDirectory = $InstallDir
            $lnk.Description = $t.Desc
            if (Test-Path $icon) { $lnk.IconLocation = $icon }
            $lnk.Save()
        }
        Say "    Desktop: GRAPAI    Start menu: GRAPAI"
    }

    if (Test-Path $Downloads) { Remove-Item -Recurse -Force $Downloads -ErrorAction SilentlyContinue }

    Step "Done"
    Say "GRAPAI is installed in $InstallDir." "Green"
    if ($NoShortcuts) { Say "Start it with $(Join-Path $InstallDir 'Start-GRAPAI.ps1')." }
    else { Say "Start it with the GRAPAI shortcut on your Desktop or in the Start menu." }
    Say "It opens in your browser at http://localhost:$GrapaiPort."
    if (-not $Yes -and (Ask "Start GRAPAI now?")) {
        Start-Process -FilePath (Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe") `
            -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$(Join-Path $InstallDir 'Start-GRAPAI.ps1')`"")
    }
} catch {
    Say ""
    Say "The installation stopped: $($_.Exception.Message)" "Red"
    Say "Run Install-GRAPAI.cmd again to continue where it stopped. Log: $Logs" "Red"
    exit 1
} finally {
    Stop-Transcript | Out-Null
}
