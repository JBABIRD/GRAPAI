"""Content storage for uploaded and generated assets (images, meshes, videos)."""

from __future__ import annotations

import io
import json
import mimetypes
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

_EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "model/gltf-binary": ".glb",
    "video/mp4": ".mp4",
}


@dataclass
class Asset:
    id: str
    mime: str
    path: Path
    width: int | None = None
    height: int | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "mime": self.mime,
            "url": f"/api/assets/{self.id}",
            "width": self.width,
            "height": self.height,
        }


class AssetStore:
    """Stores files on local disk. Swap for S3/MinIO in a multi-machine deploy."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _meta_path(self, asset_id: str) -> Path:
        return self.root / f"{asset_id}.json"

    def put_bytes(self, data: bytes, mime: str) -> Asset:
        mime = mime or "application/octet-stream"
        asset_id = uuid.uuid4().hex
        ext = _EXT_BY_MIME.get(mime) or mimetypes.guess_extension(mime) or ".bin"
        path = self.root / f"{asset_id}{ext}"
        width = height = None
        if mime.startswith("image/"):
            with Image.open(io.BytesIO(data)) as im:
                width, height = im.size
        with self._lock:
            path.write_bytes(data)
            asset = Asset(asset_id, mime, path, width, height)
            self._meta_path(asset_id).write_text(
                json.dumps({"mime": mime, "file": path.name, "width": width, "height": height})
            )
        return asset

    def put_image(self, image: Image.Image) -> Asset:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return self.put_bytes(buf.getvalue(), "image/png")

    def get(self, asset_id: str) -> Asset | None:
        if not asset_id.isalnum():
            return None
        meta_path = self._meta_path(asset_id)
        if not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text())
        return Asset(asset_id, meta["mime"], self.root / meta["file"], meta.get("width"), meta.get("height"))

    def open_image(self, asset_id: str, mode: str = "RGBA") -> Image.Image:
        asset = self.get(asset_id)
        if asset is None or not asset.mime.startswith("image/"):
            raise KeyError(f"image asset {asset_id!r} not found")
        with Image.open(asset.path) as im:
            return im.convert(mode)
