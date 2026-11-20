"""CPU stand-ins for every workflow.

These are procedural, not AI. They let the whole app (canvas, jobs, storage,
video player) run on a laptop or in CI without a GPU. Outputs follow the input
shape, the colours named in the prompt and the seed, so the UI behaves like
it will with the real models.
"""

from __future__ import annotations

import colorsys
import io
import math
import random
import re

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from ..workflows import ASPECTS, preset_prompt
from . import imaging
from .base import JobInput, Output, Provider

WORK = 640  # working resolution for procedural renders


def _fit(image: Image.Image, size: int = WORK) -> Image.Image:
    im = image.copy()
    im.thumbnail((size, size), Image.LANCZOS)
    return im


def _jitter(rgb: tuple[int, int, int], rng: random.Random, amount: float) -> tuple[int, int, int]:
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    h = (h + rng.uniform(-amount, amount)) % 1.0
    s = min(1, max(0, s + rng.uniform(-0.1, 0.1)))
    v = min(1, max(0.08, v + rng.uniform(-0.08, 0.08)))
    return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, s, v))  # type: ignore[return-value]


def _gloss_for(prompt: str) -> float:
    if re.search(r"clay|matte|knit|fabric|paper", prompt, re.I):
        return 0.12
    if re.search(r"gloss|paint|chrome|automotive|car|lacquer", prompt, re.I):
        return 0.85
    return 0.45


def shade(mask: np.ndarray, base_rgb, rng: random.Random, gloss: float = 0.6, ink: np.ndarray | None = None,
          ink_alpha: float = 0.0, flat: bool = False) -> np.ndarray:
    """Procedural 'render': inflate the mask into a surface and light it."""
    hgt, wid = mask.shape
    height = imaging.soft_height(mask, radius=max(hgt, wid) / 14)
    gy, gx = np.gradient(height * 40.0)
    normal = np.dstack([-gx, -gy, np.ones_like(height)])
    normal /= np.linalg.norm(normal, axis=2, keepdims=True)
    ang = rng.uniform(math.radians(200), math.radians(250))
    light = np.array([math.cos(ang), math.sin(ang), 1.3])
    light /= np.linalg.norm(light)
    diffuse = np.clip((normal * light).sum(axis=2), 0, 1)
    half = light + np.array([0.0, 0.0, 1.0])
    half /= np.linalg.norm(half)
    spec = np.clip((normal * half).sum(axis=2), 0, 1) ** (20 + 60 * gloss) * gloss
    band = np.exp(-((normal[..., 1] + 0.35) ** 2) / 0.01) * gloss * 0.6  # long studio highlight
    base = np.array(base_rgb, dtype=np.float32)[None, None, :]
    if flat:
        color = base * (0.75 + 0.25 * (diffuse[..., None] > 0.55)) + 0 * spec[..., None]
    else:
        color = base * (0.28 + 0.8 * diffuse[..., None]) + 255 * (spec + band)[..., None]

    bg = imaging.studio_backdrop((wid, hgt)) if not flat else np.full((hgt, wid, 3), 246, np.float32)
    shadow_src = Image.fromarray((mask * 255).astype(np.uint8))
    shadow_src = shadow_src.transform(shadow_src.size, Image.AFFINE, (1, 0, 0, 0, 1, -hgt * 0.025))
    shadow = np.asarray(shadow_src.filter(ImageFilter.GaussianBlur(hgt / 40)), dtype=np.float32) / 255
    bg = bg * (1 - (0.12 if flat else 0.35) * shadow[..., None])

    m = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)),
                   dtype=np.float32)[..., None] / 255
    out = bg * (1 - m) + color * m
    if ink is not None and ink_alpha > 0:
        out = out * (1 - ink[..., None] * ink_alpha) + 20 * ink[..., None] * ink_alpha
    return out


def _random_silhouette(size: tuple[int, int], rng: random.Random) -> np.ndarray:
    """A product-like silhouette: a rounded body with a smaller feature on top."""
    w, h = size
    img = Image.new("L", size, 0)
    d = ImageDraw.Draw(img)
    bw, bh = w * rng.uniform(0.45, 0.7), h * rng.uniform(0.3, 0.5)
    cx, cy = w / 2, h * 0.58
    d.rounded_rectangle([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], radius=int(min(bw, bh) * rng.uniform(0.2, 0.5)), fill=255)
    tw, th = bw * rng.uniform(0.3, 0.6), bh * rng.uniform(0.4, 0.8)
    tx = cx + rng.uniform(-0.2, 0.2) * bw
    d.ellipse([tx - tw / 2, cy - bh / 2 - th * 0.7, tx + tw / 2, cy - bh / 2 + th * 0.3], fill=255)
    return np.asarray(img.filter(ImageFilter.GaussianBlur(3))) > 128


class MockCreate(Provider):
    workflow, backend, model = "create", "mock", "procedural"

    def run(self, job: JobInput) -> list[Output]:
        prompt = f"{job.params.get('prompt', '')} {preset_prompt(job.params.get('preset'))}"
        w, h = ASPECTS.get(str(job.params.get("aspect", "1:1")), (1024, 1024))
        size = (int(w * WORK / max(w, h)), int(h * WORK / max(w, h)))
        seed, count = job.seed(), int(job.params.get("count", 4))
        base = imaging.prompt_color(prompt, seed)
        outs = []
        for i in range(count):
            rng = random.Random(seed + i)
            job.progress((i + 0.5) / count, f"creating {i + 1}/{count}")
            mask = _random_silhouette(size, rng)
            arr = shade(mask, _jitter(base, rng, 0.08), rng, gloss=_gloss_for(prompt))
            outs.append(Output(image=imaging.to_pil(arr), meta={"seed": seed + i}))
        return outs


class MockRender(Provider):
    workflow, backend, model = "render", "mock", "procedural"

    def run(self, job: JobInput) -> list[Output]:
        sketch = _fit(job.images["image"])
        prompt = f"{job.params.get('prompt', '')} {preset_prompt(job.params.get('preset'))}"
        influence = float(job.params.get("influence", 0.75))
        stage = str(job.params.get("stage", "realistic"))
        count, seed = int(job.params.get("count", 4)), job.seed()
        mask = imaging.object_mask_from_sketch(sketch)
        ink = imaging.ink_mask(sketch).astype(np.float32)
        ink = np.asarray(Image.fromarray((ink * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)),
                         dtype=np.float32) / 255
        base = imaging.prompt_color(prompt, seed)
        gloss = _gloss_for(prompt) if stage == "realistic" else 0.15
        ink_alpha = {"color_block": 0.9, "shaded": 0.6}.get(stage, 0.1 + 0.5 * influence)
        outs = []
        for i in range(count):
            rng = random.Random(seed + i)
            job.progress((i + 0.5) / count, f"rendering {i + 1}/{count}")
            rgb = _jitter(base, rng, 0.03 if i == 0 else 0.12)
            arr = shade(mask, rgb, rng, gloss=gloss, ink=ink, ink_alpha=ink_alpha, flat=stage == "color_block")
            outs.append(Output(image=imaging.to_pil(arr), meta={"seed": seed + i}))
        return outs


def _mean_color(image: Image.Image) -> tuple[int, int, int]:
    small = imaging.flatten(image).resize((32, 32))
    arr = np.asarray(small, dtype=np.float32).reshape(-1, 3)
    sat = arr.max(1) - arr.min(1)
    pick = arr[sat >= np.percentile(sat, 70)]  # favour the colourful pixels
    return tuple(int(c) for c in pick.mean(0))  # type: ignore[return-value]


class MockEdit(Provider):
    workflow, backend, model = "edit", "mock", "procedural"

    def run(self, job: JobInput) -> list[Output]:
        src = imaging.flatten(job.images["image"])
        mask = job.images.get("mask")
        mask = Image.new("L", src.size, 255) if mask is None else imaging.mask_from_image(mask, src.size)
        soft = imaging.feather(mask, 4)
        prompt = str(job.params.get("prompt", ""))
        seed = job.seed()
        ref = job.images.get("ref1")
        outs = []
        for i in range(int(job.params.get("count", 2))):
            rng = random.Random(seed + i)
            if re.search(r"\b(remove|delete|erase)\b", prompt, re.I):
                filled = src.filter(ImageFilter.GaussianBlur(src.width / 25))
            else:
                target = _mean_color(ref) if ref is not None else imaging.prompt_color(prompt, seed)
                target = _jitter(target, rng, 0.04 * i)
                filled = ImageOps.colorize(ImageOps.grayscale(src), black=(10, 10, 12), white=(250, 250, 250), mid=target)
                filled = ImageEnhance.Contrast(filled).enhance(1.1)
            outs.append(Output(image=Image.composite(filled, src, soft), meta={"seed": seed + i}))
        return outs


class MockNewView(Provider):
    workflow, backend, model = "new_view", "mock", "procedural"

    def run(self, job: JobInput) -> list[Output]:
        src = _fit(imaging.flatten(job.images["image"]))
        angle = float(job.params.get("angle", 45))
        outs = []
        for i in range(int(job.params.get("count", 2))):
            outs.append(Output(image=_rotate_view(src, angle + 8 * i), meta={"angle": angle}))
        return outs


def _rotate_view(src: Image.Image, angle: float) -> Image.Image:
    """Fake a y-axis rotation by squashing and mirroring the image."""
    w, h = src.size
    sx = max(0.2, abs(math.cos(math.radians(angle))))
    img = src.transpose(Image.FLIP_LEFT_RIGHT) if 90 < (angle % 360) < 270 else src
    new_w = max(8, int(w * sx))
    squeezed = img.resize((new_w, h), Image.LANCZOS)
    bg = src.getpixel((2, 2))
    canvas = Image.new("RGB", (w, h), bg)
    canvas.paste(squeezed, ((w - new_w) // 2, 0))
    return canvas


class MockAnimate(Provider):
    """Writes a real MP4: a turntable, push-in or cross-fade built from the frames."""

    workflow, backend, model = "animate", "mock", "procedural"
    fps = 24

    def run(self, job: JobInput) -> list[Output]:
        start = _fit(imaging.flatten(job.images["image"]), 512)
        end = job.images.get("end")
        end = imaging.flatten(end).resize(start.size, Image.LANCZOS) if end is not None else None
        w, h = (start.width // 16) * 16, (start.height // 16) * 16
        start = start.resize((w, h))
        if end is not None:
            end = end.resize((w, h))
        motion = str(job.params.get("motion", "custom"))
        if motion == "custom" and re.search(r"turn|rotat|spin", str(job.params.get("prompt", "")), re.I):
            motion = "turntable"
        n = int(float(job.params.get("duration", 5)) * self.fps)
        frames = []
        for f in range(n):
            t = f / max(1, n - 1)
            if f % 12 == 0:
                job.progress(t * 0.95, f"frame {f + 1}/{n}")
            if motion == "turntable" or motion == "orbit":
                frame = _rotate_view(start, 360 * t)
            else:
                zoom = 1 + 0.12 * t
                cw, ch = int(w / zoom), int(h / zoom)
                ox, oy = (w - cw) // 2, (h - ch) // 2
                frame = start.crop((ox, oy, ox + cw, oy + ch)).resize((w, h), Image.LANCZOS)
                if motion == "reveal":
                    frame = ImageEnhance.Brightness(frame).enhance(0.15 + 0.85 * min(1, t * 1.6))
            if end is not None:
                frame = Image.blend(frame, end, t * t * (3 - 2 * t))
            frames.append(np.asarray(frame))
        buf = io.BytesIO()
        _write_mp4(buf, frames, self.fps)
        return [Output(data=buf.getvalue(), mime="video/mp4", preview=Image.fromarray(frames[0]),
                       meta={"fps": self.fps, "frames": n})]


def _write_mp4(buf: io.BytesIO, frames: list[np.ndarray], fps: int) -> None:
    import os
    import tempfile

    import imageio.v2 as iio2

    fd, path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    try:
        with iio2.get_writer(path, fps=fps, codec="libx264", quality=8, pixelformat="yuv420p",
                             macro_block_size=16, ffmpeg_params=["-movflags", "+faststart"]) as writer:
            for fr in frames:
                writer.append_data(fr)
        with open(path, "rb") as fh:
            buf.write(fh.read())
    finally:
        os.unlink(path)


class MockRemoveBg(Provider):
    workflow, backend, model = "remove_bg", "mock", "border-colour key"

    def run(self, job: JobInput) -> list[Output]:
        src = job.images["image"].convert("RGBA")
        rgb = np.asarray(src.convert("RGB"), dtype=np.float32)
        border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
        bg = np.median(border, axis=0)
        dist = np.linalg.norm(rgb - bg, axis=2)
        alpha = np.clip((dist - 18) * 8, 0, 255).astype(np.uint8)
        a = Image.fromarray(alpha).filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.GaussianBlur(0.8))
        src.putalpha(a)
        return [Output(image=src)]


class LanczosUpscale(Provider):
    """Not a stand-in: plain Lanczos plus an unsharp mask, the CPU fallback."""

    workflow, backend, model = "upscale", "mock", "lanczos"

    def run(self, job: JobInput) -> list[Output]:
        src = job.images["image"]
        scale = int(job.params.get("scale", 2))
        big = src.resize((src.width * scale, src.height * scale), Image.LANCZOS)
        return [Output(image=big.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2)))]


class MockErase(Provider):
    """Preview stand-in: the soft colour fill alone, no AI."""

    workflow, backend, model = "erase", "mock", "procedural"

    def run(self, job: JobInput) -> list[Output]:
        src = imaging.flatten(job.images["image"])
        hole = imaging.fill_enclosed(imaging.mask_from_image(job.images["mask"], src.size))
        if not hole.getbbox():
            raise ValueError("The mask is empty: paint over the object to erase first")
        hole = hole.filter(ImageFilter.MaxFilter(7))
        filled = imaging.fill_holes(src, hole)
        out = Image.composite(filled, src, imaging.feather(hole, 3))
        return [Output(image=out, meta={"seed": job.seed()})]


class MockOutpaint(Provider):
    workflow, backend, model = "outpaint", "mock", "procedural"

    def run(self, job: JobInput) -> list[Output]:
        src = imaging.flatten(job.images["image"])
        canvas, _ = imaging.extend_canvas(src, *imaging.outpaint_pads(job.params, src.size))
        return [Output(image=canvas, meta={"seed": job.seed()})]


class MockStyle(Provider):
    """Preview stand-in: colour statistics transfer (Reinhard), no AI."""

    workflow, backend, model = "style", "mock", "procedural"

    def run(self, job: JobInput) -> list[Output]:
        src = np.asarray(imaging.flatten(job.images["image"]), dtype=np.float32)
        ref = np.asarray(imaging.flatten(job.images["style"]).resize((256, 256)), dtype=np.float32)
        s_mean, s_std = src.reshape(-1, 3).mean(0), src.reshape(-1, 3).std(0) + 1e-3
        r_mean, r_std = ref.reshape(-1, 3).mean(0), ref.reshape(-1, 3).std(0) + 1e-3
        outs = []
        for i in range(int(job.params.get("count", 2))):
            k = 0.85 + 0.15 * i
            arr = (src - s_mean) / s_std * (r_std * k + s_std * (1 - k)) + (r_mean * k + s_mean * (1 - k))
            outs.append(Output(image=imaging.to_pil(arr), meta={"seed": job.seed() + i}))
        return outs
