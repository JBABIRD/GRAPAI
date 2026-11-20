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
