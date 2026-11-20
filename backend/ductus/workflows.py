"""Workflow catalogue: what the UI can ask for, and which inputs each one takes.

Each workflow is served by a provider (see ductus.providers). The catalogue is
sent to the web app, so the UI is driven by this file.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Preset(BaseModel):
    id: str
    name: str
    prompt: str


# Original style presets tuned for product and transportation design.
PRESETS: list[Preset] = [
    Preset(id="studio", name="Studio product", prompt="photorealistic studio product render, softbox lighting, seamless light grey backdrop, crisp reflections, 85mm lens"),
    Preset(id="clay", name="Clay model", prompt="matte grey clay model, soft ambient occlusion, studio lighting, design review render"),
    Preset(id="auto", name="Automotive studio", prompt="automotive studio render, glossy paint with long horizontal highlights, dark reflective floor, rim lighting, clean surface reflections"),
    Preset(id="exterior", name="Outdoor context", prompt="photographed outdoors at golden hour, realistic environment reflections, shallow depth of field"),
    Preset(id="softgoods", name="Soft goods", prompt="soft goods product photo, knit and mesh textiles, stitching detail, natural daylight"),
    Preset(id="marker", name="Marker rendering", prompt="professional industrial design marker rendering on paper, bold highlights, grey and accent colour markers"),
    Preset(id="tech", name="Technical materials", prompt="anodised aluminium, bead-blasted metal, soft-touch polymer, precise part lines, engineering prototype photo"),
]


class InputSpec(BaseModel):
    name: str
    kind: str  # "image" | "mask"
    required: bool = True
    label: str = ""


class ParamSpec(BaseModel):
    name: str
    kind: str  # "text" | "number" | "select" | "preset" | "seed"
    label: str
    default: Any = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[Any] | None = None


class Workflow(BaseModel):
    id: str
    name: str
    description: str
    output: str  # "image" | "mesh" | "video"
    inputs: list[InputSpec] = Field(default_factory=list)
    params: list[ParamSpec] = Field(default_factory=list)
    model: str = ""  # default open model, shown in the UI
    license: str = ""


_SEED = ParamSpec(name="seed", kind="seed", label="Seed", default=-1)
_MODE = ParamSpec(name="mode", kind="select", label="Mode", default="fast", options=["fast", "quality"])


def _count(default: int) -> ParamSpec:
    return ParamSpec(name="count", kind="number", label="Results", default=default, min=1, max=4, step=1)


WORKFLOWS: dict[str, Workflow] = {
    w.id: w
    for w in [
        Workflow(
            id="create",
            name="Create",
            description="Generate new images from a description.",
            output="image",
            params=[
                ParamSpec(name="prompt", kind="text", label="Describe the design", default=""),
                ParamSpec(name="preset", kind="preset", label="Style", default="studio"),
                ParamSpec(name="aspect", kind="select", label="Aspect", default="1:1",
                          options=["1:1", "4:3", "3:2", "16:9", "3:4", "9:16"]),
                _MODE, _count(4), _SEED,
            ],
            model="Z-Image-Turbo / Qwen-Image",
            license="Apache-2.0",
        ),
        Workflow(
            id="render",
            name="Render sketch",
            description="Turn a sketch into colour blocking, a shaded study or a realistic render.",
            output="image",
            inputs=[InputSpec(name="image", kind="image", label="Sketch")],
            params=[
                ParamSpec(name="prompt", kind="text", label="Form, materials and colour", default=""),
                ParamSpec(name="preset", kind="preset", label="Style", default="studio"),
                ParamSpec(name="stage", kind="select", label="Fidelity", default="realistic",
                          options=["color_block", "shaded", "realistic"]),
                ParamSpec(name="influence", kind="number", label="Drawing influence", default=0.75,
                          min=0.0, max=1.0, step=0.05),
                _MODE, _count(4), _SEED,
            ],
            model="Qwen-Image-Edit",
            license="Apache-2.0",
        ),
        Workflow(
            id="edit",
            name="Edit",
            description="Change an image with words. Connect references as @2 and @3. "
                        "A painted mask limits the change to that area.",
            output="image",
            inputs=[
                InputSpec(name="image", kind="image", label="@1"),
                InputSpec(name="ref1", kind="image", label="@2", required=False),
                InputSpec(name="ref2", kind="image", label="@3", required=False),
                InputSpec(name="mask", kind="mask", label="Mask", required=False),
            ],
            params=[
                ParamSpec(name="prompt", kind="text", label="What should change?", default=""),
                _MODE, _count(2), _SEED,
            ],
            model="Qwen-Image-Edit / FLUX.2 klein 4B",
            license="Apache-2.0",
        ),
        Workflow(
            id="new_view",
            name="New view",
            description="See the design from another angle.",
            output="image",
            inputs=[InputSpec(name="image", kind="image", label="Image")],
            params=[
                ParamSpec(name="angle", kind="select", label="Rotate", default=45,
                          options=[45, 90, 135, 180, 225, 270, 315]),
                ParamSpec(name="elevation", kind="select", label="Camera", default="eye",
                          options=["low", "eye", "high", "top"]),
                _MODE, _count(2), _SEED,
            ],
            model="Qwen-Image-Edit",
            license="Apache-2.0",
        ),
        Workflow(
            id="style",
            name="Style transfer",
            description="Restyle an image with the look of a reference. A few words about the style or light "
                        "(e.g. marker sketch, cold winter daylight) make it much more reliable.",
            output="image",
            inputs=[
                InputSpec(name="image", kind="image", label="Image"),
                InputSpec(name="style", kind="image", label="Style"),
            ],
            params=[
                ParamSpec(name="transfer", kind="select", label="Take from the style", default="full",
                          options=["full", "colours_materials", "rendering", "lighting_mood"]),
                ParamSpec(name="prompt", kind="text", label="Describe the style or light (recommended)", default=""),
                _MODE, _count(2), _SEED,
            ],
            model="FLUX.2 klein 4B / Qwen-Image-Edit",
            license="Apache-2.0",
        ),
        Workflow(
            id="erase",
            name="Erase object",
            description="Paint a mask over anything (Draw → Mask) and it is removed and filled with background.",
            output="image",
            inputs=[
                InputSpec(name="image", kind="image", label="Image"),
                InputSpec(name="mask", kind="mask", label="Mask"),
            ],
            params=[
                ParamSpec(name="prompt", kind="text", label="What should be there instead? (optional)", default=""),
                _MODE, _count(1), _SEED,
            ],
            model="FLUX.2 klein 4B (inpaint)",
            license="Apache-2.0",
        ),
        Workflow(
            id="outpaint",
            name="Outpaint",
            description="Extend the image beyond its edges. Drag the frame around the image to set the new canvas.",
            output="image",
            inputs=[InputSpec(name="image", kind="image", label="Image")],
            params=[
                ParamSpec(name="prompt", kind="text", label="Describe the surroundings (recommended)", default=""),
                ParamSpec(name="left", kind="number", label="Left (px)", default=0, min=0, max=4096, step=8),
                ParamSpec(name="top", kind="number", label="Top (px)", default=0, min=0, max=4096, step=8),
                ParamSpec(name="right", kind="number", label="Right (px)", default=256, min=0, max=4096, step=8),
                ParamSpec(name="bottom", kind="number", label="Bottom (px)", default=0, min=0, max=4096, step=8),
                _MODE, _count(1), _SEED,
            ],
            model="FLUX.2 klein 4B (inpaint)",
            license="Apache-2.0",
        ),
        Workflow(
            id="animate",
            name="Animate",
            description="Make a short video from a start frame, optionally ending on a second frame.",
            output="video",
            inputs=[
                InputSpec(name="image", kind="image", label="Start"),
                InputSpec(name="end", kind="image", label="End", required=False),
            ],
            params=[
                ParamSpec(name="prompt", kind="text", label="Describe the motion", default=""),
                ParamSpec(name="motion", kind="select", label="Motion", default="custom",
                          options=["custom", "turntable", "push_in", "reveal", "orbit"]),
                ParamSpec(name="duration", kind="select", label="Seconds", default=5, options=[3, 5]),
                _MODE, _SEED,
            ],
            model="Wan 2.2 (TI2V-5B / A14B)",
            license="Apache-2.0",
        ),
        Workflow(
            id="remove_bg",
            name="Remove background",
            description="Cut the product out onto a transparent background.",
            output="image",
            inputs=[InputSpec(name="image", kind="image", label="Image")],
            model="BiRefNet",
            license="MIT",
        ),
        Workflow(
            id="upscale",
            name="Upscale",
            description="Enlarge for presentation and print.",
            output="image",
            inputs=[InputSpec(name="image", kind="image", label="Image")],
            params=[ParamSpec(name="scale", kind="select", label="Scale", default=2, options=[2, 4])],
            model="Real-ESRGAN x4plus",
            license="BSD-3-Clause",
        ),
    ]
}

MOTION_PROMPTS = {
    "turntable": "the product rotates slowly a full turn on a turntable, camera fixed, studio lighting, "
                 "keep the shape, colours and details unchanged",
    "push_in": "slow cinematic camera push-in towards the product, subtle parallax, keep the design unchanged",
    "reveal": "dramatic light sweep reveals the product from darkness, camera slowly moves, design unchanged",
    "orbit": "camera orbits smoothly around the product at eye level, keep the design unchanged",
}

STAGE_PROMPTS = {
    "color_block": "Turn this sketch into a clean colour-blocking design rendering with flat colour fills and "
                   "simple tonal separation, keep the line work.",
    "shaded": "Turn this sketch into a shaded design rendering with highlights and shadows that describe the "
              "surfaces, marker rendering style.",
    "realistic": "Turn this sketch into a photorealistic product render.",
}

ASPECTS = {"1:1": (1024, 1024), "4:3": (1152, 864), "3:2": (1216, 832), "16:9": (1344, 768),
           "3:4": (864, 1152), "9:16": (768, 1344)}


def catalogue() -> dict:
    return {
        "workflows": [w.model_dump() for w in WORKFLOWS.values()],
        "presets": [p.model_dump() for p in PRESETS],
    }


def preset_prompt(preset_id: str | None) -> str:
    for p in PRESETS:
        if p.id == preset_id:
            return p.prompt
    return ""
