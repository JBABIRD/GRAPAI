# Running the models with ComfyUI

Ductus sends each AI tool to a ComfyUI server as an API-format graph from `backend/comfy_workflows/`. Values like `{{prompt}}` are filled in per run. A node whose placeholder has no value (an optional reference image) is removed together with the links that used it.

> These graphs follow ComfyUI's built-in node set and the official example workflows, but they have not yet been run against a live GPU in this repository. If a node or file name differs in your ComfyUI version, open the official template in ComfyUI, export it with **Export (API)**, put the placeholders back in and save it over the JSON file.

## 1. Install ComfyUI

Follow https://github.com/comfyanonymous/ComfyUI (a recent version: Qwen-Image-Edit, Z-Image and Wan 2.2 nodes are built in). Start it with `--listen` so Ductus can reach it.

## 2. Download the model files

Put the files in ComfyUI's `models/` folders. The Comfy-Org repackaged files on Hugging Face use these names; each template's `_meta.files` lists what it needs.

| Tool | Folder | File |
|---|---|---|
| Create, fast | diffusion_models | `z_image_turbo_bf16.safetensors` |
| | text_encoders | `qwen_3_4b.safetensors` |
| | vae | `ae.safetensors` |
| Create, quality | diffusion_models | `qwen_image_2512_fp8_e4m3fn.safetensors` |
| Create quality, Edit, Render, New view | text_encoders | `qwen_2.5_vl_7b_fp8_scaled.safetensors` |
| | vae | `qwen_image_vae.safetensors` |
| Edit, Render, New view | diffusion_models | `qwen_image_edit_2511_bf16.safetensors` |
| Fast mode | loras | `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors` |
| Animate, fast | diffusion_models | `wan2.2_ti2v_5B_fp16.safetensors` |
| | vae | `wan2.2_vae.safetensors` |
| Animate (both) | text_encoders | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` |
| Animate, quality / key frames | diffusion_models | `wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors`, `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors` |
| | vae | `wan_2.1_vae.safetensors` |

Background removal (BiRefNet) and upscaling (Real-ESRGAN) run inside the Ductus API (`pip install -e ".[local]"`) and download their weights on first use.

## 3. GPU sizing

| GPU | What runs well |
|---|---|
| 24 GB (RTX 4090/5090) | All image tools (fp8), Wan 2.2 5B. ComfyUI swaps models, so the first run of each tool is slower |
| 48 GB (L40S, RTX 6000) | Everything above at full speed, Wan 2.2 A14B key frames |
| 80 GB (A100/H100) | Everything warm at once, faster video |

## 4. Point Ductus at it

```bash
export DUCTUS_PROVIDER=comfy
export DUCTUS_COMFY_URL=http://<gpu-host>:8188
uvicorn ductus.api:app --port 8000
```
