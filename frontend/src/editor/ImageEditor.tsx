import { useCallback, useEffect, useRef, useState } from "react";
import { canvasToBlob, loadImage } from "../api";

export type EditorResult = {
  image: Blob;
  /** Blob = new mask, null = mask cleared, undefined = unchanged. */
  mask: Blob | null | undefined;
};

type Props = {
  src: string | null;
  maskSrc: string | null;
  width: number;
  height: number;
  onCancel: () => void;
  onSave: (r: EditorResult) => void;
};

type Blend = "normal" | "multiply" | "screen" | "overlay" | "color";
type Layer = { id: string; name: string; canvas: HTMLCanvasElement; visible: boolean; opacity: number; blend: Blend };
type Tool = "brush" | "eraser" | "mask" | "unmask" | "lasso";

const MAX_SIDE = 2048;
const MASK_RGB = "255, 70, 70";
const SWATCHES = ["#111111", "#5b6270", "#ffffff", "#d9342b", "#ff8a3d", "#f2c94c", "#2f9e6e", "#2d6cdf", "#7b4fd6"];
const COMPOSITE: Record<Blend, GlobalCompositeOperation> = {
  normal: "source-over",
  multiply: "multiply",
  screen: "screen",
  overlay: "overlay",
  color: "color",
};
const TOOL_LABELS: Record<Tool, string> = {
  brush: "Brush (B)",
  eraser: "Eraser (E)",
  mask: "Paint mask (M)",
  unmask: "Erase mask (Shift+M)",
  lasso: "Lasso mask (L, hold Alt to subtract)",
};

let layerSeq = 0;
function makeCanvas(w: number, h: number) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return c;
}
function makeLayer(name: string, w: number, h: number): Layer {
  return { id: `L${++layerSeq}`, name, canvas: makeCanvas(w, h), visible: true, opacity: 1, blend: "normal" };
}

export default function ImageEditor({ src, maskSrc, width, height, onCancel, onSave }: Props) {
  const scale = Math.min(1, MAX_SIDE / Math.max(width, height));
  const W = Math.round(width * scale);
  const H = Math.round(height * scale);

  const [layers, setLayers] = useState<Layer[]>([]);
  const [active, setActive] = useState<string>("");
  const [tool, setTool] = useState<Tool>("brush");
  const [color, setColor] = useState("#111111");
  const [size, setSize] = useState(6);
  const [flow, setFlow] = useState(1);
  const [showMask, setShowMask] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [lasso, setLasso] = useState<{ x: number; y: number }[] | null>(null);

  const maskRef = useRef<HTMLCanvasElement>(makeCanvas(W, H));
  const maskDirty = useRef(false);
  const hadMask = useRef(!!maskSrc);
  const undo = useRef<{ target: HTMLCanvasElement; data: ImageData }[]>([]);
  const viewport = useRef<HTMLDivElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const drawing = useRef<{ last: { x: number; y: number }; pointer: number } | null>(null);
  const panning = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const spaceDown = useRef(false);

  // ---------- setup ----------
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const base = makeLayer(src ? "Image" : "Paper", W, H);
      const ctx = base.canvas.getContext("2d")!;
      if (src) {
        const img = await loadImage(src);
        ctx.drawImage(img, 0, 0, W, H);
      } else {
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, W, H);
      }
      const ink = makeLayer(src ? "Paint" : "Lines", W, H);
      if (maskSrc) {
        try {
          const m = await loadImage(maskSrc);
          maskRef.current.getContext("2d")!.drawImage(m, 0, 0, W, H);
        } catch {
          /* ignore broken mask */
        }
      }
      if (cancelled) return;
      setLayers([base, ink]);
      setActive(ink.id);
      setReady(true);
      if (src && maskSrc) setTool("mask");
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // fit to the viewport
  const fit = useCallback(() => {
    const vp = viewport.current;
    if (!vp) return;
    const z = Math.min((vp.clientWidth - 80) / W, (vp.clientHeight - 80) / H, 4);
    setZoom(z);
    setOffset({ x: (vp.clientWidth - W * z) / 2, y: (vp.clientHeight - H * z) / 2 });
  }, [W, H]);
  useEffect(() => {
    if (ready) fit();
  }, [ready, fit]);

  const activeLayer = layers.find((l) => l.id === active);

  // ---------- drawing ----------
  const toImage = (e: { clientX: number; clientY: number }) => {
    const r = stage.current!.getBoundingClientRect();
    return { x: ((e.clientX - r.left) / r.width) * W, y: ((e.clientY - r.top) / r.height) * H };
  };

  const targetCanvas = () => (tool === "mask" || tool === "unmask" || tool === "lasso" ? maskRef.current : activeLayer?.canvas);

  const pushUndo = (c: HTMLCanvasElement) => {
    undo.current.push({ target: c, data: c.getContext("2d")!.getImageData(0, 0, c.width, c.height) });
    if (undo.current.length > 40) undo.current.shift();
  };

  const stroke = (from: { x: number; y: number }, to: { x: number; y: number }, pressure: number) => {
    const c = targetCanvas();
    if (!c) return;
    const ctx = c.getContext("2d")!;
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    const isMask = tool === "mask" || tool === "unmask";
    ctx.globalCompositeOperation = tool === "eraser" || tool === "unmask" ? "destination-out" : "source-over";
    ctx.strokeStyle = isMask ? `rgb(${MASK_RGB})` : color;
    ctx.globalAlpha = isMask ? 1 : flow;
    ctx.lineWidth = Math.max(0.5, (isMask ? size * 4 : size) * pressure);
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(to.x, to.y);
    ctx.stroke();
    ctx.restore();
    if (isMask) maskDirty.current = true;
  };

  const onPointerDown = (e: React.PointerEvent) => {
    if (!ready) return;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    if (e.button === 1 || e.button === 2 || spaceDown.current) {
      panning.current = { x: e.clientX, y: e.clientY, ox: offset.x, oy: offset.y };
      return;
    }
    const p = toImage(e);
    if (tool === "lasso") {
      setLasso([p]);
      return;
    }
    const c = targetCanvas();
    if (!c) return;
    pushUndo(c);
    drawing.current = { last: p, pointer: e.pointerId };
    const pressure = e.pointerType === "pen" ? Math.max(0.05, e.pressure) : 1;
    stroke(p, { x: p.x + 0.01, y: p.y }, pressure);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (panning.current) {
      const p = panning.current;
      setOffset({ x: p.ox + e.clientX - p.x, y: p.oy + e.clientY - p.y });
      return;
    }
    if (lasso) {
      setLasso((pts) => (pts ? [...pts, toImage(e)] : pts));
      return;
    }
    const d = drawing.current;
    if (!d || d.pointer !== e.pointerId) return;
    const events = (e.nativeEvent as PointerEvent).getCoalescedEvents?.() ?? [e.nativeEvent];
    for (const ev of events) {
      const p = toImage(ev);
      const pressure = ev.pointerType === "pen" ? Math.max(0.05, ev.pressure) : 1;
      stroke(d.last, p, pressure);
      d.last = p;
    }
  };

  const onPointerUp = (e: React.PointerEvent) => {
    panning.current = null;
    drawing.current = null;
    if (lasso && lasso.length > 2) {
      const c = maskRef.current;
      pushUndo(c);
      const ctx = c.getContext("2d")!;
      ctx.save();
      ctx.globalCompositeOperation = e.altKey ? "destination-out" : "source-over";
      ctx.fillStyle = `rgb(${MASK_RGB})`;
      ctx.beginPath();
      lasso.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
      ctx.closePath();
      ctx.fill();
      ctx.restore();
      maskDirty.current = true;
      setShowMask(true);
    }
    setLasso(null);
  };

  const onWheel = (e: React.WheelEvent) => {
    const vp = viewport.current!.getBoundingClientRect();
    const mx = e.clientX - vp.left;
    const my = e.clientY - vp.top;
    if (e.ctrlKey || e.metaKey || !e.shiftKey) {
      const nz = Math.min(8, Math.max(0.05, zoom * Math.exp(-e.deltaY * 0.0015)));
      setOffset({ x: mx - ((mx - offset.x) * nz) / zoom, y: my - ((my - offset.y) * nz) / zoom });
      setZoom(nz);
    } else {
      setOffset({ x: offset.x - e.deltaX, y: offset.y - e.deltaY });
    }
  };

  const doUndo = useCallback(() => {
    const u = undo.current.pop();
    if (!u) return;
    u.target.getContext("2d")!.putImageData(u.data, 0, 0);
    if (u.target === maskRef.current) maskDirty.current = true;
    setLayers((ls) => [...ls]);
  }, []);

  const clearMask = () => {
    pushUndo(maskRef.current);
    maskRef.current.getContext("2d")!.clearRect(0, 0, W, H);
    maskDirty.current = true;
    setLayers((ls) => [...ls]);
  };

  // ---------- layers ----------
  const patchLayer = (id: string, patch: Partial<Layer>) => setLayers((ls) => ls.map((l) => (l.id === id ? { ...l, ...patch } : l)));
  const addLayer = () => {
    const l = makeLayer(`Layer ${layers.length + 1}`, W, H);
    const idx = layers.findIndex((x) => x.id === active);
    const next = [...layers];
    next.splice(idx + 1, 0, l);
    setLayers(next);
    setActive(l.id);
    if (tool !== "brush" && tool !== "eraser") setTool("brush");
  };
  const removeLayer = (id: string) => {
    if (layers.length <= 1) return;
    const next = layers.filter((l) => l.id !== id);
    setLayers(next);
    if (active === id) setActive(next[next.length - 1].id);
  };
  const moveLayer = (id: string, dir: 1 | -1) => {
    const i = layers.findIndex((l) => l.id === id);
    const j = i + dir;
    if (j < 0 || j >= layers.length) return;
    const next = [...layers];
    [next[i], next[j]] = [next[j], next[i]];
    setLayers(next);
  };

  // ---------- save ----------
  const save = async () => {
    setBusy(true);
    try {
      const out = makeCanvas(W, H);
      const ctx = out.getContext("2d")!;
      for (const l of layers) {
        if (!l.visible) continue;
        ctx.globalAlpha = l.opacity;
        ctx.globalCompositeOperation = COMPOSITE[l.blend];
        ctx.drawImage(l.canvas, 0, 0);
      }
      const image = await canvasToBlob(out);
      let mask: Blob | null | undefined = undefined;
      if (maskDirty.current) {
        const data = maskRef.current.getContext("2d")!.getImageData(0, 0, W, H).data;
        let any = false;
        for (let i = 3; i < data.length; i += 4 * 7) if (data[i] > 0) { any = true; break; }
        mask = any ? await canvasToBlob(maskRef.current) : hadMask.current ? null : undefined;
      }
      onSave({ image, mask });
    } finally {
      setBusy(false);
    }
  };

  // ---------- keyboard ----------
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, select, textarea")) return;
      if (e.code === "Space") {
        spaceDown.current = true;
        e.preventDefault();
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        doUndo();
      } else if (e.key === "Escape") onCancel();
      else if (e.key === "b") setTool("brush");
      else if (e.key === "e") setTool("eraser");
      else if (e.key === "m") setTool("mask");
      else if (e.key === "M") setTool("unmask");
      else if (e.key === "l") setTool("lasso");
      else if (e.key === "[") setSize((s) => Math.max(1, Math.round(s / 1.25)));
      else if (e.key === "]") setSize((s) => Math.min(400, Math.round(s * 1.25 + 1)));
      else if (e.key === "0") fit();
    };
    const up = (e: KeyboardEvent) => {
      if (e.code === "Space") spaceDown.current = false;
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [doUndo, fit, onCancel]);

  const isMaskTool = tool === "mask" || tool === "unmask" || tool === "lasso";
  const cursorSize = Math.max(4, (isMaskTool ? size * 4 : size) * zoom);

  return (
    <div className="editor" role="dialog" aria-label="Image editor">
      <header className="editor-top">
        <div className="editor-tools">
          {(Object.keys(TOOL_LABELS) as Tool[]).map((t) => (
            <button key={t} className={tool === t ? "on" : ""} onClick={() => setTool(t)} title={TOOL_LABELS[t]}>
              {{ brush: "Brush", eraser: "Eraser", mask: "Mask", unmask: "Unmask", lasso: "Lasso" }[t]}
            </button>
          ))}
        </div>
        <label className="ed-field">
          Size
          <input type="range" min={1} max={200} value={size} onChange={(e) => setSize(Number(e.target.value))} />
          <output>{size}</output>
        </label>
        {!isMaskTool && (
          <>
            <label className="ed-field">
              Flow
              <input type="range" min={0.05} max={1} step={0.05} value={flow} onChange={(e) => setFlow(Number(e.target.value))} />
            </label>
            <div className="swatches">
              {SWATCHES.map((c) => (
                <button key={c} className={c === color ? "on" : ""} style={{ background: c }} onClick={() => setColor(c)} aria-label={c} />
              ))}
              <input type="color" value={color} onChange={(e) => setColor(e.target.value)} title="Custom colour" />
            </div>
          </>
        )}
        {isMaskTool && (
          <div className="mask-actions">
            <label>
              <input type="checkbox" checked={showMask} onChange={(e) => setShowMask(e.target.checked)} /> Show mask
            </label>
            <button onClick={clearMask}>Clear mask</button>
            <span className="hint">The mask limits Edit to the painted area.</span>
          </div>
        )}
        <div className="spacer" />
        <button onClick={doUndo} title="Undo (Ctrl+Z)">
          Undo
        </button>
        <button onClick={fit} title="Fit (0)">
          Fit
        </button>
        <button onClick={onCancel}>Cancel</button>
        <button className="primary" onClick={save} disabled={!ready || busy}>
          {busy ? "Saving…" : "Done"}
        </button>
      </header>
      <div className="editor-body">
        <div
          className="editor-viewport"
          ref={viewport}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onWheel={onWheel}
          onContextMenu={(e) => e.preventDefault()}
          style={{ ["--cursor-size" as string]: `${cursorSize}px` }}
        >
          <div
            className="editor-stage"
            ref={stage}
            style={{ width: W, height: H, transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})` }}
          >
            {layers.map((l) => (
              <div
                key={l.id}
                className="layer-slot"
                style={{ opacity: l.opacity, mixBlendMode: l.blend === "normal" ? undefined : l.blend, display: l.visible ? "block" : "none" }}
                ref={(el) => {
                  if (el && el.firstChild !== l.canvas) {
                    el.replaceChildren(l.canvas);
                  }
                }}
              />
            ))}
            <div
              className="layer-slot mask-slot"
              style={{ display: showMask ? "block" : "none" }}
              ref={(el) => {
                if (el && el.firstChild !== maskRef.current) el.replaceChildren(maskRef.current);
              }}
            />
            {lasso && (
              <svg className="lasso" viewBox={`0 0 ${W} ${H}`}>
                <polyline points={lasso.map((p) => `${p.x},${p.y}`).join(" ")} vectorEffect="non-scaling-stroke" />
              </svg>
            )}
          </div>
          {!ready && <div className="editor-loading">Loading…</div>}
        </div>
        <aside className="layers-panel">
          <div className="layers-head">
            <b>Layers</b>
            <button onClick={addLayer} title="New layer">
              + Layer
            </button>
          </div>
          <ul>
            {[...layers].reverse().map((l) => (
              <li key={l.id} className={l.id === active ? "on" : ""} onClick={() => setActive(l.id)}>
                <div className="layer-row">
                  <button
                    className={`eye${l.visible ? "" : " off"}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      patchLayer(l.id, { visible: !l.visible });
                    }}
                    title="Show or hide"
                  >
                    {l.visible ? "◉" : "○"}
                  </button>
                  <input className="layer-name" value={l.name} onChange={(e) => patchLayer(l.id, { name: e.target.value })} />
                  <button onClick={(e) => (e.stopPropagation(), moveLayer(l.id, 1))} title="Move up">
                    ↑
                  </button>
                  <button onClick={(e) => (e.stopPropagation(), moveLayer(l.id, -1))} title="Move down">
                    ↓
                  </button>
                  <button onClick={(e) => (e.stopPropagation(), removeLayer(l.id))} title="Delete layer" disabled={layers.length <= 1}>
                    ×
                  </button>
                </div>
                {l.id === active && (
                  <div className="layer-props">
                    <select value={l.blend} onChange={(e) => patchLayer(l.id, { blend: e.target.value as Blend })}>
                      {Object.keys(COMPOSITE).map((b) => (
                        <option key={b} value={b}>
                          {b[0].toUpperCase() + b.slice(1)}
                        </option>
                      ))}
                    </select>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={l.opacity}
                      onChange={(e) => patchLayer(l.id, { opacity: Number(e.target.value) })}
                      title="Opacity"
                    />
                    <output>{Math.round(l.opacity * 100)}%</output>
                  </div>
                )}
              </li>
            ))}
          </ul>
          <p className="layers-note">
            Layers are merged when you press Done. Paint a mask to edit only that part of the image with the Edit block.
          </p>
        </aside>
      </div>
    </div>
  );
}
