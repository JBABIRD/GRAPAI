import { Handle, NodeResizer, NodeToolbar, Position, type NodeProps } from "@xyflow/react";
import { memo, useRef, useState } from "react";
import { download } from "../../api";
import type { ImageNodeT } from "../../types";
import { useBoard } from "../BoardContext";
import OutpaintFrame, { type Pads } from "./OutpaintFrame";

function ImageNode({ id, data, selected }: NodeProps<ImageNodeT>) {
  const { openEditor, quickAction, clearMask, compareWith, eraseObject, outpaint } = useBoard();
  const [extend, setExtend] = useState<Pads | null>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const startExtend = () => {
    const side = Math.round(data.width * 0.25 / 8) * 8;
    setExtend({ left: side, top: 0, right: side, bottom: 0 });
  };
  return (
    <div className={`item image-item${data.sketch ? " is-sketch" : ""}`} onDoubleClick={() => openEditor(id)}>
      <NodeResizer isVisible={selected} keepAspectRatio minWidth={80} minHeight={50} color="var(--accent)" />
      <Handle type="target" position={Position.Left} id="in" className="handle-in" isConnectable={false} />
      <img ref={imgRef} src={data.url} alt={data.title ?? "image"} draggable={false} />
      {data.maskUrl && <img className="mask-overlay" src={data.maskUrl} alt="" draggable={false} />}
      {data.caption && <div className="caption" title={data.caption}>{data.caption}</div>}
      <Handle type="source" position={Position.Right} id="out" className="handle-out" title="Drag to a tool input" />
      {extend && (
        <OutpaintFrame
          imgW={data.width}
          imgH={data.height}
          shownW={imgRef.current?.offsetWidth || data.width}
          pads={extend}
          onChange={setExtend}
          onCancel={() => setExtend(null)}
          initialPrompt={sceneFromCaption(data.caption)}
          onGenerate={(prompt) => {
            outpaint(id, extend, prompt);
            setExtend(null);
          }}
        />
      )}
      {!extend && (
      <NodeToolbar position={Position.Top} className="node-toolbar">
        <button onClick={() => openEditor(id)} title="Draw, paint or mask (double-click)">
          Draw
        </button>
        {data.sketch && <button onClick={() => quickAction(id, "render")}>Render</button>}
        <button onClick={() => quickAction(id, "edit")} title="Edit with a prompt (E)">
          Edit
        </button>
        <button onClick={() => quickAction(id, "new_view")}>New view</button>
        <button onClick={() => quickAction(id, "views")} title="Standard views: front, side, rear, top and 3/4 in one go">
          Views
        </button>
        <button onClick={() => quickAction(id, "animate")}>Animate</button>
        <button
          onClick={() => quickAction(id, "style")}
          title="Style transfer: also select a style image (Shift-click) to use it, or connect one to the Style input"
        >
          Style
        </button>
        <button onClick={() => compareWith(id)} title="Before/after slider against the image this came from">
          Compare
        </button>
        <span className="sep" />
        <button onClick={() => eraseObject(id)} title="Remove what you mask and fill in the background">
          Erase
        </button>
        <button onClick={startExtend} title="Outpaint: drag a frame around the image to extend it">
          Extend
        </button>
        <button onClick={() => quickAction(id, "remove_bg")}>Cut out</button>
        <button onClick={() => quickAction(id, "upscale")}>Upscale</button>
        {data.maskAssetId && <button onClick={() => clearMask(id)}>Clear mask</button>}
        <button onClick={() => download(data.url, `${data.title ?? "ductus"}-${id}.png`)} title="Download">
          ↓
        </button>
      </NodeToolbar>
      )}
    </div>
  );
}

/** "Create: orange drill on ice" -> "orange drill on ice"; tool-only captions give nothing. */
function sceneFromCaption(caption?: string): string {
  if (!caption) return "";
  const i = caption.indexOf(": ");
  return i >= 0 ? caption.slice(i + 2).trim() : "";
}

export default memo(ImageNode);
