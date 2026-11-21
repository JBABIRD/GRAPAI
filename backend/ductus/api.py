"""HTTP API for the Ductus web app."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .boards import BoardStore
from .config import Settings, settings as default_settings
from .jobs import JobManager, JobValidationError
from .providers import describe_all
from .storage import AssetStore
from .workflows import catalogue

MAX_UPLOAD = 64 * 1024 * 1024
ALLOWED_UPLOAD = {"image/png", "image/jpeg", "image/webp", "video/mp4"}


class JobRequest(BaseModel):
    workflow: str
    inputs: dict[str, str | None] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)


class BoardCreate(BaseModel):
    name: str = "Untitled board"


def create_app(cfg: Settings | None = None) -> FastAPI:
    cfg = cfg or default_settings
    logging.basicConfig(level=logging.INFO)
    store = AssetStore(cfg.data_dir / "assets")
    boards = BoardStore(cfg.data_dir / "boards")
    jobs = JobManager(store, max_workers=cfg.max_workers)

    app = FastAPI(title="Ductus", version=__version__)
    app.add_middleware(CORSMiddleware, allow_origins=cfg.cors_origins, allow_methods=["*"], allow_headers=["*"])
    app.state.store, app.state.jobs, app.state.boards = store, jobs, boards

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__, "provider": cfg.provider, "providers": describe_all()}

    @app.get("/api/workflows")
    def workflows():
        return catalogue()

    @app.post("/api/assets")
    async def upload(file: UploadFile = File(...)):
        mime = (file.content_type or "").split(";")[0]
        if mime not in ALLOWED_UPLOAD:
            raise HTTPException(415, f"unsupported file type {mime or 'unknown'}")
        data = await file.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "file too large")
        try:
            return store.put_bytes(data, mime).to_dict()
        except Exception as exc:
            raise HTTPException(400, f"could not read file: {exc}") from exc

    @app.get("/api/assets/{asset_id}")
    def asset(asset_id: str):
        a = store.get(asset_id)
        if a is None:
            raise HTTPException(404, "asset not found")
        return FileResponse(a.path, media_type=a.mime, headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @app.post("/api/jobs")
    def submit(req: JobRequest):
        try:
            job = jobs.submit(req.workflow, {k: v for k, v in req.inputs.items() if v}, req.params)
        except JobValidationError as exc:
            raise HTTPException(422, str(exc)) from exc
        return job.to_dict()

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        j = jobs.get(job_id)
        if j is None:
            raise HTTPException(404, "job not found")
        return j.to_dict()

    @app.get("/api/boards")
    def list_boards():
        return boards.list()

    @app.post("/api/boards")
    def create_board(body: BoardCreate):
        return boards.create(body.name)

    @app.get("/api/boards/{board_id}")
    def get_board(board_id: str):
        try:
            doc = boards.get(board_id)
        except KeyError:
            doc = None
        if doc is None:
            raise HTTPException(404, "board not found")
        return doc

    @app.put("/api/boards/{board_id}")
    def save_board(board_id: str, doc: dict[str, Any]):
        try:
            return {"id": board_id, "updated": boards.save(board_id, doc)["updated"]}
        except KeyError as exc:
            raise HTTPException(400, "bad board id") from exc

    @app.delete("/api/boards/{board_id}")
    def delete_board(board_id: str):
        try:
            return {"deleted": boards.delete(board_id)}
        except KeyError as exc:
            raise HTTPException(400, "bad board id") from exc

    # Serve the built web app when it exists (single-container deploy).
    web = Path(os.environ.get("DUCTUS_WEB_DIR", Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"))
    if web.exists():
        app.mount("/", StaticFiles(directory=web, html=True), name="web")

    return app


app = create_app()
