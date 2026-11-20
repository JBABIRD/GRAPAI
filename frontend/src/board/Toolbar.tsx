import { useState } from "react";
import type { Workflow } from "../types";
import { WORKFLOW_ICONS } from "./util";

type Props = {
  workflows: Workflow[];
  onSketch: () => void;
  onUpload: () => void;
  onNote: () => void;
  onSection: () => void;
  onTool: (workflow: string) => void;
  onFit: () => void;
  onCompare: () => void;
};

export default function Toolbar({ workflows, onSketch, onUpload, onNote, onSection, onTool, onFit, onCompare }: Props) {
  const [open, setOpen] = useState(false);
  return (
    <div className="side-toolbar">
      <button onClick={onSketch} title="New sketch (D)">
        <span>✏︎</span>
        <small>Sketch</small>
      </button>
      <button onClick={onUpload} title="Upload images or video, or drop/paste them on the board">
        <span>⇪</span>
        <small>Upload</small>
      </button>
      <div className="tool-menu-wrap">
        <button className={open ? "on" : ""} onClick={() => setOpen((o) => !o)} title="Add an AI tool block">
          <span>✦</span>
          <small>AI tools</small>
        </button>
        {open && (
          <div className="tool-menu" onMouseLeave={() => setOpen(false)}>
            {workflows.map((w) => (
              <button
                key={w.id}
                onClick={() => {
                  onTool(w.id);
                  setOpen(false);
                }}
              >
                <span className="ti">{WORKFLOW_ICONS[w.id] ?? "◆"}</span>
                <span>
                  <b>{w.name}</b>
                  <em>{w.description}</em>
                </span>
                <i>{w.model}</i>
              </button>
            ))}
          </div>
        )}
      </div>
      <button onClick={onCompare} title="Before/after compare: select one result, or two images (left = before)">
        <span>◧</span>
        <small>Compare</small>
      </button>
      <button onClick={onNote} title="Sticky note (N)">
        <span>▤</span>
        <small>Note</small>
      </button>
      <button onClick={onSection} title="Section around the selection (S)">
        <span>⬚</span>
        <small>Section</small>
      </button>
      <hr />
      <button onClick={onFit} title="Fit everything (Shift+1)">
        <span>⤧</span>
        <small>Fit</small>
      </button>
    </div>
  );
}
