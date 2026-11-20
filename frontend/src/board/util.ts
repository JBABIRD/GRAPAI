import type { BoardNode } from "../types";

export const uid = (prefix = "n") => `${prefix}_${Math.random().toString(36).slice(2, 10)}`;

export const IMAGE_W = 300;
export const TOOL_W = 300;

export function nodeSize(n: BoardNode): { w: number; h: number } {
  const w = n.measured?.width ?? n.width ?? (n.type === "tool" ? TOOL_W : IMAGE_W);
  const h = n.measured?.height ?? n.height ?? 200;
  return { w, h };
}

export function fitSize(width: number, height: number, target = IMAGE_W) {
  const ratio = height / Math.max(1, width);
  return { width: target, height: Math.round(target * ratio) };
}

export const WORKFLOW_ICONS: Record<string, string> = {
  create: "✦",
  render: "◐",
  edit: "✎",
  new_view: "⟲",
  animate: "▶",
  remove_bg: "◌",
  erase: "⌫",
  outpaint: "⤢",
  upscale: "⤢",
  compare: "◧",
};

export function inside(inner: BoardNode, outer: BoardNode): boolean {
  const a = nodeSize(inner);
  const b = nodeSize(outer);
  return (
    inner.position.x >= outer.position.x &&
    inner.position.y >= outer.position.y &&
    inner.position.x + a.w <= outer.position.x + b.w &&
    inner.position.y + a.h <= outer.position.y + b.h
  );
}

type Box = { x: number; y: number; w: number; h: number };
const hit = (a: Box, b: Box, gap = 24) =>
  a.x < b.x + b.w + gap && a.x + a.w + gap > b.x && a.y < b.y + b.h + gap && a.y + a.h + gap > b.y;

/** Move a box down until it no longer overlaps anything on the board (sections excepted). */
export function freeSpot(nodes: BoardNode[], pos: { x: number; y: number }, w: number, h: number, ignore: Set<string> = new Set()) {
  const boxes = nodes
    .filter((n) => n.type !== "section" && !ignore.has(n.id))
    .map((n) => ({ x: n.position.x, y: n.position.y, ...(() => { const s = nodeSize(n); return { w: s.w, h: s.h }; })() }));
  const box = { x: pos.x, y: pos.y, w, h };
  for (let i = 0; i < 200; i++) {
    const blocker = boxes.find((b) => hit(box, b));
    if (!blocker) break;
    box.y = blocker.y + blocker.h + 40;
  }
  return { x: box.x, y: box.y };
}
