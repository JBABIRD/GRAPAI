"""Prompt building shared by the AI backends."""

from __future__ import annotations

import re

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


BLANK_WORDS = {"", "nothing", "none", "no", "empty", "blank", "plain", "nothing else", "n/a", "-", "same", "keep"}


def is_blank_prompt(text) -> bool:
    """'nothing', 'none', 'empty'... mean 'no new content', not a scene to describe."""
    return str(text or "").strip().strip(".!").lower() in BLANK_WORDS


def outpaint_prompt(params: dict) -> str:
    extra = str(params.get("prompt", "")).strip().rstrip(".")
    base = ("Extend the image outward in exactly the same medium and style (photo, sketch, drawing or render): "
            "the same background continues naturally beyond the original edges, matching its colour, texture, "
            "lighting and perspective.")
    if is_blank_prompt(extra):
        base += " If the background is plain, keep it plain and empty."
    else:
        base += f" Around it: {extra}."
    return base + (" Do not add any vehicles, people, buildings, text or other new objects."
                   " Do not repeat or duplicate the main subject, and add no reflections of it."
                   " Add no other drawings, sketches, posters, pictures or screens.")


def outpaint_lora_prompt(params: dict) -> str:
    """The fal outpaint LoRA's own instruction first; a scene description, if any, after it."""
    base = "Fill the green spaces according to the image"
    extra = str(params.get("prompt", "")).strip().rstrip(".")
    if is_blank_prompt(extra) or extra.lower() in ("extend the image", "extend", "outpaint"):
        return base + "."
    return f"{base}: {extra}."


STYLE_ASPECTS = {
    "full": ("Re-render image 1 with the look of image 2", "medium, line work, colours, materials, shading and lighting", "style"),
    "colours_materials": ("Re-render image 1 with the colours and materials of image 2", "colour palette, materials and surface finishes", "colour and material"),
    "rendering": ("Re-render image 1 with the rendering technique of image 2", "medium, line work, shading and rendering technique", "rendering"),
    "lighting_mood": ("Relight image 1 with the lighting and colour palette of image 2", "lighting, time of day, atmosphere and colour grading", "colour and light"),
}


GENERIC_STYLE = re.compile(r"^(render|restyle|redraw|make|turn|transfer|apply|use)?\s*(image ?1|it|this)?\s*(in|into|to|with)?\s*(the)?\s*(style|look)\s*(of)?\s*(image ?2|the reference|reference)?\.?$", re.I)


def style_prompt(params: dict, style: str | None = None, info: dict | None = None) -> str:
    """Restyle image 1 with image 2's style. `style` is image 2's style in words (from the local vision model);
    without it, a simple read of the reference (a monochrome drawing on paper and its ink) stands in.

    Laptop tests: klein copies a style only loosely from the reference latent alone (a coloured photo with a
    pencil filter); the style written out in words is what makes the transfer happen."""
    transfer = str(params.get("transfer", "full"))
    lead, aspect, kind = STYLE_ASPECTS.get(transfer, STYLE_ASPECTS["full"])
    desc = str(params.get("prompt", "")).strip().rstrip(".")
    if desc and GENERIC_STYLE.match(desc):
        desc = ""
    if not style and info and info.get("kind") == "drawing":
        style = (f"a monochrome hand drawing in {info['colour']} ink on white paper, loose strokes and hatching, "
                 "no colour fill, the background left as white paper")
    if transfer == "full":
        text = "Restyle image 1 completely in the visual style of image 2"
        text += f". The style of image 2: {style}." if style else "."
        text += (" Apply this medium, technique, line work, colour palette, shading, lighting and background treatment"
                 " to all of image 1, so it no longer looks like the original medium.")
    else:
        text = f"{lead}"
        text += f". The style of image 2: {style}. Take only its {aspect}." if style else f": match its {aspect}."
    if desc:
        text += f" {desc}."
    text += (" Keep image 1's subject with its exact shape, proportions, design details, viewpoint and composition."
             f" Image 2 is only a {kind} reference: none of its objects, vehicles, text or layout may appear.")
    return text


VIEWS = {
    "front": ("straight front view: the camera is directly in front of the {what} at its centre height; only the "
              "front face is visible, both sides are hidden, the view is symmetric"),
    "front_left_34": "three-quarter front view from the front-left, camera slightly above centre height",
    "left": "pure side view of the left side, camera perpendicular to the side, profile silhouette",
    "rear_left_34": ("three-quarter rear view from the rear-left: we see the back end and the left side of the {what}, "
                     "the front end faces away and is hidden"),
    "rear": ("straight rear view: the camera is directly behind the {what}; its front end, which faces away from "
             "the camera, is completely hidden; we see only the back end"),
    "rear_right_34": ("three-quarter rear view from the rear-right: we see the back end and the right side of the "
                      "{what}, the front end faces away and is hidden"),
    "right": "pure side view of the right side, camera perpendicular to the side, profile silhouette",
    "front_right_34": "three-quarter front view from the front-right, camera slightly above centre height",
    "top": ("top view: the camera is directly above the {what} looking straight down; only its upper surface is "
            "visible, the sides are hidden, the outline is the plan silhouette"),
}
VIEW_LABELS = {
    "front": "Front", "front_left_34": "3/4 front left", "left": "Left side", "rear_left_34": "3/4 rear left",
    "rear": "Rear", "rear_right_34": "3/4 rear right", "right": "Right side", "front_right_34": "3/4 front right",
    "top": "Top (approx.)",
}
VIEW_SETS = {
    # Top is the weakest view with klein 4B, so the default design set leaves it out (Ortho 4 has it).
    "design_5": ["front", "left", "rear", "front_left_34", "rear_right_34"],
    "ortho_4": ["front", "left", "rear", "top"],
    "turnaround_8": ["front", "front_right_34", "right", "rear_right_34", "rear", "rear_left_34", "left",
                     "front_left_34"],
}


def view_prompt(params: dict, view: str) -> str:
    what = str(params.get("prompt", "")).strip().rstrip(".") or "object"
    text = (f"Show the exact same {what} from a new camera position: {VIEWS[view].format(what=what)}. "
            "Keep its design, shape, proportions, colours, materials and every detail identical, only the camera moves.")
    if str(params.get("scene", "same_scene")) == "studio":
        text += " Place it on a plain light grey studio backdrop with soft, even lighting."
    else:
        text += " Keep the same environment, ground, background and lighting, seen from this new angle."
    return text


def envswap_prompt(params: dict) -> str:
    what = str(params.get("what", "")).strip().rstrip(".") or "product"
    desc = str(params.get("prompt", "")).strip().rstrip(".")
    text = (f"Image 1 shows the {what} standing in a new environment. Rebuild the whole environment around the "
            f"{what} as a coherent photograph based on the environment in image 2")
    text += f": {desc}." if desc else "."
    text += (f" The {what} stands on the ground or surface of this environment. A soft, diffuse contact shadow falls on "
             f"the surface directly under the {what}, fading gradually, with no visible outline, base or plate under it; "
             f"match perspective, horizon, scale and lighting to the {what}, with natural reflections. Image 2 is only "
             "an environment reference: none of its vehicles, people or objects may appear. "
             f"Keep the {what} itself exactly unchanged.")
    return text
