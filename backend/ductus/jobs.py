"""In-process job queue. Swap for Redis/RQ when running several API replicas."""

from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from .providers import get_provider
from .providers.base import JobInput
from .storage import AssetStore
from .workflows import WORKFLOWS

log = logging.getLogger("ductus.jobs")


@dataclass
class Job:
    id: str
    workflow: str
    inputs: dict[str, str]
    params: dict[str, Any]
    status: str = "queued"  # queued | running | done | error
    progress: float = 0.0
    message: str = ""
    error: str | None = None
    outputs: list[dict] = field(default_factory=list)
    provider: dict = field(default_factory=dict)
    created: float = field(default_factory=time.time)
    finished: float | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "workflow": self.workflow, "inputs": self.inputs, "params": self.params,
            "status": self.status, "progress": round(self.progress, 3), "message": self.message,
            "error": self.error, "outputs": self.outputs, "provider": self.provider,
            "created": self.created, "finished": self.finished,
        }


class JobValidationError(ValueError):
    pass


class JobManager:
    def __init__(self, store: AssetStore, max_workers: int = 1):
        self.store = store
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ductus-job")

    def submit(self, workflow: str, inputs: dict[str, str], params: dict[str, Any]) -> Job:
        wf = WORKFLOWS.get(workflow)
        if wf is None:
            raise JobValidationError(f"unknown workflow {workflow!r}")
        names = {i.name for i in wf.inputs}
        for spec in wf.inputs:
            if spec.required and not inputs.get(spec.name):
                raise JobValidationError(f"{wf.name} needs an input for {spec.label or spec.name}")
        for name, asset_id in inputs.items():
            if name not in names:
                raise JobValidationError(f"{wf.name} has no input {name!r}")
            if asset_id and self.store.get(asset_id) is None:
                raise JobValidationError(f"asset {asset_id} not found")
        defaults = {p.name: p.default for p in wf.params}
        params = {**defaults, **{k: v for k, v in params.items() if k in defaults}}
        job = Job(id=uuid.uuid4().hex, workflow=workflow, inputs={k: v for k, v in inputs.items() if v}, params=params)
        with self._lock:
            self.jobs[job.id] = job
        self._pool.submit(self._run, job)
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def _run(self, job: Job) -> None:
        job.status = "running"
        try:
            provider = get_provider(job.workflow)
            job.provider = provider.describe()
            images = {name: self.store.open_image(aid) for name, aid in job.inputs.items()}

            def progress(p: float, msg: str = "") -> None:
                job.progress = max(job.progress, min(1.0, float(p)))
                if msg:
                    job.message = msg

            results = provider.run(JobInput(images=images, params=job.params, progress=progress))
            outputs = []
            for r in results:
                if r.image is not None:
                    asset = self.store.put_image(r.image)
                    entry = {"kind": "image", "asset": asset.to_dict()}
                else:
                    asset = self.store.put_bytes(r.data or b"", r.mime)
                    entry = {"kind": "video" if r.mime.startswith("video/") else "file", "asset": asset.to_dict()}
                    if r.preview is not None:
                        entry["poster"] = self.store.put_image(r.preview).to_dict()
                entry["meta"] = r.meta
                outputs.append(entry)
            job.outputs = outputs
            job.progress, job.status, job.message = 1.0, "done", ""
        except Exception as exc:  # report every failure to the UI
            log.error("job %s failed: %s", job.id, traceback.format_exc())
            job.status, job.error = "error", str(exc) or exc.__class__.__name__
        finally:
            job.finished = time.time()
