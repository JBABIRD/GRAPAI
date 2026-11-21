import { Handle, Position, useEdges, type NodeProps } from "@xyflow/react";
import { memo, useMemo } from "react";
import type { ParamSpec, ToolNodeT } from "../../types";
import { useBoard } from "../BoardContext";
import { WORKFLOW_ICONS } from "../util";

const PROMPT_CHIPS: Record<string, string[]> = {
  edit: ["Change the material of @1 to ", "Add ", "Remove ", "Recolour to ", "Apply the style of @2 to @1"],
  render: ["glossy paint ", "brushed aluminium ", "soft-touch black polymer ", "walnut and leather "],
  create: ["electric scooter ", "office chair ", "running shoe ", "handheld power tool ", "concept car "],
  animate: ["slow turntable ", "camera pushes in ", "lid opens smoothly ", "light sweep across the surface "],
};

const LABELS: Record<string, string> = {
  design_5: "5 views",
  keep: "Keep as is",
  ground: "Stand on ground",
  ortho_4: "Ortho 4",
  turnaround_8: "8 around",
  same_scene: "Same scene",
  studio: "Studio",
  full: "Full look",
  colours_materials: "Colours & materials",
  rendering: "Rendering technique",
  lighting_mood: "Lighting & mood",
  color_block: "Colour block",
  shaded: "Shaded",
  realistic: "Realistic",
  push_in: "Push in",
  custom: "From prompt",
  eye: "Eye level",
};

const label = (v: string | number) => LABELS[String(v)] ?? (typeof v === "number" ? String(v) : String(v).replace(/_/g, " "));

function ToolNode({ id, data, selected }: NodeProps<ToolNodeT>) {
  const { workflow: getWorkflow, presets, runTool, updateNodeData, deleteNode } = useBoard();
  const wf = getWorkflow(data.workflow);
  const edges = useEdges();
  const connected = useMemo(
    () => new Set(edges.filter((e) => e.target === id).map((e) => e.targetHandle)),
    [edges, id],
  );
  if (!wf) return <div className="tool-item">Unknown tool {data.workflow}</div>;

  const set = (name: string, value: unknown) => updateNodeData(id, { params: { ...data.params, [name]: value } });
  const value = (p: ParamSpec) => (data.params[p.name] ?? p.default) as string | number;
  const running = data.status === "running";
  const missing = wf.inputs.filter((i) => i.kind === "image" && i.required && !connected.has(i.name));

  const renderParam = (p: ParamSpec) => {
    const v = value(p);
    switch (p.kind) {
      case "text":
        return (
          <div className="param" key={p.name}>
            <textarea
              className="nodrag nowheel prompt"
              placeholder={p.label}
              value={String(v ?? "")}
              rows={3}
              onChange={(e) => set(p.name, e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) runTool(id);
              }}
            />
            {PROMPT_CHIPS[wf.id] && (
              <div className="chips">
                {PROMPT_CHIPS[wf.id].map((c) => (
                  <button key={c} className="chip nodrag" onClick={() => set(p.name, `${String(v ?? "").trim()} ${c}`.trimStart())}>
                    {c.trim()}
                  </button>
                ))}
              </div>
            )}
          </div>
        );
      case "preset":
        return (
          <label className="param row" key={p.name}>
            <span>{p.label}</span>
            <select className="nodrag" value={String(v)} onChange={(e) => set(p.name, e.target.value)}>
              <option value="">None</option>
              {presets.map((pr) => (
                <option key={pr.id} value={pr.id}>
                  {pr.name}
                </option>
              ))}
            </select>
          </label>
        );
      case "select":
        if (p.name === "mode" || (p.options && p.options.length <= 3)) {
          return (
            <div className="param row" key={p.name}>
              <span>{p.label}</span>
              <div className="segmented nodrag">
                {p.options!.map((o) => (
                  <button key={String(o)} className={String(o) === String(v) ? "on" : ""} onClick={() => set(p.name, o)}>
                    {label(o)}
                  </button>
                ))}
              </div>
            </div>
          );
        }
        return (
          <label className="param row" key={p.name}>
            <span>{p.label}</span>
            <select
              className="nodrag"
              value={String(v)}
              onChange={(e) => set(p.name, typeof p.default === "number" ? Number(e.target.value) : e.target.value)}
            >
              {p.options!.map((o) => (
                <option key={String(o)} value={String(o)}>
                  {p.name === "angle" ? `${o}°` : p.name === "size" ? `${o}%` : label(o)}
                </option>
              ))}
            </select>
          </label>
        );
      case "number":
        return (
          <label className="param row" key={p.name}>
            <span>{p.label}</span>
            <input
              className="nodrag"
              type="range"
              min={p.min ?? 0}
              max={p.max ?? 1}
              step={p.step ?? 0.01}
              value={Number(v)}
              onChange={(e) => set(p.name, Number(e.target.value))}
            />
            <output>{(p.step ?? 1) < 1 ? `${Math.round(Number(v) * 100)}%` : String(v)}</output>
          </label>
        );
      case "seed":
        return (
          <label className="param row" key={p.name}>
            <span>{p.label}</span>
            <input
              className="nodrag seed"
              type="number"
              value={Number(v)}
              onChange={(e) => set(p.name, Number(e.target.value))}
              title="-1 picks a new random seed every run"
            />
            <button className="icon nodrag" title="Random every run" onClick={() => set(p.name, -1)}>
              ⚄
            </button>
          </label>
        );
      default:
        return null;
    }
  };

  return (
    <div className={`tool-item${selected ? " selected" : ""} status-${data.status}`}>
      <div className="tool-head">
        <span className="tool-icon">{WORKFLOW_ICONS[wf.id] ?? "◆"}</span>
        <span className="tool-name">{wf.name}</span>
        <span className="tool-model" title={`${wf.model} · ${wf.license}`}>
          {wf.model.split(" / ")[data.params.mode === "quality" ? 1 : 0] ?? wf.model}
        </span>
        <button className="icon nodrag close" onClick={() => deleteNode(id)} title="Remove block">
          ×
        </button>
      </div>
      <p className="tool-desc">{wf.description}</p>
      {wf.inputs.filter((i) => i.kind === "image").length > 0 && (
        <div className="tool-inputs">
          {wf.inputs
            .filter((i) => i.kind === "image")
            .map((i) => (
              <div key={i.name} className={`tool-input${connected.has(i.name) ? " connected" : ""}`}>
                <Handle type="target" position={Position.Left} id={i.name} className="handle-tool-in" />
                <span>{i.label}</span>
                <em>{connected.has(i.name) ? "connected" : i.required ? "connect an image" : "optional"}</em>
              </div>
            ))}
        </div>
      )}
      <div className="tool-params">{wf.params.map(renderParam)}</div>
      {data.error && <div className="tool-error">{data.error}</div>}
      <div className="tool-foot">
        {running ? (
          <div className="progress" title={data.message}>
            <div style={{ width: `${Math.max(4, (data.progress ?? 0) * 100)}%` }} />
            <span>{data.message || "working…"}</span>
          </div>
        ) : (
          <button
            className="primary nodrag"
            disabled={missing.length > 0}
            onClick={() => runTool(id)}
            title={missing.length ? `Connect ${missing.map((m) => m.label).join(", ")}` : "Generate (Ctrl+Enter)"}
          >
            {wf.output === "video" ? "Animate" : "Generate"}
          </button>
        )}
      </div>
      <Handle type="source" position={Position.Right} id="out" className="handle-out" isConnectable={false} />
    </div>
  );
}

export default memo(ToolNode);
