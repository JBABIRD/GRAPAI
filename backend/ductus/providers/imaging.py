"""Small image helpers shared by providers (no GPU, numpy + Pillow only)."""

from __future__ import annotations

import colorsys
import hashlib
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

COLOR_WORDS: dict[str, tuple[int, int, int]] = {
    "red": (196, 32, 38), "orange": (232, 112, 28), "yellow": (236, 196, 40),
    "green": (46, 140, 76), "teal": (20, 128, 128), "blue": (30, 84, 180),
    "navy": (24, 38, 84), "purple": (104, 56, 160), "pink": (226, 110, 160),
    "white": (232, 232, 228), "black": (28, 28, 30), "grey": (128, 130, 134),
    "gray": (128, 130, 134), "silver": (176, 180, 186), "gold": (198, 160, 70),
    "copper": (184, 104, 60), "brown": (110, 72, 44), "beige": (210, 190, 160),
    "olive": (110, 116, 60), "mint": (150, 214, 186), "cream": (240, 230, 206),
}


def flatten(image: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    """RGBA -> RGB over a solid background."""
    if image.mode != "RGBA":
        return image.convert("RGB")
    base = Image.new("RGB", image.size, bg)
    base.paste(image, mask=image.split()[3])
    return base


def prompt_color(prompt: str, seed: int) -> tuple[int, int, int]:
    words = re.findall(r"[a-z]+", (prompt or "").lower())
    for w in words:
        if w in COLOR_WORDS:
            return COLOR_WORDS[w]
    # No colour named: a stable, tasteful colour from the prompt and seed.
    h = int(hashlib.sha1(f"{prompt}|{seed}".encode()).hexdigest(), 16)
    hue = (h % 360) / 360.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.55, 0.72)
    return int(r * 255), int(g * 255), int(b * 255)


def ink_mask(image: Image.Image, threshold: int = 140) -> np.ndarray:
    """Boolean array of the dark strokes in a sketch."""
    gray = np.asarray(flatten(image).convert("L"), dtype=np.uint8)
    return gray < threshold


def object_mask_from_sketch(image: Image.Image) -> np.ndarray:
    """Fill the regions enclosed by the sketch lines.

    The background is whatever a flood fill from the border reaches after the
    strokes are thickened slightly to close small gaps.
    """
    ink = ink_mask(image)
    if not ink.any():
        return np.zeros(ink.shape, dtype=bool)
    ink_img = Image.fromarray((ink * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(7))
    work = Image.fromarray(np.where(np.asarray(ink_img) > 0, 0, 255).astype(np.uint8))
    # pad so the fill can travel all the way around the border
    padded = Image.new("L", (work.width + 2, work.height + 2), 255)
    padded.paste(work, (1, 1))
    ImageDraw.floodfill(padded, (0, 0), 128)
    filled = np.asarray(padded)[1:-1, 1:-1]
    obj = filled != 128
    if obj.mean() < 0.01 or obj.sum() <= ink.sum() * 1.3:
        # Open sketch: fall back to a soft hull around the strokes.
        hull = Image.fromarray((ink * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(31))
        hull = hull.filter(ImageFilter.GaussianBlur(12))
        obj = np.asarray(hull) > 60
    return obj


def soft_height(mask: np.ndarray, radius: float) -> np.ndarray:
    """Pillowy height field inside a mask (0 at the edge, 1 in the middle)."""
    m = Image.fromarray((mask * 255).astype(np.uint8))
    h = np.zeros(mask.shape, dtype=np.float32)
    for r in (radius * 0.25, radius * 0.5, radius):
        blurred = np.asarray(m.filter(ImageFilter.GaussianBlur(max(r, 1))), dtype=np.float32) / 255.0
        h += blurred
    h = h / 3.0 * mask
    if h.max() > 0:
        h = h / h.max()
    return np.sqrt(np.clip(h, 0, 1))


def studio_backdrop(size: tuple[int, int], top=(238, 238, 236), bottom=(196, 198, 200)) -> np.ndarray:
    w, h = size
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    top_a = np.array(top, dtype=np.float32)[None, None, :]
    bot_a = np.array(bottom, dtype=np.float32)[None, None, :]
    grad = top_a * (1 - t) + bot_a * t
    return np.repeat(grad, w, axis=1)


def feather(mask: Image.Image, radius: float = 6) -> Image.Image:
    return mask.convert("L").filter(ImageFilter.GaussianBlur(radius))


def to_pil(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def mask_from_image(mask: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Masks arrive as RGBA paint (alpha = selected) or as greyscale (white = selected)."""
    if mask.mode == "RGBA" and mask.split()[3].getextrema()[0] < 255:
        m = mask.split()[3]
    else:
        m = mask.convert("L")
    return m.resize(size, Image.LANCZOS)


def pad_to_aspect(image: Image.Image, aspect: float) -> Image.Image:
    """Letterbox an RGB image to width/height = aspect, filling with its border colour."""
    w, h = image.size
    if abs(w / h - aspect) < 0.01:
        return image
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    fill = tuple(int(c) for c in np.median(border, axis=0))
    nw, nh = (round(h * aspect), h) if w / h < aspect else (w, round(w / aspect))
    canvas = Image.new("RGB", (nw, nh), fill)
    canvas.paste(image.convert("RGB"), ((nw - w) // 2, (nh - h) // 2))
    return canvas


def _box_blur(arr: np.ndarray, r: int) -> np.ndarray:
    """Mean filter of radius r over the first two axes (edges clamped), via cumulative sums."""
    if r < 1:
        return arr
    out = arr
    for axis in (0, 1):
        n = out.shape[axis]
        pad = [(0, 0)] * out.ndim
        pad[axis] = (r + 1, r)
        c = np.cumsum(np.pad(out, pad, mode="edge"), axis=axis, dtype=np.float64)
        hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
        lo = np.take(c, np.arange(0, n), axis=axis)
        out = ((hi - lo) / (2 * r + 1)).astype(np.float32)
    return out


def fill_holes(image: Image.Image, hole: Image.Image) -> Image.Image:
    """Fill the white area of `hole` from its surroundings, coarse to fine.

    Not a generative fill: it gives the AI model (or the preview mode) a soft,
    colour-matched starting point instead of the object or a blank border.
    """
    hole = hole.convert("L").resize(image.size)
    if max(image.size) > 512:
        # Work on a small copy (it is a soft fill anyway), then keep full-res pixels outside the hole.
        k = 512 / max(image.size)
        small = (max(1, round(image.width * k)), max(1, round(image.height * k)))
        rough = fill_holes(image.resize(small, Image.BILINEAR), hole.resize(small, Image.BILINEAR))
        return Image.composite(rough.resize(image.size, Image.BICUBIC), image.convert("RGB"), hole.point(lambda v: 255 if v >= 128 else 0))
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    known = (np.asarray(hole, dtype=np.float32) < 128).astype(np.float32)
    if known.min() == 1.0:
        return image.convert("RGB")
    if known.max() == 0.0:
        return Image.new("RGB", image.size, (128, 128, 128))
    out = rgb.copy()
    r = max(image.size) // 4
    while r >= 1:
        k = known[..., None]
        num = _box_blur(_box_blur(rgb * k, r), r)
        den = _box_blur(_box_blur(known, r), r)[..., None]
        est = num / np.maximum(den, 1e-6)
        # Finer levels take over where they have enough known pixels, blended so no bands show.
        alpha = np.clip(den * 3, 0, 1) * (1 - k) if r < max(image.size) // 4 else (den > 1e-6) * (1 - k)
        out = alpha * est + (1 - alpha) * out
        r //= 2
    return to_pil(out)


def extend_canvas(image: Image.Image, left: int, top: int, right: int, bottom: int) -> tuple[Image.Image, Image.Image]:
    """Place the image on a larger canvas; returns (prefilled canvas, mask of the new area)."""
    src = flatten(image)
    w, h = src.size
    size = (w + left + right, h + top + bottom)
    canvas = Image.new("RGB", size)
    canvas.paste(src, (left, top))
    hole = Image.new("L", size, 255)
    hole.paste(0, (left, top, left + w, top + h))
    return fill_holes(canvas, hole), hole


def mask_box(mask: Image.Image, margin: float = 0.6, min_side: int = 384) -> tuple[int, int, int, int] | None:
    """Box around the painted area, grown by `margin` of its size so the model sees context."""
    bbox = mask.point(lambda v: 255 if v > 127 else 0).getbbox()
    if not bbox:
        return None
    x0, y0, x1, y1 = bbox
    w, h = mask.size
    bw, bh = x1 - x0, y1 - y0
    gw = max(bw * (1 + 2 * margin), min(min_side, w))
    gh = max(bh * (1 + 2 * margin), min(min_side, h))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    nx0 = int(max(0, min(cx - gw / 2, w - gw)))
    ny0 = int(max(0, min(cy - gh / 2, h - gh)))
    return nx0, ny0, int(min(w, nx0 + gw)), int(min(h, ny0 + gh))


def outpaint_pads(params: dict, size: tuple[int, int], max_side: int = 4096) -> tuple[int, int, int, int]:
    """Left/top/right/bottom padding in source pixels, clamped so the canvas stays <= max_side."""
    w, h = size
    pads = [max(0, int(float(params.get(k, 0) or 0))) for k in ("left", "top", "right", "bottom")]
    if not any(pads):
        raise ValueError("Drag the frame outside the image to choose where to extend it")
    for a, b, side in ((0, 2, w), (1, 3, h)):
        extra = pads[a] + pads[b]
        if side + extra > max_side:
            k = (max_side - side) / extra
            pads[a], pads[b] = int(pads[a] * k), int(pads[b] * k)
    return tuple(pads)  # type: ignore[return-value]
