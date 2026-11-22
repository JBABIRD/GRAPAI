import { Handle, NodeResizer, Position, useEdges, useNodes, type NodeProps } from "@xyflow/react";
import { memo, useRef } from "react";
import type { BoardNode, CompareNodeT, ImageNodeT } from "../../types";
import { useBoard } from "../BoardContext";

/** Before/after viewer: two connected images, split by a draggable divider. */
function CompareNode({ id, data, selected }: NodeProps<CompareNodeT>) {
  const { updateNodeData, deleteNode } = useBoard();
  const edges = useEdges();
  const nodes = useNodes<BoardNode>();
  const area = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const imageFor = (handle: string) => {
    const e = edges.find((x) => x.target === id && x.targetHandle === handle);
    const n = e && (nodes.find((x) => x.id === e.source) as ImageNodeT | undefined);
    return n?.type === "image" ? n.data : null;
  };
  const before = imageFor("before");
  const after = imageFor("after");
  const split = Math.min(1, Math.max(0, data.split ?? 0.5));

  const setFromPointer = (clientX: number) => {
    const r = area.current?.getBoundingClientRect();
    if (r) updateNodeData(id, { split: Math.min(1, Math.max(0, (clientX - r.left) / r.width)) });
  };

  const ratio = after ? after.height / after.width : before ? before.height / before.width : 0.75;

  return (
    <div className="item compare-item">
      <NodeResizer isVisible={selected} keepAspectRatio minWidth={160} minHeight={120} color="var(--accent)" />
      <div className="compare-head">
        <span>Compare</span>
        <button className="icon nodrag close" onClick={() => deleteNode(id)} title="Remove">
          ×
        </button>
      </div>
      <Handle type="target" position={Position.Left} id="before" className="handle-tool-in compare-handle before" title="Before" />
      <Handle type="target" position={Position.Left} id="after" className="handle-tool-in compare-handle after" title="After" />
      <div
        ref={area}
        className="compare-area nodrag nowheel"
        style={{ aspectRatio: `${1 / ratio}` }}
        onPointerDown={(e) => {
          if (!before || !after) return;
          dragging.current = true;
          (e.target as HTMLElement).setPointerCapture(e.pointerId);
          setFromPointer(e.clientX);
        }}
        onPointerMove={(e) => dragging.current && setFromPointer(e.clientX)}
        onPointerUp={() => (dragging.current = false)}
        onPointerCancel={() => (dragging.current = false)}
      >
        {after && <img src={after.url} alt="after" draggable={false} />}
        {before && (
          <img
            className="compare-before"
            src={before.url}
            alt="before"
            draggable={false}
            style={after ? { clipPath: `inset(0 ${(1 - split) * 100}% 0 0)` } : undefined}
          />
        )}
        {before && after && (
          <>
            <div className="compare-divider" style={{ left: `${split * 100}%` }}>
              <span className="compare-knob">⟷</span>
            </div>
            <span className="compare-label left">Before</span>
            <span className="compare-label right">After</span>
          </>
        )}
        {(!before || !after) && (
          <div className="compare-empty">
            Connect {!before && <b>Before</b>}
            {!before && !after && " and "}
            {!after && <b>After</b>}
          </div>
        )}
      </div>
    </div>
  );
}

export default memo(CompareNode);
