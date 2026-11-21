import { NodeResizer, type NodeProps } from "@xyflow/react";
import { memo } from "react";
import type { NoteNodeT } from "../../types";
import { useBoard } from "../BoardContext";

const COLORS = ["#fff4b8", "#ffd9c7", "#d6f0ff", "#dcf5dc", "#eadcff"];

function NoteNode({ id, data, selected }: NodeProps<NoteNodeT>) {
  const { updateNodeData } = useBoard();
  return (
    <div className="item note-item" style={{ background: data.color }}>
      <NodeResizer isVisible={selected} minWidth={120} minHeight={80} color="var(--accent)" />
      <textarea
        className="nodrag nowheel"
        value={data.text}
        placeholder="Note…"
        onChange={(e) => updateNodeData(id, { text: e.target.value })}
      />
      {selected && (
        <div className="note-colors">
          {COLORS.map((c) => (
            <button key={c} style={{ background: c }} onClick={() => updateNodeData(id, { color: c })} aria-label="note colour" />
          ))}
        </div>
      )}
    </div>
  );
}

export default memo(NoteNode);
