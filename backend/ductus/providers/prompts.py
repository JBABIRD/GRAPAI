"""Prompt building shared by the AI backends."""

from __future__ import annotations

from ..workflows import MOTION_PROMPTS, STAGE_PROMPTS, preset_prompt

VIEW_ELEVATION = {
    "low": "from a low camera angle",
    "eye": "at eye level",
    "high": "from a high three-quarter angle",
    "top": "from directly above, top view",
}

INPAINT_NEGATIVE = ("blurry, smeared, visible seam, border, frame, text, watermark, vehicles, people, buildings")
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
    """Klein follows instructions: say what to remove and, if given, what replaces it."""
    text = str(params.get("prompt", "")).strip()
    base = "Remove the masked object completely, including its shadow and reflection."
    if text:
        return f"{base} {text}. Keep everything else unchanged, same lighting and perspective."
    return (f"{base} Fill the area with the background that continues seamlessly from its surroundings, "
            "same surfaces, texture, lighting and perspective. Keep everything else unchanged.")


def outpaint_prompt(params: dict) -> str:
    extra = str(params.get("prompt", "")).strip()
    base = ("Extend the photo outward: the same scene continues naturally beyond the original edges, matching "
            "ground, background, sky, lighting, reflections and perspective.")
    if extra:
        base += f" Around it: {extra}."
    return base + " Do not add any vehicles, people, buildings, text or other new objects."


STYLE_ASPECTS = {
    "full": "same medium, line work, colours, materials, shading, lighting and background treatment as image 2",
    "colours_materials": "same colour palette, materials and surface finishes as image 2",
    "rendering": "same medium, line work, shading and rendering technique as image 2",
    "lighting_mood": "same lighting, time of day, atmosphere and colour grading as image 2",
}


def style_prompt(params: dict) -> str:
    """Laptop tests: 'image 1 / image 2' wording transfers far more than 'Picture 1/2', and a described
    style works best inside the instruction rather than appended."""
    transfer = str(params.get("transfer", "full"))
    aspect = STYLE_ASPECTS.get(transfer, STYLE_ASPECTS["full"])
    verb = "Relight image 1" if transfer == "lighting_mood" else "Redraw image 1"
    desc = str(params.get("prompt", "")).strip().rstrip(".")
    text = f"{verb} in the exact visual style of image 2"
    text += f": {desc}, {aspect}." if desc else f": {aspect}."
    text += (" Keep image 1's object, exact shape, proportions, design details and composition."
             " Do not copy any objects or content from image 2.")
    if transfer == "lighting_mood":
        text += " Do not add any vehicles, people or objects from image 2."
    return text
