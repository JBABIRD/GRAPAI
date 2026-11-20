import io

import pytest
from PIL import Image

from conftest import upload, wait


def test_health_and_catalogue(client):
    assert client.get("/api/health").json()["ok"]
    cat = client.get("/api/workflows").json()
    ids = {w["id"] for w in cat["workflows"]}
    assert {"create", "render", "edit", "animate", "remove_bg", "upscale", "new_view"} <= ids
    assert cat["presets"]


@pytest.mark.parametrize("workflow,params,expect", [
    ("render", {"prompt": "red gloss", "count": 3, "seed": 7}, 3),
    ("render", {"stage": "color_block", "count": 1}, 1),
    ("edit", {"prompt": "make it blue", "count": 2}, 2),
    ("new_view", {"angle": 135, "count": 1}, 1),
    ("remove_bg", {}, 1),
    ("upscale", {"scale": 2}, 1),
])
def test_image_workflows(client, sketch, workflow, params, expect):
    aid = upload(client, sketch)
    r = client.post("/api/jobs", json={"workflow": workflow, "inputs": {"image": aid}, "params": params})
    assert r.status_code == 200, r.text
    job = wait(client, r.json()["id"])
    assert job["status"] == "done", job
    assert len(job["outputs"]) == expect
    out = job["outputs"][0]
    assert out["kind"] == "image"
    img = Image.open(io.BytesIO(client.get(out["asset"]["url"]).content))
    assert img.width > 0
    if workflow == "upscale":
        assert img.size == (sketch.width * 2, sketch.height * 2)
    if workflow == "remove_bg":
        assert img.mode == "RGBA" and img.getpixel((0, 0))[3] == 0


def test_create_needs_no_input(client):
    r = client.post("/api/jobs", json={"workflow": "create", "params": {"prompt": "a yellow drill", "aspect": "16:9", "count": 2}})
    job = wait(client, r.json()["id"])
    assert job["status"] == "done"
    assert [o["asset"]["width"] > o["asset"]["height"] for o in job["outputs"]] == [True, True]


def test_edit_with_mask_keeps_outside(client, sketch):
    aid = upload(client, sketch)
    mask = Image.new("RGBA", sketch.size, (0, 0, 0, 0))
    mask.paste((255, 0, 0, 255), (0, 0, 100, 100))
    mid = upload(client, mask)
    r = client.post("/api/jobs", json={"workflow": "edit", "inputs": {"image": aid, "mask": mid},
                                       "params": {"prompt": "red", "count": 1}})
    job = wait(client, r.json()["id"])
    img = Image.open(io.BytesIO(client.get(job["outputs"][0]["asset"]["url"]).content)).convert("RGB")
    assert img.getpixel((350, 280)) == (255, 255, 255)  # far outside the mask: untouched
    assert img.getpixel((20, 20)) != (255, 255, 255)


def test_animate_returns_mp4(client, sketch):
    a = upload(client, sketch)
    b = upload(client, sketch.transpose(Image.FLIP_LEFT_RIGHT))
    r = client.post("/api/jobs", json={"workflow": "animate", "inputs": {"image": a, "end": b},
                                       "params": {"duration": 3, "motion": "push_in"}})
    job = wait(client, r.json()["id"], timeout=120)
    assert job["status"] == "done", job
    out = job["outputs"][0]
    assert out["kind"] == "video" and out["poster"]["url"]
    data = client.get(out["asset"]["url"]).content
    assert data[4:8] == b"ftyp"


def test_validation(client):
    assert client.post("/api/jobs", json={"workflow": "nope"}).status_code == 422
    assert client.post("/api/jobs", json={"workflow": "edit", "inputs": {}}).status_code == 422
    assert client.post("/api/jobs", json={"workflow": "edit", "inputs": {"image": "deadbeef"}}).status_code == 422
    r = client.post("/api/assets", files={"file": ("a.txt", b"hi", "text/plain")})
    assert r.status_code == 415


def test_boards_roundtrip(client):
    b = client.post("/api/boards", json={"name": "Seat concepts"}).json()
    doc = {"name": "Seat concepts", "nodes": [{"id": "n1", "type": "image", "position": {"x": 1, "y": 2}, "data": {}}], "edges": []}
    assert client.put(f"/api/boards/{b['id']}", json=doc).status_code == 200
    got = client.get(f"/api/boards/{b['id']}").json()
    assert got["nodes"][0]["id"] == "n1"
    assert client.get("/api/boards").json()[0]["items"] == 1
    assert client.get("/api/boards/..%2Fetc").status_code in (400, 404)


def test_erase_fills_only_the_mask(client, sketch):
    aid = upload(client, sketch)
    mask = Image.new("RGBA", sketch.size, (0, 0, 0, 0))
    mask.paste((255, 0, 0, 255), (100, 100, 200, 200))
    mid = upload(client, mask)
    r = client.post("/api/jobs", json={"workflow": "erase", "inputs": {"image": aid, "mask": mid}, "params": {}})
    job = wait(client, r.json()["id"])
    assert job["status"] == "done", job
    img = Image.open(io.BytesIO(client.get(job["outputs"][0]["asset"]["url"]).content)).convert("RGB")
    assert img.size == sketch.size
    assert img.getpixel((5, 5)) == sketch.convert("RGB").getpixel((5, 5))


def test_erase_needs_a_mask(client, sketch):
    aid = upload(client, sketch)
    r = client.post("/api/jobs", json={"workflow": "erase", "inputs": {"image": aid}, "params": {}})
    assert r.status_code in (400, 422)


def test_outpaint_grows_canvas(client, sketch):
    aid = upload(client, sketch)
    r = client.post("/api/jobs", json={"workflow": "outpaint", "inputs": {"image": aid},
                                       "params": {"left": 64, "top": 0, "right": 128, "bottom": 32}})
    job = wait(client, r.json()["id"])
    assert job["status"] == "done", job
    a = job["outputs"][0]["asset"]
    assert (a["width"], a["height"]) == (sketch.width + 192, sketch.height + 32)


def test_outline_mask_selects_inside():
    from PIL import ImageDraw
    from ductus.providers import imaging
    ring = Image.new("L", (200, 200), 0)
    ImageDraw.Draw(ring).ellipse((40, 40, 160, 160), outline=255, width=6)
    filled = imaging.fill_enclosed(ring)
    assert filled.getpixel((100, 100)) == 255 and filled.getpixel((5, 5)) == 0
    open_stroke = Image.new("L", (200, 200), 0)
    ImageDraw.Draw(open_stroke).line((20, 100, 180, 100), fill=255, width=6)
    assert imaging.fill_enclosed(open_stroke).getpixel((100, 60)) == 0


def test_style_transfer_needs_both_images(client, sketch):
    aid = upload(client, sketch)
    ref = Image.new("RGB", (128, 128), (200, 60, 20))
    rid = upload(client, ref)
    r = client.post("/api/jobs", json={"workflow": "style", "inputs": {"image": aid}, "params": {}})
    assert r.status_code in (400, 422)
    r = client.post("/api/jobs", json={"workflow": "style", "inputs": {"image": aid, "style": rid}, "params": {"count": 2}})
    job = wait(client, r.json()["id"])
    assert job["status"] == "done", job
    assert len(job["outputs"]) == 2


def test_views_returns_labelled_set(client, sketch):
    aid = upload(client, sketch)
    r = client.post("/api/jobs", json={"workflow": "views", "inputs": {"image": aid}, "params": {"set": "design_6"}})
    job = wait(client, r.json()["id"])
    assert job["status"] == "done", job
    assert [o["meta"]["view"] for o in job["outputs"]] == ["Front", "Left side", "Rear", "Top", "3/4 front left", "3/4 rear right"]
