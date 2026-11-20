import { Handle, NodeResizer, NodeToolbar, Position, type NodeProps } from "@xyflow/react";
import { memo } from "react";
import { download } from "../../api";
import type { ImageNodeT } from "../../types";
import { useBoard } from "../BoardContext";

function ImageNode({ id, data, selected }: NodeProps<ImageNodeT>) {
  const { openEditor, quickAction, clearMask } = useBoard();
  return (
    <div className={`item image-item${data.sketch ? " is-sketch" : ""}`} onDoubleClick={() => openEditor(id)}>
      <NodeResizer isVisible={selected} keepAspectRatio minWidth={80} minHeight={50} color="var(--accent)" />
      <Handle type="target" position={Position.Left} id="in" className="handle-in" isConnectable={false} />
      <img src={data.url} alt={data.title ?? "image"} draggable={false} />
      {data.maskUrl && <img className="mask-overlay" src={data.maskUrl} alt="" draggable={false} />}
      {data.caption && <div className="caption" title={data.caption}>{data.caption}</div>}
      <Handle type="source" position={Position.Right} id="out" className="handle-out" title="Drag to a tool input" />
      <NodeToolbar position={Position.Top} className="node-toolbar">
        <button onClick={() => openEditor(id)} title="Draw, paint or mask (double-click)">
          Draw
        </button>
        {data.sketch && <button onClick={() => quickAction(id, "render")}>Render</button>}
        <button onClick={() => quickAction(id, "edit")} title="Edit with a prompt (E)">
          Edit
        </button>
        <button onClick={() => quickAction(id, "new_view")}>New view</button>
        <button onClick={() => quickAction(id, "animate")}>Animate</button>
        <span className="sep" />
        <button onClick={() => quickAction(id, "remove_bg")}>Cut out</button>
        <button onClick={() => quickAction(id, "upscale")}>Upscale</button>
        {data.maskAssetId && <button onClick={() => clearMask(id)}>Clear mask</button>}
        <button onClick={() => download(data.url, `${data.title ?? "ductus"}-${id}.png`)} title="Download">
          ↓
        </button>
      </NodeToolbar>
    </div>
  );
}

export default memo(ImageNode);
