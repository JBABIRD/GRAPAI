"""Runtime settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class Settings:
    # "mock" runs everything on CPU with procedural stand-ins, "comfy" sends the
    # AI workflows to a ComfyUI server running the open-weight models.
    provider: str = field(default_factory=lambda: _env("DUCTUS_PROVIDER", "mock"))
    data_dir: Path = field(default_factory=lambda: Path(_env("DUCTUS_DATA_DIR", "./data")).resolve())
    max_workers: int = field(default_factory=lambda: int(_env("DUCTUS_WORKERS", "1")))
    cors_origins: list[str] = field(
        default_factory=lambda: _env("DUCTUS_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    )
    device: str = field(default_factory=lambda: _env("DUCTUS_DEVICE", "cuda"))

    comfy_url: str = field(default_factory=lambda: _env("DUCTUS_COMFY_URL", "http://127.0.0.1:8188"))
    # Hybrid setups send each mode (or tool) to its own ComfyUI server, e.g. fast
    # mode to a laptop and quality mode to a rented GPU. See comfy_target().
    comfy_workflows: Path = field(
        default_factory=lambda: Path(_env("DUCTUS_COMFY_WORKFLOWS", str(Path(__file__).resolve().parent.parent / "comfy_workflows")))
    )
    comfy_timeout: float = field(default_factory=lambda: float(_env("DUCTUS_COMFY_TIMEOUT", "1800")))

    # Small models run in-process (CPU works, GPU is faster).
    bg_model: str = field(default_factory=lambda: _env("DUCTUS_BG_MODEL", "ZhengPeng7/BiRefNet"))
    upscale_weights: str = field(
        default_factory=lambda: _env(
            "DUCTUS_UPSCALE_WEIGHTS",
            "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
        )
    )

    def comfy_target(self, workflow: str, mode: str) -> tuple[str, str]:
        """(server URL, template profile) for a tool in a mode.

        Most specific wins: DUCTUS_COMFY_URL_<TOOL>_<MODE>, DUCTUS_COMFY_URL_<TOOL>,
        DUCTUS_COMFY_URL_<MODE>, then DUCTUS_COMFY_URL. Profiles (a subfolder of
        comfy_workflows/ with lighter graphs, e.g. "laptop") resolve the same way
        from DUCTUS_COMFY_PROFILE_*.
        """
        w, m = workflow.upper(), mode.upper()

        def pick(prefix: str, default: str) -> str:
            for key in (f"{prefix}_{w}_{m}", f"{prefix}_{w}", f"{prefix}_{m}", prefix):
                if os.environ.get(key):
                    return os.environ[key]
            return default

        return pick("DUCTUS_COMFY_URL", self.comfy_url).rstrip("/"), pick("DUCTUS_COMFY_PROFILE", "")

    def provider_for(self, workflow: str) -> str:
        """Per-workflow override, e.g. DUCTUS_PROVIDER_ANIMATE=mock."""
        return _env(f"DUCTUS_PROVIDER_{workflow.upper()}", self.provider)


settings = Settings()
