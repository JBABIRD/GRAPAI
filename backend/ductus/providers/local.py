"""Small open models run in-process with torch (CPU works, a GPU is faster)."""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
from PIL import Image

from ..config import settings
from .base import JobInput, Output, Provider


def _device():
    import torch

    if settings.device.startswith("cuda") and torch.cuda.is_available():
        return torch.device(settings.device)
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


class BiRefNetRemoveBg(Provider):
    """BiRefNet (MIT) dichotomous segmentation for clean product cut-outs."""

    workflow, backend = "remove_bg", "local"
    _lock = threading.Lock()
    _model = None

    @property
    def model(self) -> str:  # type: ignore[override]
        return settings.bg_model

    def _load(self):
        with self._lock:
            if BiRefNetRemoveBg._model is None:
                from transformers import AutoModelForImageSegmentation

                m = AutoModelForImageSegmentation.from_pretrained(settings.bg_model, trust_remote_code=True)
                dev = _device()
                # Recent transformers keeps the checkpoint's fp16 weights; CPU needs fp32.
                if dev.type == "cpu":
                    m = m.float()
                m.to(dev).eval()
                BiRefNetRemoveBg._model = m
        return BiRefNetRemoveBg._model

    def run(self, job: JobInput) -> list[Output]:
        import torch
        from torchvision import transforms

        model = self._load()
        src = job.images["image"].convert("RGB")
        tf = transforms.Compose([
            transforms.Resize((1024, 1024)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        p = next(model.parameters())
        x = tf(src).unsqueeze(0).to(device=p.device, dtype=p.dtype)
        job.progress(0.3, "segmenting")
        with torch.no_grad():
            pred = model(x)[-1].sigmoid().float().cpu()[0].squeeze()
        alpha = transforms.functional.to_pil_image(pred).resize(src.size, Image.LANCZOS)
        out = src.copy()
        out.putalpha(alpha)
        return [Output(image=out)]


class ESRGANUpscale(Provider):
    """Real-ESRGAN x4plus (BSD-3) through spandrel; 2x is a 4x pass downsampled."""

    workflow, backend, model = "upscale", "local", "Real-ESRGAN x4plus"
    _lock = threading.Lock()
    _net = None

    def _load(self):
        with self._lock:
            if ESRGANUpscale._net is None:
                import torch
                from spandrel import ModelLoader

                weights = Path(settings.data_dir) / "models" / Path(settings.upscale_weights).name
                if not weights.exists():
                    weights.parent.mkdir(parents=True, exist_ok=True)
                    torch.hub.download_url_to_file(settings.upscale_weights, str(weights))
                net = ModelLoader().load_from_file(str(weights))
                net.to(_device()).eval()
                ESRGANUpscale._net = net
        return ESRGANUpscale._net

    def run(self, job: JobInput) -> list[Output]:
        import torch

        net = self._load()
        src = job.images["image"]
        alpha = src.split()[3] if src.mode == "RGBA" else None
        rgb = np.asarray(src.convert("RGB"), dtype=np.float32) / 255.0
        device = next(net.model.parameters()).device
        x = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).to(device)
        tile = 512
        _, _, h, w = x.shape
        out = torch.zeros((1, 3, h * 4, w * 4))
        tiles = [(ty, tx) for ty in range(0, h, tile) for tx in range(0, w, tile)]
        with torch.no_grad():
            for i, (ty, tx) in enumerate(tiles):
                job.progress(i / len(tiles), f"tile {i + 1}/{len(tiles)}")
                pad = 16
                y0, x0 = max(0, ty - pad), max(0, tx - pad)
                y1, x1 = min(h, ty + tile + pad), min(w, tx + tile + pad)
                res = net(x[:, :, y0:y1, x0:x1]).cpu()
                oy, ox = (ty - y0) * 4, (tx - x0) * 4
                th, tw = min(tile, h - ty) * 4, min(tile, w - tx) * 4
                out[:, :, ty * 4: ty * 4 + th, tx * 4: tx * 4 + tw] = res[:, :, oy: oy + th, ox: ox + tw]
        arr = (out[0].permute(1, 2, 0).clamp(0, 1).numpy() * 255).round().astype(np.uint8)
        big = Image.fromarray(arr)
        scale = int(job.params.get("scale", 2))
        if scale != 4:
            big = big.resize((src.width * scale, src.height * scale), Image.LANCZOS)
        if alpha is not None:
            big.putalpha(alpha.resize(big.size, Image.LANCZOS))
        return [Output(image=big)]
