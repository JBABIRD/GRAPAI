# Hybrid setup: laptop GPU + rented GPU

Fast mode runs on your own laptop for free, and quality mode plus video go to a cloud GPU that you start only when you need it. Ductus routes each job by mode, so on the board you only pick **Fast** or **Quality**.

| Tool | Fast mode on the laptop (8 GB) | Quality mode on the rented GPU |
|---|---|---|
| Create | Z-Image-Turbo GGUF Q5 | Qwen-Image-2512 |
| Render sketch, Edit, New view | FLUX.2 klein 4B fp8 (up to 2 references) | Qwen-Image-Edit-2511 |
| Animate | Wan 2.2 5B GGUF Q4, 832×480, up to 3 s (slow: expect 10 to 20 min) | Wan 2.2 14B, start and end frame |
| Cut out, Upscale | inside the Ductus API (CPU or GPU) | the same |

By default Animate is sent to the cloud GPU even in fast mode, because a laptop takes a long time. You can change that (see step 3).

> These graphs have not been benchmarked on an 8 GB card yet. Times are estimates. If a node or file name differs in your ComfyUI version, see [comfyui.md](comfyui.md) for how to swap in an exported workflow.

## 1. Laptop (Windows 11, RTX 4070 8 GB)

System RAM: 32 GB is comfortable. With 16 GB the image tools work, but local video may run out of memory.

1. Install **ComfyUI** for Windows (the portable NVIDIA build or ComfyUI Desktop) from https://github.com/comfyanonymous/ComfyUI. Update the NVIDIA driver first.
2. In ComfyUI Manager, install the custom node **ComfyUI-GGUF** (by city96) and restart.
3. Put these files into `ComfyUI\models\…`. Each name must match the graph in `backend/comfy_workflows/laptop/`; rename the file or edit the JSON if your download is named differently.

| Folder | File | Where to get it |
|---|---|---|
| `unet` | `z_image_turbo-Q5_K_M.gguf` | a GGUF build of Tongyi-MAI/Z-Image-Turbo on Hugging Face |
| `text_encoders` | `Qwen3-4B-Q4_K_M.gguf` | a GGUF build of Qwen3-4B |
| `vae` | `ae.safetensors` | Comfy-Org Z-Image-Turbo repackage |
| `diffusion_models` | `flux-2-klein-4b-fp8.safetensors` | FLUX.2 klein 4B (Apache-2.0), fp8 build |
| `text_encoders` | `qwen_3_4b.safetensors` | Comfy-Org FLUX.2 klein / Z-Image repackage |
| `vae` | `flux2-vae.safetensors` | Comfy-Org FLUX.2 repackage |
| `unet` | `Wan2.2-TI2V-5B-Q4_K_M.gguf` | a GGUF build of Wan-AI/Wan2.2-TI2V-5B (only if you want local video) |
| `text_encoders` | `umt5-xxl-encoder-Q4_K_M.gguf` | city96/umt5-xxl-encoder-gguf |
| `vae` | `wan2.2_vae.safetensors` | Comfy-Org Wan 2.2 repackage |

4. Start ComfyUI. The default `http://127.0.0.1:8188` is what Ductus expects. If you run out of memory, add `--lowvram` to the start command.

## 2. Rented GPU (only while you work)

1. Rent a GPU with **24 GB or more** (48 GB, such as an L40S or RTX 6000, runs the 14B video model comfortably) from a per-second provider such as RunPod or Vast.ai, using their ComfyUI template.
2. Download the files listed in [comfyui.md](comfyui.md) into its `models` folders.
3. Do **not** expose ComfyUI to the internet: it has no login. Connect through an SSH tunnel instead:

   ```powershell
   ssh -N -L 8189:127.0.0.1:8188 root@<pod-address> -p <ssh-port>
   ```

   The cloud ComfyUI is then reachable at `http://127.0.0.1:8189` on your laptop.
4. Stop the pod when you are done so billing stops.

## 3. Point Ductus at both

PowerShell, in `backend\`:

```powershell
$env:DUCTUS_PROVIDER = "comfy"
$env:DUCTUS_COMFY_URL = "http://127.0.0.1:8189"          # rented GPU (default for everything)
$env:DUCTUS_COMFY_URL_FAST = "http://127.0.0.1:8188"     # laptop ComfyUI for fast mode
$env:DUCTUS_COMFY_PROFILE_FAST = "laptop"                # use the lighter graphs there
$env:DUCTUS_COMFY_URL_ANIMATE = "http://127.0.0.1:8189"  # video always on the rented GPU
$env:DUCTUS_COMFY_PROFILE_ANIMATE = ""
uvicorn ductus.api:app --port 8000
```

To try local video, remove the two `ANIMATE` lines. To work offline with only the laptop, set `DUCTUS_COMFY_URL` to the laptop too and use **Fast** mode.

Routing rules, most specific first: `DUCTUS_COMFY_URL_<TOOL>_<MODE>`, `DUCTUS_COMFY_URL_<TOOL>`, `DUCTUS_COMFY_URL_<MODE>`, `DUCTUS_COMFY_URL`. Profiles (`DUCTUS_COMFY_PROFILE_*`) resolve the same way. Tool names are `create`, `render`, `edit`, `new_view` and `animate`.
