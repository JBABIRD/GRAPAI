"""Boards: the infinite canvas documents, stored as JSON."""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path

_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class BoardStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, board_id: str) -> Path:
        if not _ID.match(board_id):
            raise KeyError(board_id)
        return self.root / f"{board_id}.json"

    def list(self) -> list[dict]:
        out = []
        for p in sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                doc = json.loads(p.read_text())
            except json.JSONDecodeError:
                continue
            out.append({"id": doc["id"], "name": doc.get("name", "Untitled"), "updated": doc.get("updated"),
                        "items": len(doc.get("nodes", []))})
        return out

    def create(self, name: str = "Untitled board") -> dict:
        doc = {"id": uuid.uuid4().hex[:12], "name": name, "nodes": [], "edges": [],
               "viewport": {"x": 0, "y": 0, "zoom": 1}, "updated": time.time()}
        self.save(doc["id"], doc)
        return doc

    def get(self, board_id: str) -> dict | None:
        p = self._path(board_id)
        return json.loads(p.read_text()) if p.exists() else None

    def save(self, board_id: str, doc: dict) -> dict:
        doc = {**doc, "id": board_id, "updated": time.time()}
        with self._lock:
            tmp = self._path(board_id).with_suffix(".tmp")
            tmp.write_text(json.dumps(doc))
            tmp.replace(self._path(board_id))
        return doc

    def delete(self, board_id: str) -> bool:
        p = self._path(board_id)
        if p.exists():
            p.unlink()
            return True
        return False
