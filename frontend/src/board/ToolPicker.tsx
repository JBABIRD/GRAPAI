import { useEffect, useMemo, useRef, useState } from "react";
import type { Workflow } from "../types";
import { WORKFLOW_ICONS } from "./util";

type Props = {
  at: { x: number; y: number };
  workflows: Workflow[];
  onPick: (workflow: string) => void;
  onClose: () => void;
};

/** Menu shown where a connection dragged out of an image was dropped. */
export default function ToolPicker({ at, workflows, onPick, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLDivElement>(null);

  const items = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? workflows.filter((w) => `${w.name} ${w.description}`.toLowerCase().includes(q)) : workflows;
  }, [query, workflows]);

  useEffect(() => input.current?.focus(), []);
  useEffect(() => setActive(0), [query]);

  // Keep the menu inside the board.
  const [pos, setPos] = useState(at);
  useEffect(() => {
    const el = box.current;
    const parent = el?.parentElement;
    if (!el || !parent) return;
    const x = Math.min(at.x, parent.clientWidth - el.offsetWidth - 8);
    const y = Math.min(at.y, parent.clientHeight - el.offsetHeight - 8);
    setPos({ x: Math.max(8, x), y: Math.max(8, y) });
  }, [at]);

  return (
    <div
      ref={box}
      className="tool-picker"
      style={{ left: pos.x, top: pos.y }}
      role="menu"
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
        else if (e.key === "ArrowDown") (e.preventDefault(), setActive((a) => Math.min(items.length - 1, a + 1)));
        else if (e.key === "ArrowUp") (e.preventDefault(), setActive((a) => Math.max(0, a - 1)));
        else if (e.key === "Enter" && items[active]) onPick(items[active].id);
      }}
    >
      <input ref={input} placeholder="Use this image with…" value={query} onChange={(e) => setQuery(e.target.value)} />
      {items.map((w, i) => (
        <button
          key={w.id}
          role="menuitem"
          className={i === active ? "on" : ""}
          onMouseEnter={() => setActive(i)}
          onClick={() => onPick(w.id)}
        >
          <span className="ti">{WORKFLOW_ICONS[w.id] ?? "◆"}</span>
          <span>
            <b>{w.name}</b>
            <em>{w.description}</em>
          </span>
        </button>
      ))}
      {items.length === 0 && <p className="none">No matching tool</p>}
    </div>
  );
}
