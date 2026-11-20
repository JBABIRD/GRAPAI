"""Provider registry: picks the backend for each workflow from settings.

Backends:
- ``mock``  CPU stand-ins, no AI, for development and tests.
- ``comfy`` a ComfyUI server running the open-weight models (see comfy_workflows/).
- ``local`` small models run in-process with torch (background removal, upscaling).
"""

from __future__ import annotations

import importlib
from functools import lru_cache

from ..config import settings
from .base import Provider

REGISTRY: dict[str, dict[str, str]] = {
    "create": {"mock": "mock:MockCreate", "comfy": "comfy:ComfyCreate"},
    "render": {"mock": "mock:MockRender", "comfy": "comfy:ComfyRender"},
    "edit": {"mock": "mock:MockEdit", "comfy": "comfy:ComfyEdit"},
    "new_view": {"mock": "mock:MockNewView", "comfy": "comfy:ComfyNewView"},
    "style": {"mock": "mock:MockStyle", "comfy": "comfy:ComfyStyle"},
    "erase": {"mock": "mock:MockErase", "comfy": "comfy:ComfyErase"},
    "outpaint": {"mock": "mock:MockOutpaint", "comfy": "comfy:ComfyOutpaint"},
    "animate": {"mock": "mock:MockAnimate", "comfy": "comfy:ComfyAnimate"},
    "remove_bg": {"mock": "mock:MockRemoveBg", "local": "local:BiRefNetRemoveBg", "comfy": "local:BiRefNetRemoveBg"},
    "upscale": {"mock": "mock:LanczosUpscale", "local": "local:ESRGANUpscale", "comfy": "local:ESRGANUpscale"},
}


@lru_cache(maxsize=None)
def get_provider(workflow: str, backend: str | None = None) -> Provider:
    backend = backend or settings.provider_for(workflow)
    try:
        target = REGISTRY[workflow][backend]
    except KeyError as exc:
        raise KeyError(f"no provider for workflow={workflow!r} backend={backend!r}") from exc
    module_name, cls_name = target.split(":")
    module = importlib.import_module(f"{__name__}.{module_name}")
    return getattr(module, cls_name)()


def describe_all() -> list[dict]:
    return [
        {"workflow": w, "backend": settings.provider_for(w), "target": REGISTRY[w].get(settings.provider_for(w))}
        for w in REGISTRY
    ]
