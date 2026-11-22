# Install GRAPAI on a Windows laptop (one click, no admin rights)

## What you need

- Windows 10 (1803 or newer) or Windows 11, 64-bit
- An NVIDIA GPU with **8 GB of VRAM or more** and a recent NVIDIA driver (570 or newer)
- 16 GB of RAM (32 GB if you want to make videos)
- About **45 GB of free disk space** (about 38 GB without video)
- A good internet connection: the first install downloads about 33 GB

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

Shortcuts: `GRAPAI` on the Desktop, and a `GRAPAI` folder in the Start menu with **Uninstall GRAPAI**.

## Options

Run the installer from a PowerShell window in the unpacked folder for these:

```powershell
.\Install-GRAPAI.cmd -NoVideo                  # skip the video model (about 8 GB less)
.\Install-GRAPAI.cmd -InstallDir D:\GRAPAI     # install on another drive
.\Install-GRAPAI.cmd -SkipModels               # app only, copy the models in yourself
```

## Update

Download the newer GRAPAI zip, unpack it, and run `Install-GRAPAI.cmd` again. It updates the app, keeps your boards, and only downloads models that changed. Every model file is checked against its SHA-256 checksum.

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
| Cut out | BiRefNet |
| Upscale | Real-ESRGAN x4plus |
