import pytest
import json
from pathlib import Path

from PIL import Image, ImageDraw

from ductus.providers import comfy
from ductus.providers.base import JobInput

TEMPLATES = Path(__file__).resolve().parent.parent / "comfy_workflows"


def test_templates_are_valid_graphs():
    for path in TEMPLATES.rglob("*.json"):
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


def test_laptop_klein_prunes_reference_chains():
    graph = json.loads((TEMPLATES / "laptop" / "edit_fast.json").read_text())
    filled = comfy.fill_template(graph, {"image": "a.png", "prompt": "p", "seed": 1, "width": 1024, "height": 768,
                                         "ref1": None, "ref2": None})
    for gone in ("11", "12", "15", "16", "17", "18", "21", "22"):
        assert gone not in filled
    assert filled["35"]["inputs"]["conditioning"] == ["20", 0]  # bypassed straight to the first reference
    with_ref = comfy.fill_template(graph, {"image": "a.png", "ref1": "b.png", "prompt": "p", "seed": 1,
                                           "width": 1024, "height": 768, "ref2": None})
    assert with_ref["35"]["inputs"]["conditioning"] == ["21", 0] and "16" in with_ref
    for node in with_ref.values():
        for v in node["inputs"].values():
            if isinstance(v, list):
                assert v[0] in with_ref


def test_hybrid_routing(monkeypatch):
    from ductus.config import settings

    monkeypatch.setenv("DUCTUS_COMFY_URL", "http://cloud:8188")
    monkeypatch.setenv("DUCTUS_COMFY_URL_FAST", "http://laptop:8188/")
    monkeypatch.setenv("DUCTUS_COMFY_PROFILE_FAST", "laptop")
    monkeypatch.setenv("DUCTUS_COMFY_URL_ANIMATE", "http://cloud:8188")
    monkeypatch.setenv("DUCTUS_COMFY_PROFILE_ANIMATE", "")
    monkeypatch.setattr(settings, "comfy_url", "http://cloud:8188")
    assert settings.comfy_target("edit", "fast") == ("http://laptop:8188", "laptop")
    assert settings.comfy_target("edit", "quality") == ("http://cloud:8188", "")
    assert settings.comfy_target("animate", "fast")[0] == "http://cloud:8188"


def test_laptop_profile_shrinks_video(monkeypatch):
    from ductus.config import settings

    monkeypatch.setattr(settings, "comfy_target", lambda w, m: ("http://x", "laptop"))

    class FakeClient:
        base_url = "http://x"

        def upload_image(self, image, hint):
            return f"{hint}.png"

    p = comfy.ComfyAnimate()
    p.client = FakeClient()
    job = JobInput(images={"image": Image.new("RGB", (1600, 900))}, params={"mode": "fast", "duration": 5})
    p.prepare(job)
    v = p.values(job)
    assert (v["width"], v["height"]) == (832, 480)
    assert v["length"] == 73  # 3 s cap at 24 fps, 4n+1


def test_animate_pads_square_frames_instead_of_cropping(monkeypatch):
    from ductus.config import settings

    monkeypatch.setattr(settings, "comfy_target", lambda w, m: ("http://x", "laptop"))
    uploaded = {}

    class FakeClient:
        base_url = "http://x"

        def upload_image(self, image, hint):
            uploaded[hint] = image
            return f"{hint}.png"

    p = comfy.ComfyAnimate()
    p.client = FakeClient()
    job = JobInput(images={"image": Image.new("RGB", (1024, 1024), "white")}, params={"mode": "fast", "duration": 3})
    p.prepare(job)
    v = p.values(job)
    img = uploaded["image"]
    assert abs(img.width / img.height - v["width"] / v["height"]) < 0.01
    assert img.height == 1024  # nothing cropped, sides padded


class _BlueServer:
    def __init__(self):
        self.uploads = {}
        self.graph = None

    def upload_image(self, image, hint):
        self.uploads[hint] = image
        return f"{hint}.png"

    def run(self, graph, progress=None):
        self.graph = graph
        return [{"filename": "out.png", "subfolder": "", "type": "output"}]

    def fetch(self, f):
        import io
        buf = io.BytesIO()
        Image.new("RGB", (256, 256), "blue").save(buf, format="PNG")
        return buf.getvalue()


def test_erase_crops_around_mask_and_keeps_the_rest():
    srv = _BlueServer()
    p = comfy.ComfyErase()
    p.client = srv
    src = Image.new("RGB", (1600, 1200), "white")
    mask = Image.new("L", src.size, 0)
    mask.paste(255, (700, 500, 800, 600))
    outs = p.run(JobInput(images={"image": src, "mask": mask}, params={"mode": "fast", "count": 1, "seed": 1}))
    sent = srv.uploads["image"]
    assert abs(sent.size[0] / sent.size[1] - 1.0) < 0.05  # a square crop around the mask, not the 4:3 frame
    assert srv.graph["5"]["inputs"]["text"].startswith("Remove the masked object")
    assert srv.uploads["mask"].mode == "RGB"  # LoadImageMask reads the red channel
    assert srv.graph["32"]["inputs"]["width"] == sent.size[0]
    out = outs[0].image
    assert out.size == src.size
    assert out.getpixel((750, 550))[2] > 200 and out.getpixel((750, 550))[0] < 60  # filled by the model
    assert out.getpixel((10, 10)) == (255, 255, 255)  # far away: untouched


def test_outpaint_keeps_original_and_fills_new_area():
    srv = _BlueServer()
    p = comfy.ComfyOutpaint()
    p.client = srv
    src = Image.new("RGB", (800, 600), "white")
    outs = p.run(JobInput(images={"image": src},
                          params={"mode": "fast", "count": 1, "seed": 1, "left": 200, "right": 0, "top": 0, "bottom": 100,
                                  "prompt": "a sandy beach"}))
    out = outs[0].image
    assert out.size == (1000, 700)
    up = srv.uploads["image"].size
    assert abs(up[0] / up[1] - 1000 / 700) < 0.03 and up[0] % 16 == 0 and up[1] % 16 == 0
    assert out.getpixel((20, 300))[2] > 200          # new area from the model
    up_img = srv.uploads["image"]
    assert up_img.getpixel((2, up_img.height // 2)) == (0, 255, 0)  # the LoRA's green canvas
    assert "Fill the green spaces according to the image: a sandy beach." in json.dumps(srv.graph)
    assert srv.graph["4"]["class_type"] == "LoraLoaderModelOnly"
    assert out.getpixel((600, 300)) == (255, 255, 255)  # original pixels back


def test_outpaint_plain_background_needs_no_model():
    srv = _BlueServer()
    p = comfy.ComfyOutpaint()
    p.client = srv
    src = Image.new("RGB", (800, 400), (250, 250, 248))
    ImageDraw.Draw(src).line((0, 300, 800, 120), fill=(40, 40, 40), width=6)  # a line touching the edges
    ImageDraw.Draw(src).rectangle((100, 330, 700, 400), fill=(60, 60, 60))   # subject cut off at the bottom
    outs = p.run(JobInput(images={"image": src},
                          params={"mode": "fast", "count": 1, "seed": 1, "left": 100, "top": 300, "prompt": "nothing"}))
    out = outs[0].image
    assert out.size == (900, 700) and not srv.uploads
    assert out.getpixel((10, 10)) == (250, 250, 248) and out.getpixel((500, 500)) == src.getpixel((400, 200))


def test_outpaint_overlap_spares_a_small_original():
    srv = _BlueServer()
    p = comfy.ComfyOutpaint()
    p.client = srv
    src = Image.new("RGB", (600, 260), "white")
    ImageDraw.Draw(src).rectangle((0, 0, 600, 60), fill="green")  # not a plain border
    outs = p.run(JobInput(images={"image": src},
                          params={"mode": "fast", "count": 1, "seed": 1, "left": 400, "right": 400, "top": 1200, "bottom": 300,
                                  "prompt": "a studio"}))
    out = outs[0].image
    assert out.getpixel((400 + 300, 1200 + 150)) == (255, 255, 255)  # centre of the original stays exact


def test_style_sends_image_and_reference():
    srv = _BlueServer()
    p = comfy.ComfyStyle()
    p.client = srv
    img = Image.new("RGB", (800, 600), "white")
    p.run(JobInput(images={"image": img, "style": Image.new("RGB", (300, 300), "red")},
                   params={"mode": "fast", "count": 1, "seed": 1, "transfer": "rendering"}))
    assert set(srv.uploads) == {"image", "style"}
    text = json.dumps(srv.graph)
    assert "rendering technique of image 2" in text and "only a rendering reference" in text


def test_views_one_run_per_view_same_seed():
    graphs = []

    class Srv(_BlueServer):
        def run(self, graph, progress=None):
            graphs.append(graph)
            return super().run(graph, progress)

    p = comfy.ComfyViews()
    p.client = Srv()
    outs = p.run(JobInput(images={"image": Image.new("RGB", (800, 600), "white")},
                          params={"mode": "fast", "seed": 5, "set": "ortho_4", "scene": "studio"}))
    assert [o.meta["view"] for o in outs] == ["Front", "Left side", "Rear", "Top (approx.)"]
    texts = [json.dumps(g) for g in graphs]
    assert all('"noise_seed": 5' in t or '"seed": 5' in t for t in texts)
    assert "studio backdrop" in texts[0] and "top view" in texts[3]


def test_envswap_keeps_product_and_sends_environment():
    srv = _BlueServer()
    p = comfy.ComfyEnvSwap()
    p.client = srv
    src = Image.new("RGB", (800, 600), (240, 240, 240))
    src.paste((200, 30, 30), (300, 200, 500, 400))  # the "product"
    env = Image.new("RGB", (1200, 500), (20, 120, 40))
    outs = p.run(JobInput(images={"image": src, "environment": env},
                          params={"mode": "fast", "count": 1, "seed": 3, "what": "red box"}))
    out = outs[0].image
    assert out.getpixel((400, 300)) == (200, 30, 30)  # product untouched
    assert out.getpixel((20, 20))[2] > 200             # surroundings generated
    assert "ref1" in srv.uploads and srv.graph["40"]["inputs"]["image"] == "ref1.png"
    assert "red box" in srv.graph["5"]["inputs"]["text"]


def test_inpaint_without_ref1_drops_the_chain():
    srv = _BlueServer()
    p = comfy.ComfyErase()
    p.client = srv
    src = Image.new("RGB", (400, 400), "white")
    mask = Image.new("L", src.size, 0)
    mask.paste(255, (150, 150, 250, 250))
    p.run(JobInput(images={"image": src, "mask": mask}, params={"mode": "fast", "count": 1, "seed": 1}))
    assert "40" not in srv.graph and "42" not in srv.graph
    assert srv.graph["35"]["inputs"]["conditioning"] == ["20", 0]


def test_place_product_shrinks_onto_ground():
    src = Image.new("RGB", (1000, 800), "white")
    src.paste((200, 30, 30), (300, 100, 700, 700))
    alpha = Image.new("L", src.size, 0)
    alpha.paste(255, (300, 100, 700, 700))
    product, a = comfy.place_product(src, alpha, 0.5, "ground")
    x0, y0, x1, y1 = a.getbbox()
    assert (x1 - x0, y1 - y0) == (200, 300)
    assert abs((x0 + x1) / 2 - 500) <= 1 and abs(y1 - 720) <= 1
    assert product.getpixel((500, 600)) == (200, 30, 30)


def test_outpaint_passes_stay_within_lora_training_range():
    steps = comfy.outpaint_passes((1000, 600), (368, 256, 368, 112), 0.25)
    assert len(steps) == 2 and steps[0] == (250, 150, 250, 112)
    assert tuple(map(sum, zip(*steps))) == (368, 256, 368, 112)
    assert comfy.outpaint_passes((800, 600), (200, 0, 0, 100), 0.25) == [(200, 0, 0, 100)]
