import { Handle, NodeResizer, NodeToolbar, Position, type NodeProps } from "@xyflow/react";
import { memo, useRef } from "react";
import { download } from "../../api";
import type { VideoNodeT } from "../../types";
import { useBoard } from "../BoardContext";

function VideoNode({ id, data, selected }: NodeProps<VideoNodeT>) {
  const { saveVideoFrame } = useBoard();
  const ref = useRef<HTMLVideoElement>(null);
  return (
    <div className="item video-item">
      <NodeResizer isVisible={selected} keepAspectRatio minWidth={120} minHeight={70} color="var(--accent)" />
      <Handle type="target" position={Position.Left} id="in" className="handle-in" isConnectable={false} />
      <video ref={ref} className="nodrag" src={data.url} poster={data.posterUrl} controls loop muted playsInline autoPlay />
      {data.caption && <div className="caption" title={data.caption}>{data.caption}</div>}
      <NodeToolbar position={Position.Top} className="node-toolbar">
        <button
          onClick={() => {
            const v = ref.current;
            if (v) {
              v.pause();
              saveVideoFrame(id, v.currentTime);
            }
          }}
          title="Pause and place this frame on the board, to start the next shot"
        >
          Save frame
        </button>
        <button onClick={() => download(data.url, `${data.title ?? "ductus"}-${id}.mp4`)}>↓ MP4</button>
      </NodeToolbar>
    </div>
  );
}

export default memo(VideoNode);
