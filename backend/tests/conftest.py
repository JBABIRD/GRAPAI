import io
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from ductus.api import create_app
from ductus.config import Settings


@pytest.fixture()
def client(tmp_path):
    cfg = Settings()
    cfg.provider = "mock"
    cfg.data_dir = tmp_path
    return TestClient(create_app(cfg))


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def sketch() -> Image.Image:
    img = Image.new("RGB", (400, 300), "white")
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([60, 120, 340, 230], radius=40, outline="black", width=4)
    d.ellipse([140, 70, 260, 150], outline="black", width=4)
    return img


def upload(client, img: Image.Image) -> str:
    r = client.post("/api/assets", files={"file": ("a.png", png_bytes(img), "image/png")})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def wait(client, job_id: str, timeout: float = 60) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.05)
    raise TimeoutError(job_id)
