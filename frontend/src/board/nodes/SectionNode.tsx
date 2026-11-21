import { NodeResizer, type NodeProps } from "@xyflow/react";
import { memo } from "react";
import type { SectionNodeT } from "../../types";
import { useBoard } from "../BoardContext";

function SectionNode({ id, data, selected }: NodeProps<SectionNodeT>) {
  const { updateNodeData } = useBoard();
  return (
    <div className={`section-item${selected ? " selected" : ""}`}>
      <NodeResizer isVisible={selected} minWidth={200} minHeight={150} color="var(--accent)" />
      <input
        className="section-title nodrag"
        value={data.title}
        onChange={(e) => updateNodeData(id, { title: e.target.value })}
        aria-label="Section title"
      />
    </div>
  );
}

export default memo(SectionNode);
