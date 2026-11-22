import type { Asset, BoardDoc, BoardSummary, Catalogue, Job } from "./types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* not json */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetch("/api/health").then((r) => json<{ ok: boolean; provider: string }>(r)),
  catalogue: () => fetch("/api/workflows").then((r) => json<Catalogue>(r)),
  upload: (blob: Blob, name = "image.png") => {
    const form = new FormData();
    form.append("file", blob, name);
    return fetch("/api/assets", { method: "POST", body: form }).then((r) => json<Asset>(r));
  },
  submitJob: (workflow: string, inputs: Record<string, string | null | undefined>, params: Record<string, unknown>) =>
    fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workflow, inputs, params }),
    }).then((r) => json<Job>(r)),
  job: (id: string) => fetch(`/api/jobs/${id}`).then((r) => json<Job>(r)),
  boards: () => fetch("/api/boards").then((r) => json<BoardSummary[]>(r)),
  createBoard: (name: string) =>
    fetch("/api/boards", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) }).then((r) =>
      json<BoardDoc>(r),
    ),
  board: (id: string) => fetch(`/api/boards/${id}`).then((r) => json<BoardDoc>(r)),
  saveBoard: (doc: BoardDoc) =>
    fetch(`/api/boards/${doc.id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(doc) }).then((r) =>
      json<{ id: string; updated: number }>(r),
    ),
  deleteBoard: (id: string) => fetch(`/api/boards/${id}`, { method: "DELETE" }).then((r) => json<{ deleted: boolean }>(r)),
};

export function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`could not load ${url}`));
    img.src = url;
  });
}

export function canvasToBlob(canvas: HTMLCanvasElement, type = "image/png"): Promise<Blob> {
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("empty canvas"))), type));
}

export function download(url: string, filename: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}
