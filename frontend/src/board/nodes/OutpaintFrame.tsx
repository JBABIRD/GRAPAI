import { useStore } from "@xyflow/react";
import { useRef, useState } from "react";

/** Padding around the image, in source pixels. */
export type Pads = { left: number; top: number; right: number; bottom: number };

type Props = {
  imgW: number;
  imgH: number;
  /** Displayed width of the image on the board (flow units). */
  shownW: number;
  pads: Pads;
  onChange: (p: Pads) => void;
  /** Starting text for the scene description (e.g. the image's own prompt). */
  initialPrompt?: string;
  onGenerate: (prompt: string) => void;
  onCancel: () => void;
};

const ASPECTS: [string, number | null][] = [["Free", null], ["1:1", 1], ["4:3", 4 / 3], ["3:2", 3 / 2], ["16:9", 16 / 9], ["9:16", 9 / 16]];
const MAX_SIDE = 4096;
const snap = (v: number) => Math.max(0, Math.round(v / 8) * 8);

type Edge = "l" | "r" | "t" | "b";
const HANDLES: { id: string; edges: Edge[] }[] = [
  { id: "nw", edges: ["l", "t"] }, { id: "n", edges: ["t"] }, { id: "ne", edges: ["r", "t"] },
  { id: "e", edges: ["r"] }, { id: "se", edges: ["r", "b"] }, { id: "s", edges: ["b"] },
  { id: "sw", edges: ["l", "b"] }, { id: "w", edges: ["l"] },
];

/** Grow the frame (never shrink it) so it has the given aspect, centred on the current frame. */
export function padsForAspect(p: Pads, w: number, h: number, a: number): Pads {
  const fw = w + p.left + p.right, fh = h + p.top + p.bottom;
  if (fw / fh < a) {
    const add = fh * a - fw;
    return { ...p, left: snap(p.left + add / 2), right: snap(p.right + add / 2) };
  }
  const add = fw / a - fh;
  return { ...p, top: snap(p.top + add / 2), bottom: snap(p.bottom + add / 2) };
}

export default function OutpaintFrame({ imgW, imgH, shownW, pads, initialPrompt = "", onChange, onGenerate, onCancel }: Props) {
  const [prompt, setPrompt] = useState(initialPrompt);
  const zoom = useStore((s) => s.transform[2]);
  const s = shownW / imgW; // flow units per source pixel
  const [aspect, setAspect] = useState<string>("Free");
  const drag = useRef<{ x: number; y: number; start: Pads; edges: Edge[] } | null>(null);

  const clamp = (p: Pads): Pads => {
    const out = { ...p };
    const fit = (a: "left" | "top", b: "right" | "bottom", side: number) => {
      const extra = out[a] + out[b];
      if (side + extra > MAX_SIDE) {
        const k = (MAX_SIDE - side) / extra;
        out[a] = snap(out[a] * k);
        out[b] = snap(out[b] * k);
      }
    };
    fit("left", "right", imgW);
    fit("top", "bottom", imgH);
    return out;
  };

  const down = (e: React.PointerEvent, edges: Edge[]) => {
    e.stopPropagation();
    (e.target as Element).setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, start: pads, edges };
  };
  const move = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = (e.clientX - d.x) / zoom / s, dy = (e.clientY - d.y) / zoom / s;
    const p = { ...d.start };
    if (d.edges.includes("l")) p.left = snap(d.start.left - dx);
    if (d.edges.includes("r")) p.right = snap(d.start.right + dx);
    if (d.edges.includes("t")) p.top = snap(d.start.top - dy);
    if (d.edges.includes("b")) p.bottom = snap(d.start.bottom + dy);
    setAspect("Free");
    onChange(clamp(p));
  };
  const up = () => (drag.current = null);

  const fw = imgW + pads.left + pads.right, fh = imgH + pads.top + pads.bottom;
  const style = { left: -pads.left * s, top: -pads.top * s, width: fw * s, height: fh * s };
  const ui = 1 / zoom; // keep handles and labels the same size on screen

  return (
    <div className="outpaint-frame nodrag nopan nowheel" style={style} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
      <div className="outpaint-image" style={{ left: pads.left * s, top: pads.top * s, width: imgW * s, height: imgH * s }} />
      {HANDLES.map((h) => (
        <div
          key={h.id}
          className={`outpaint-handle h-${h.id}`}
          style={{ transform: `translate(-50%, -50%) scale(${ui})` }}
          onPointerDown={(e) => down(e, h.edges)}
        />
      ))}
      <div className="outpaint-size" style={{ transform: `scale(${ui})` }}>
        {fw} × {fh} px
      </div>
      <div className="outpaint-bar" style={{ transform: `scale(${ui})` }} onPointerDown={(e) => e.stopPropagation()}>
        {ASPECTS.map(([label, a]) => (
          <button
            key={label}
            className={aspect === label ? "on" : ""}
            onClick={() => {
              setAspect(label);
              if (a) onChange(clamp(padsForAspect(pads, imgW, imgH, a)));
            }}
          >
            {label}
          </button>
        ))}
        <span className="sep" />
        <input
          className="outpaint-prompt"
          value={prompt}
          placeholder="Describe the surroundings, e.g. frozen lake, snowy mountains"
          title="A few words about the scene make the extension much better"
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            e.stopPropagation();
            if (e.key === "Enter" && !(fw === imgW && fh === imgH)) onGenerate(prompt.trim());
          }}
        />
        <button onClick={onCancel}>Cancel</button>
        <button className="primary" onClick={() => onGenerate(prompt.trim())} disabled={fw === imgW && fh === imgH}>
          Extend
        </button>
      </div>
    </div>
  );
}
