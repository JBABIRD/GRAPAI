# Install GRAPAI on a Windows laptop (one click, no admin rights)

## What you need

- Windows 10 (1803 or newer) or Windows 11, 64-bit
- An NVIDIA GPU with **8 GB of VRAM or more** and a recent NVIDIA driver (570 or newer). With **12 GB or more**, the installer picks the 12 GB mode by itself (see below)
- 16 GB of RAM (32 GB if you want to make videos)
- About **45 GB of free disk space** in 8 GB mode, about **55 GB** in 12 GB mode (less without video)
- A good internet connection: the first install downloads about 39 GB (8 GB mode) or 47 GB (12 GB mode)

You do **not** need admin rights, Python, Node.js or Git. Nothing is installed system-wide.

## Install

1. Get the GRAPAI folder: on GitHub, **Code → Download ZIP**, or a zip someone sends you. Unpack it anywhere (right-click → **Extract All**).
2. Double-click **`Install-GRAPAI.cmd`** in the unpacked folder.
   - If Windows shows "Windows protected your PC", click **More info → Run anyway**. That is SmartScreen, not an admin prompt.
3. Wait. The installer checks your GPU, then downloads and sets up everything. The first run takes from about 30 minutes to a few hours, depending on your connection. If it stops (connection lost, laptop asleep), just double-click it again: it continues where it stopped.
4. At the end it asks whether to start GRAPAI.

## Use

- Double-click **GRAPAI** on your Desktop (or in the Start menu). A window opens, and after about half a minute the board opens in your browser at http://localhost:8000.
- Keep that window open while you work. Close it to stop GRAPAI and free the GPU.
- Everything stays on your computer: the servers only listen on this computer (127.0.0.1), and your boards are saved in the install folder.

## Where things go

Everything is in `%LOCALAPPDATA%\GRAPAI` (for example `C:\Users\you\AppData\Local\GRAPAI`):

| Folder | What |
|---|---|
| `ComfyUI_windows_portable` | ComfyUI with its own Python, and the AI models (`ComfyUI\models`) |
| `app` | the GRAPAI server and web app |
| `data` | your boards and images, plus the background-removal and upscaler weights |
| `tools` | a portable Node.js, only used to build the web app |
| `logs` | install and run logs, for when something goes wrong |

Shortcuts: `GRAPAI` on the Desktop, and a `GRAPAI` folder in the Start menu with **Update GRAPAI** and **Uninstall GRAPAI**.

The GRAPAI server runs in ComfyUI's own Python (it reuses ComfyUI's GPU build of PyTorch, which saves a 3 GB download). The installer pins ComfyUI to a tested version, so do not update ComfyUI from its own updater: run a newer GRAPAI installer instead.

## 8 GB and 12 GB modes

The installer reads your GPU's memory and picks the model set:

| | 8 GB mode | 12 GB mode (about 12 GB or more) |
|---|---|---|
| Create | Z-Image-Turbo GGUF Q5, Qwen3-4B Q4 text encoder | Z-Image-Turbo GGUF **Q8**, Qwen3-4B **Q8**: cleaner detail and text |
| Edit, Render, New view, Erase, Extend, Style, Views, Environment | FLUX.2 klein 4B at about 1 MP | the same model at about **1.5 MP**: sharper Edit, Render, New view and Style (finer detail, legible logos); Erase, Extend and Environment look about the same |
| Animate | Wan 2.2 5B GGUF Q4, 832x480 | Wan 2.2 5B GGUF **Q8**, **1280x704 (720p)** |

Both modes use only commercially usable licences. The bigger models (Qwen-Image-Edit 20B, Wan 2.2 14B) need 24 GB or more and are not part of either mode. To force a mode, run the installer with `-Mode 8gb` or `-Mode gpu12`.

## Options

Run the installer from a PowerShell window in the unpacked folder for these:

```powershell
.\Install-GRAPAI.cmd -NoVideo                  # skip the video model (about 8 to 13 GB less)
.\Install-GRAPAI.cmd -InstallDir D:\GRAPAI     # install on another drive
.\Install-GRAPAI.cmd -SkipModels               # app only, copy the models in yourself
```

## Update

Click **Update GRAPAI** in the Start menu (GRAPAI folder). It checks GitHub for the newest version, stops GRAPAI if it is running, and installs the new version over the old one. No admin rights are needed. Your boards, `settings.ps1` and models stay; only models that are new or changed are downloaded, and every model is checked against its SHA-256 checksum. ComfyUI-GGUF is pinned to a Git commit instead, because GitHub's source zips have no fixed checksum.

When GRAPAI starts, its window says when an update is available. The first update after installing from a zip always runs once, because the zip does not say which version it was.

Updates follow the `main` branch. To follow another branch, change `$UpdateBranch` in `settings.ps1`.

You can also run it from PowerShell: `& "$env:LOCALAPPDATA\GRAPAI\Update-GRAPAI.ps1"` (add `-Check` to only check, `-Force` to reinstall the same version).

## If something goes wrong

- **"No NVIDIA driver found"**: install the latest driver from nvidia.com, then run the installer again.
- **A tool runs out of GPU memory**: close other GPU apps (Blender, Alias, games). If it still happens, open `settings.ps1` in the install folder and set `$LowVram = 1`.
- **Port 8000 is already in use**: change `$GrapaiPort` in `settings.ps1`.
- **Something else**: look at the newest file in the `logs` folder.

## Models

All models allow commercial use (Apache-2.0; BiRefNet is MIT, Real-ESRGAN is BSD-3). The exact files, versions and checksums are in [`installer/manifest.json`](../installer/manifest.json).

| Tool | Model |
|---|---|
| Create | Z-Image-Turbo (GGUF Q5) |
| Render, Edit, New view, Erase, Extend, Style, Views, Environment | FLUX.2 klein 4B (fp8); Quality mode for Erase and Extend uses klein Base 4B |
| Animate | Wan 2.2 TI2V 5B (GGUF Q4) |
| Extend (outpaint) | FLUX.2 klein 4B with the fal outpaint LoRA (Apache-2.0) |
| Style transfer (reading the reference) | Qwen3-VL 2B Instruct (Apache-2.0) |
| Cut out | BiRefNet |
| Upscale | Real-ESRGAN x4plus |
