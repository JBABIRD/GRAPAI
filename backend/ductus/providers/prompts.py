"""Prompt building shared by the AI backends."""

from __future__ import annotations

from ..workflows import MOTION_PROMPTS, STAGE_PROMPTS, preset_prompt

VIEW_ELEVATION = {
    "low": "from a low camera angle",
    "eye": "at eye level",
    "high": "from a high three-quarter angle",
    "top": "from directly above, top view",
}

NEGATIVE = "blurry, low quality, distorted proportions, extra parts, watermark, text artifacts"
VIDEO_NEGATIVE = ("static, blurry, distorted, deformed product, changing shape, flicker, low quality, "
                  "watermark, text, morphing")


def create_prompt(params: dict) -> str:
    return ", ".join(p for p in [params.get("prompt", "").strip(), preset_prompt(params.get("preset"))] if p)


def render_prompt(params: dict) -> str:
    stage = STAGE_PROMPTS.get(str(params.get("stage", "realistic")), STAGE_PROMPTS["realistic"])
    influence = float(params.get("influence", 0.75))
    if influence >= 0.66:
        keep = "Keep the exact shape, proportions, perspective and line positions of the sketch."
    elif influence >= 0.33:
        keep = "Keep the overall shape and perspective of the sketch, refine the details."
    else:
        keep = "Use the sketch as loose inspiration for the form; refine and improve the design freely."
    parts = [stage, keep, params.get("prompt", "").strip()]
    if params.get("stage", "realistic") == "realistic":
        parts.append(preset_prompt(params.get("preset")))
    return " ".join(p for p in parts if p)


def edit_prompt(params: dict, n_refs: int) -> str:
    text = str(params.get("prompt", "")).strip()
    # Users write @1 @2 @3 like on the canvas; Qwen-Image-Edit calls them Picture 1..3.
    for i in range(1, 4):
        text = text.replace(f"@{i}", f"Picture {i}")
    if n_refs and "Picture" not in text:
        text += " Use the style, materials and colours of the reference image."
    return text


def new_view_prompt(params: dict) -> str:
    angle = int(params.get("angle", 45))
    elev = VIEW_ELEVATION.get(str(params.get("elevation", "eye")), "at eye level")
    return (f"Rotate the camera {angle} degrees around the product and show it {elev}. "
            "Keep the design, materials, colours and proportions exactly the same. Plain studio background.")


def animate_prompt(params: dict) -> str:
    motion = MOTION_PROMPTS.get(str(params.get("motion", "custom")), "")
    return ", ".join(p for p in [params.get("prompt", "").strip(), motion] if p) or \
        "subtle camera movement, the product stays unchanged"


def erase_prompt(params: dict) -> str:
    fill = str(params.get("prompt", "")).strip()
    if fill:
        return f"{fill}, seamlessly matching the surrounding scene, same lighting, perspective and texture, photorealistic"
    return ("empty background only, seamless continuation of the surrounding surfaces, floor and backdrop, "
            "same lighting, perspective and texture, nothing in this area, no objects, photorealistic")


def outpaint_prompt(params: dict) -> str:
    extra = str(params.get("prompt", "")).strip()
    base = ("wide view of the same scene, the background, ground, sky and lighting continue naturally to the "
            "edges of the frame, consistent perspective and reflections, sharp photographic detail, "
            "no additional vehicles, products or people, no added text, no borders, no frames")
    return f"{extra}, {base}" if extra else base
