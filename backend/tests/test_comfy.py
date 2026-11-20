import json
from pathlib import Path

from PIL import Image

from ductus.providers import comfy
from ductus.providers.base import JobInput

TEMPLATES = Path(__file__).resolve().parent.parent / "comfy_workflows"


def test_templates_are_valid_graphs():
    for path in TEMPLATES.glob("*.json"):
        graph = json.loads(path.read_text())
        assert "_meta" in graph
        nodes = {k: v for k, v in graph.items() if k != "_meta"}
        for nid, node in nodes.items():
            assert "class_type" in node, (path.name, nid)
            for val in node["inputs"].values():
                if isinstance(val, list):
                    assert str(val[0]) in nodes, (path.name, nid, val)
        assert any(n["class_type"] in ("SaveImage", "SaveVideo") for n in nodes.values()), path.name


def test_fill_prunes_missing_optional_inputs():
    graph = json.loads((TEMPLATES / "edit_fast.json").read_text())
    filled = comfy.fill_template(graph, {"image": "a.png", "prompt": "make it red", "negative": " ", "seed": 5,
                                         "ref1": None, "ref2": None})
    assert "_meta" not in filled
    assert "11" not in filled and "12" not in filled
    enc = filled["20"]["inputs"]
    assert "image2" not in enc and "image3" not in enc and enc["prompt"] == "make it red"
    assert filled["30"]["inputs"]["seed"] == 5


def test_edit_provider_against_fake_server(monkeypatch):
    sent = {}

    class FakeClient:
        def upload_image(self, image, hint):
            return f"{hint}.png"

        def run(self, graph, progress=None):
            sent["graph"] = graph
            return [{"filename": "out.png", "subfolder": "", "type": "output"}]

        def fetch(self, f):
            import io
            buf = io.BytesIO()
            Image.new("RGB", (64, 64), "blue").save(buf, format="PNG")
            return buf.getvalue()

    p = comfy.ComfyEdit()
    p.client = FakeClient()
    src = Image.new("RGB", (64, 64), "white")
    mask = Image.new("L", (64, 64), 0)
    mask.paste(255, (0, 0, 16, 16))
    outs = p.run(JobInput(images={"image": src, "ref1": src, "mask": mask},
                          params={"prompt": "@1 in the colour of @2", "mode": "quality", "count": 1, "seed": 1}))
    g = sent["graph"]
    assert g["20"]["inputs"]["prompt"].startswith("Picture 1 in the colour of Picture 2")
    assert g["11"]["inputs"]["image"] == "ref1.png" and "12" not in g
    assert outs[0].image.getpixel((2, 2))[2] > 200      # inside mask: edited
    assert outs[0].image.getpixel((60, 60)) == (255, 255, 255)  # outside: original


def test_animate_picks_keyframe_graph(monkeypatch):
    class FakeClient:
        def upload_image(self, image, hint):
            return f"{hint}.png"

    p = comfy.ComfyAnimate()
    p.client = FakeClient()
    img = Image.new("RGB", (800, 600))
    job = JobInput(images={"image": img, "end": img}, params={"mode": "fast", "duration": 5})
    assert p.template_name(job) == "animate_quality"
    v = p.values(job)
    assert (v["length"] - 1) % 4 == 0 and v["width"] % 32 == 0 and v["height"] % 32 == 0
    job2 = JobInput(images={"image": img}, params={"mode": "fast", "duration": 5})
    assert p.template_name(job2) == "animate_fast"
