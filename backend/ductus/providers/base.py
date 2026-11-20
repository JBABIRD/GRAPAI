"""Provider interface. A provider runs one workflow on one backend."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable

from PIL import Image

ProgressFn = Callable[[float, str], None]


@dataclass
class JobInput:
    images: dict[str, Image.Image]
    params: dict[str, Any]
    progress: ProgressFn = lambda p, msg="": None

    def seed(self) -> int:
        s = int(self.params.get("seed", -1) or -1)
        return random.randint(0, 2**31 - 1) if s < 0 else s


@dataclass
class Output:
    """One generated result. Exactly one of image or data is set."""

    image: Image.Image | None = None
    data: bytes | None = None
    mime: str = "image/png"
    preview: Image.Image | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class Provider:
    workflow: str = ""
    backend: str = ""
    model: str = ""

    def run(self, job: JobInput) -> list[Output]:  # pragma: no cover - interface
        raise NotImplementedError

    def describe(self) -> dict:
        return {"workflow": self.workflow, "backend": self.backend, "model": self.model}
