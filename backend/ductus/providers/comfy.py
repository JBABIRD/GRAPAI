"""ComfyUI backend: runs the open-weight models through a ComfyUI server.

Each workflow has API-format graph templates in ``comfy_workflows/``
(``<workflow>_<mode>.json``). String values written as ``{{name}}`` are
filled in at run time. A node whose placeholder has no value (an optional
reference image, say) is removed, together with every input that pointed at
it, so one template covers both "with" and "without" a reference.

You can replace any template with your own: build the graph in ComfyUI,
export it with "Export (API)", and put the placeholders in.
"""

from __future__ import annotations

import copy
import io
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import httpx
import numpy as np
from PIL import Image, ImageFilter, ImageOps

from ..config import settings
from ..workflows import ASPECTS
from . import imaging, prompts
from .base import JobInput, Output, Provider

_PLACEHOLDER = re.compile(r"^\{\{(\w+)\}\}$")


class ComfyError(RuntimeError):
    pass


def fill_template(graph: dict, values: dict[str, Any]) -> dict:
    """Substitute {{name}} placeholders and prune nodes whose placeholder is unset."""
    graph = copy.deepcopy(graph)
    meta = graph.pop("_meta", None) or {}
    dropped: set[str] = set()
    # Optional chains: when a value is missing, drop its nodes and bypass the
    # nodes that merged it in (e.g. a ReferenceLatent passes its conditioning on).
    alias: dict[str, list] = {}
    for name, spec in (meta.get("optional") or {}).items():
        if values.get(name) is not None:
            continue
        for nid in spec.get("drop", []):
            graph.pop(str(nid), None)
        for nid, through in (spec.get("bypass") or {}).items():
            node = graph.pop(str(nid), None)
            if node is not None:
                alias[str(nid)] = node["inputs"][through]

    def resolve(link):
        seen = 0
        while isinstance(link, list) and len(link) == 2 and str(link[0]) in alias and seen < 64:
            link, seen = alias[str(link[0])], seen + 1
        return link

    if alias:
        for node in graph.values():
            for key, val in list(node.get("inputs", {}).items()):
                node["inputs"][key] = resolve(val)
    for node_id, node in graph.items():
        for key, val in list(node.get("inputs", {}).items()):
            if isinstance(val, str):
                m = _PLACEHOLDER.match(val)
                if m:
                    name = m.group(1)
                    if values.get(name) is None:
                        dropped.add(node_id)
                    else:
                        node["inputs"][key] = values[name]
                elif "{{" in val:
                    node["inputs"][key] = re.sub(r"\{\{(\w+)\}\}", lambda mm: str(values.get(mm.group(1), "")), val)
    # Removing a node can orphan nodes that only fed into it; keep pruning
    # links until stable. Links are [node_id, output_index].
    changed = True
    while changed:
        changed = False
        for node_id in list(graph):
            if node_id in dropped:
                graph.pop(node_id)
                changed = True
                continue
            for key, val in list(graph[node_id]["inputs"].items()):
                if isinstance(val, list) and len(val) == 2 and str(val[0]) in dropped:
                    del graph[node_id]["inputs"][key]
                    changed = True
    return graph


class ComfyClient:
    def __init__(self, base_url: str | None = None, timeout: float | None = None):
        self.base_url = (base_url or settings.comfy_url).rstrip("/")
        self.timeout = timeout or settings.comfy_timeout
        self.client_id = uuid.uuid4().hex

    def upload_image(self, image: Image.Image, name_hint: str) -> str:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        files = {"image": (f"ductus_{name_hint}_{uuid.uuid4().hex[:8]}.png", buf.getvalue(), "image/png")}
        r = httpx.post(f"{self.base_url}/upload/image", files=files, data={"overwrite": "true"}, timeout=60)
        r.raise_for_status()
        info = r.json()
        return f"{info['subfolder']}/{info['name']}" if info.get("subfolder") else info["name"]

    def run(self, graph: dict, progress=lambda p, m="": None) -> list[dict]:
        r = httpx.post(f"{self.base_url}/prompt", json={"prompt": graph, "client_id": self.client_id}, timeout=60)
        if r.status_code != 200:
            raise ComfyError(f"ComfyUI rejected the workflow: {r.text[:800]}")
        prompt_id = r.json()["prompt_id"]
        started = time.time()
        while True:
            if time.time() - started > self.timeout:
                raise ComfyError("ComfyUI timed out")
            h = httpx.get(f"{self.base_url}/history/{prompt_id}", timeout=30).json()
            if prompt_id in h:
                entry = h[prompt_id]
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise ComfyError(f"ComfyUI failed: {json.dumps(status.get('messages', []))[:800]}")
                files = []
                for node_out in entry.get("outputs", {}).values():
                    for items in node_out.values():
                        if isinstance(items, list):
                            files += [it for it in items if isinstance(it, dict) and "filename" in it]
                return files
            progress(min(0.9, (time.time() - started) / 120), "generating")
            time.sleep(1.0)

    def fetch(self, file: dict) -> bytes:
        params = {"filename": file["filename"], "subfolder": file.get("subfolder", ""), "type": file.get("type", "output")}
        r = httpx.get(f"{self.base_url}/view", params=params, timeout=300)
        r.raise_for_status()
        return r.content


def load_template(name: str, profile: str = "") -> dict:
    """A profile folder (e.g. comfy_workflows/laptop/) overrides the default graph."""
    root = Path(settings.comfy_workflows)
    for path in ([root / profile / f"{name}.json"] if profile else []) + [root / f"{name}.json"]:
        if path.exists():
            return json.loads(path.read_text())
    raise ComfyError(f"missing ComfyUI template {name}.json (profile {profile or 'default'})")


class ComfyProvider(Provider):
    backend = "comfy"
    template_base = ""

    def __init__(self):
        # Tests inject a fake here; otherwise a client is made per job so each
        # mode can go to its own server.
        self.client: Any = None
        self.template_meta: dict = {}

    def mode(self, job: JobInput) -> str:
        return str(job.params.get("mode", "fast"))

    def target(self, job: JobInput) -> tuple[str, str]:
        return settings.comfy_target(self.workflow, self.mode(job))

    def prepare(self, job: JobInput) -> dict:
        """Pick server and graph for this job; returns the template."""
        url, profile = self.target(job)
        if self.client is None or getattr(self.client, "base_url", url) != url:
            self.client = ComfyClient(url)
        template = load_template(self.template_name(job), profile)
        self.template_meta = template.get("_meta", {})
        return template

    def template_name(self, job: JobInput) -> str:
        return f"{self.template_base}_{self.mode(job)}"

    def values(self, job: JobInput) -> dict[str, Any]:  # pragma: no cover - per workflow
        raise NotImplementedError

    def run_images(self, job: JobInput, count_key: str = "count", prepared: Callable[[], dict] | None = None) -> list[Output]:
        template = self.prepare(job)
        base_values = prepared() if prepared else self.values(job)
        count, seed = int(job.params.get(count_key, 1) or 1), job.seed()
        outs: list[Output] = []
        for i in range(count):
            job.progress(i / count, f"generating {i + 1}/{count}")
            graph = fill_template(template, {**base_values, "seed": seed + i})
            for f in self.client.run(graph, lambda p, m="": job.progress((i + p) / count, m)):
                if f["filename"].lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    img = Image.open(io.BytesIO(self.client.fetch(f)))
                    img.load()
                    outs.append(Output(image=img, meta={"seed": seed + i}))
        return outs

    def run(self, job: JobInput) -> list[Output]:
        return self.run_images(job)


def _upload_inputs(client: ComfyClient, job: JobInput, names: list[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for n in names:
        img = job.images.get(n)
        out[n] = client.upload_image(imaging.flatten(img), n) if img is not None else None
    return out


def _megapixel_size(job: JobInput, megapixels: float = 1.0, multiple: int = 16) -> dict[str, int]:
    """Output size for graphs that need one (FLUX.2): the input's aspect at ~1 MP."""
    return _size_for(job.images["image"].size, megapixels, multiple)


def _size_for(size: tuple[int, int], megapixels: float = 1.0, multiple: int = 16) -> dict[str, int]:
    w, h = size
    k = (megapixels * 1024 * 1024 / max(1, w * h)) ** 0.5
    return {"width": max(multiple, round(w * k / multiple) * multiple),
            "height": max(multiple, round(h * k / multiple) * multiple)}


class ComfyCreate(ComfyProvider):
    workflow, template_base, model = "create", "create", "Z-Image-Turbo / Qwen-Image"

    def values(self, job: JobInput) -> dict[str, Any]:
        w, h = ASPECTS.get(str(job.params.get("aspect", "1:1")), (1024, 1024))
        return {"prompt": prompts.create_prompt(job.params), "negative": prompts.NEGATIVE, "width": w, "height": h}


class ComfyEdit(ComfyProvider):
    workflow, template_base, model = "edit", "edit", "Qwen-Image-Edit-2511"

    def values(self, job: JobInput) -> dict[str, Any]:
        files = _upload_inputs(self.client, job, ["image", "ref1", "ref2"])
        n_refs = sum(1 for k in ("ref1", "ref2") if files.get(k))
        return {"prompt": prompts.edit_prompt(job.params, n_refs), "negative": " ", **files, **_megapixel_size(job)}

    def run(self, job: JobInput) -> list[Output]:
        outs = self.run_images(job)
        mask = job.images.get("mask")
        if mask is not None:
            # Region edit: keep everything outside the painted mask untouched.
            src = imaging.flatten(job.images["image"])
            soft = imaging.feather(imaging.mask_from_image(mask, src.size), 6)
            for o in outs:
                o.image = Image.composite(o.image.convert("RGB").resize(src.size, Image.LANCZOS), src, soft)
        return outs


class ComfyRender(ComfyEdit):
    workflow, template_base, model = "render", "edit", "Qwen-Image-Edit-2511"

    def values(self, job: JobInput) -> dict[str, Any]:
        files = _upload_inputs(self.client, job, ["image"])
        return {"prompt": prompts.render_prompt(job.params), "negative": " ", **files, "ref1": None, "ref2": None,
                **_megapixel_size(job)}


class ComfyNewView(ComfyEdit):
    workflow, template_base, model = "new_view", "edit", "Qwen-Image-Edit-2511"

    def values(self, job: JobInput) -> dict[str, Any]:
        files = _upload_inputs(self.client, job, ["image"])
        return {"prompt": prompts.new_view_prompt(job.params), "negative": " ", **files, "ref1": None, "ref2": None,
                **_megapixel_size(job)}


class ComfyAnimate(ComfyProvider):
    workflow, template_base, model = "animate", "animate", "Wan 2.2"

    def mode(self, job: JobInput) -> str:
        # Only the A14B graph supports an end frame.
        return "quality" if job.images.get("end") is not None else str(job.params.get("mode", "fast"))

    def values(self, job: JobInput) -> dict[str, Any]:
        start = job.images["image"]
        quality = self.mode(job) == "quality"
        video = {"fps": 16, "long": 832, "short": 480} if quality else {"fps": 24, "long": 1280, "short": 704}
        video.update(self.template_meta.get("video", {}))  # lighter profiles shrink this
        fps = int(video["fps"])
        seconds = min(float(job.params.get("duration", 5)), float(video.get("max_seconds", 10)))
        # Wan wants frame counts of 4n+1 and sizes divisible by 32.
        frames = int(seconds * fps) // 4 * 4 + 1
        long_side, short_side = int(video["long"]), int(video["short"])
        w, h = (long_side, short_side) if start.width >= start.height else (short_side, long_side)
        # Wan crops the frame to the video's aspect; pad instead so the whole product stays in shot.
        framed = {k: imaging.pad_to_aspect(imaging.flatten(img), w / h)
                  for k, img in job.images.items() if k in ("image", "end") and img is not None}
        files = {n: (self.client.upload_image(framed[n], n) if n in framed else None) for n in ("image", "end")}
        return {"prompt": prompts.animate_prompt(job.params), "negative": prompts.VIDEO_NEGATIVE,
                "width": w, "height": h, "length": frames, "fps": fps, **files}

    def run(self, job: JobInput) -> list[Output]:
        template = self.prepare(job)
        graph = fill_template(template, {**self.values(job), "seed": job.seed()})
        outs = []
        for f in self.client.run(graph, job.progress):
            if f["filename"].lower().endswith((".mp4", ".webm", ".mov")):
                outs.append(Output(data=self.client.fetch(f), mime="video/mp4", preview=imaging.flatten(job.images["image"])))
        if not outs:
            raise ComfyError("ComfyUI returned no video")
        return outs


class ComfyInpaint(ComfyProvider):
    """True inpainting with FLUX.2 klein: only the masked area is generated, the whole image is the
    model's reference, and unmasked pixels stay exact."""

    backend, template_base = "comfy", "inpaint"

    def inpaint(self, job: JobInput, image: Image.Image, hole: Image.Image, prompt: str,
                grow: int, blur: float, reference: Image.Image | None = None) -> list[Image.Image]:
        """Fill the white part of `hole` (full-res, binary) in `image`. `grow`/`blur` are in pixels at
        the model's working size (~1 MP), so they behave the same for any input size."""
        template = self.prepare(job)
        size = _size_for(image.size, float(self.template_meta.get("megapixels", 1.0)))
        work = image.resize((size["width"], size["height"]), Image.LANCZOS)
        m = hole.resize(work.size, Image.BILINEAR).point(lambda v: 255 if v > 127 else 0)
        if grow > 1:
            m = m.filter(ImageFilter.MaxFilter(grow | 1))
        soft = m.filter(ImageFilter.GaussianBlur(blur)) if blur > 0 else m
        # LoadImageMask reads the red channel: the mask must go up as RGB, not L.
        img_name = self.client.upload_image(work, "image")
        mask_name = self.client.upload_image(soft.convert("RGB"), "mask")
        if reference is None:
            ref_name = img_name
        else:
            rs = _size_for(reference.size, float(self.template_meta.get("megapixels", 1.0)))
            ref_name = self.client.upload_image(reference.resize((rs["width"], rs["height"]), Image.LANCZOS), "reference")
        full_soft = soft.resize(image.size, Image.BILINEAR)
        count, seed = int(job.params.get("count", 1) or 1), job.seed()
        outs: list[Image.Image] = []
        for i in range(count):
            job.progress(i / count, f"generating {i + 1}/{count}")
            graph = fill_template(template, {"prompt": prompt, "image": img_name, "mask": mask_name, "reference": ref_name,
                                             "seed": seed + i, **size})
            for f in self.client.run(graph, lambda p, m="": job.progress((i + p) / count, m)):
                if f["filename"].lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    out = Image.open(io.BytesIO(self.client.fetch(f)))
                    out.load()
                    out = out.convert("RGB").resize(image.size, Image.LANCZOS)
                    # Only the masked area changes; the rest stays pixel-exact at full resolution.
                    outs.append(Image.composite(out, image, full_soft))
        return outs


class ComfyErase(ComfyInpaint):
    """Erase: the original (no prefill, or klein copies the blur) with the grown, softened mask."""

    workflow, model = "erase", "FLUX.2 klein 4B (inpaint)"

    def run(self, job: JobInput) -> list[Output]:
        src = imaging.flatten(job.images["image"])
        hole = imaging.fill_enclosed(imaging.mask_from_image(job.images["mask"], src.size))
        box = imaging.mask_box(hole, margin=1.5, min_side=int(min(src.size) * 0.6))
        if box is None:
            raise ValueError("The mask is empty: paint over the object to erase first")
        crop = src.crop(box)
        # Grow/blur were tuned on the whole image at ~1 MP; the crop is magnified more, so scale them
        # to cover the same part of the object's edge.
        k = ((src.width * src.height) / max(1, crop.width * crop.height)) ** 0.5
        grow, blur = min(61, int(15 * k)), min(30.0, 8 * k)
        outs = []
        for patch in self.inpaint(job, crop, hole.crop(box), prompts.erase_prompt(job.params), grow=grow, blur=blur):
            full = src.copy()
            full.paste(patch, box[:2])
            outs.append(Output(image=full, meta={"seed": job.seed()}))
        return outs


class ComfyOutpaint(ComfyInpaint):
    """Outpaint: edge-extend the image onto the bigger canvas and inpaint the new area, overlapping the
    original a little so the join is generated with its surroundings."""

    workflow, model = "outpaint", "FLUX.2 klein 4B (inpaint)"

    def run(self, job: JobInput) -> list[Output]:
        src = imaging.flatten(job.images["image"])
        left, top, right, bottom = imaging.outpaint_pads(job.params, src.size)
        arr = np.pad(np.asarray(src), ((top, bottom), (left, right), (0, 0)), mode="edge")
        canvas = Image.fromarray(arr)
        hole = Image.new("L", canvas.size, 255)
        hole.paste(0, (left, top, left + src.width, top + src.height))
        outs = self.inpaint(job, canvas, hole, prompts.outpaint_prompt(job.params), grow=2 * 24 + 1, blur=10)
        # Reference = the padded canvas. Tested: the unpadded original as reference duplicated the
        # subject or left a sky rectangle; the scene description is what fixes weak fills.
        return [Output(image=o, meta={"seed": job.seed()}) for o in outs]
