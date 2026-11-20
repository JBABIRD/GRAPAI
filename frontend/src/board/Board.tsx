import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  SelectionMode,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type IsValidConnection,
  type NodeTypes,
  type OnConnect,
  type OnConnectEnd,
  type OnNodeDrag,
} from "@xyflow/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, canvasToBlob } from "../api";
import ImageEditor, { type EditorResult } from "../editor/ImageEditor";
import type {
  Asset,
  CompareNodeT,
  BoardDoc,
  BoardNode,
  Catalogue,
  ImageNodeT,
  JobOutput,
  NoteNodeT,
  SectionNodeT,
  ToolData,
  ToolNodeT,
  VideoNodeT,
  Workflow,
} from "../types";
import { BoardContext, type BoardActions } from "./BoardContext";
import CompareNode from "./nodes/CompareNode";
import ImageNode from "./nodes/ImageNode";
import NoteNode from "./nodes/NoteNode";
import SectionNode from "./nodes/SectionNode";
import ToolNode from "./nodes/ToolNode";
import VideoNode from "./nodes/VideoNode";
import Toolbar from "./Toolbar";
import ToolPicker from "./ToolPicker";
import { IMAGE_W, TOOL_W, fitSize, freeSpot, rowSpot, inside, nodeSize, uid } from "./util";

const nodeTypes: NodeTypes = { image: ImageNode, video: VideoNode, note: NoteNode, section: SectionNode, tool: ToolNode, compare: CompareNode };

type Props = {
  doc: BoardDoc;
  catalogue: Catalogue;
  onSaveState: (s: "saved" | "saving" | "error") => void;
};

type EditorTarget = { nodeId: string | null; url: string | null; maskUrl: string | null; width: number; height: number; at?: { x: number; y: number }; then?: "erase" };

const IMAGE_INPUT_NODES = new Set(["image"]);

// Compare is a board tool, not an AI workflow; it shares the picker's list format.
/** Width a block needs on its row: itself plus the results it will place to its right. */
function rowWidth(wf: Workflow) {
  const count = wf.id === "views" ? 3 : Math.min(4, Number(wf.params.find((p) => p.name === "count")?.default ?? 1));
  const each = wf.output === "video" ? 424 : 284;
  return TOOL_W + 90 + count * each;
}

/** Tools whose text field is optional: run straight away from the image toolbar. */
const AUTO_RUN = new Set(["erase", "style", "views"]);

const COMPARE_ENTRY = {
  id: "compare",
  name: "Compare",
  description: "Before/after slider. This image is Before; connect an After.",
  output: "image" as const,
  inputs: [],
  params: [],
  model: "",
  license: "",
};

function prepare(nodes: BoardNode[]): BoardNode[] {
  return nodes.map((n) => (n.type === "section" ? { ...n, zIndex: -1 } : n));
}

export default function Board({ doc, catalogue, onSaveState }: Props) {
  const rf = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState<BoardNode>(prepare(doc.nodes));
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(doc.edges);
  const [editor, setEditor] = useState<EditorTarget | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  nodesRef.current = nodes;
  edgesRef.current = edges;
  const polls = useRef(new Set<string>());

  const workflows = useMemo(() => new Map(catalogue.workflows.map((w) => [w.id, w])), [catalogue]);

  const flash = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast((t) => (t === msg ? null : t)), 3500);
  }, []);

  const updateNodeData = useCallback(
    (id: string, patch: Record<string, unknown>) =>
      setNodes((ns) => ns.map((n) => (n.id === id ? ({ ...n, data: { ...n.data, ...patch } } as BoardNode) : n))),
    [setNodes],
  );

  // ---------- placing things on the board ----------
  const centre = useCallback(() => {
    const el = document.querySelector(".react-flow") as HTMLElement | null;
    const r = el?.getBoundingClientRect();
    return rf.screenToFlowPosition({ x: (r?.left ?? 0) + (r?.width ?? 800) / 2, y: (r?.top ?? 0) + (r?.height ?? 600) / 2 });
  }, [rf]);

  const imageNode = (asset: Asset, pos: { x: number; y: number }, extra: Partial<ImageNodeT["data"]> = {}): ImageNodeT => {
    const size = fitSize(asset.width ?? 1024, asset.height ?? 1024);
    return {
      id: uid("img"),
      type: "image",
      position: pos,
      width: size.width,
      height: size.height,
      data: { assetId: asset.id, url: asset.url, width: asset.width ?? 1024, height: asset.height ?? 1024, ...extra },
    };
  };

  const addAssets = useCallback(
    async (files: File[], at: { x: number; y: number }) => {
      let x = at.x;
      for (const f of files) {
        if (!/^image\/(png|jpeg|webp)$|^video\/mp4$/.test(f.type)) {
          flash(`Skipped ${f.name}: use PNG, JPEG, WebP or MP4`);
          continue;
        }
        try {
          const asset = await api.upload(f, f.name);
          if (asset.mime.startsWith("video/")) {
            const node: VideoNodeT = {
              id: uid("vid"),
              type: "video",
              position: { x, y: at.y },
              width: 360,
              height: 203,
              data: { assetId: asset.id, url: asset.url, width: 1280, height: 720, title: f.name },
            };
            setNodes((ns) => [...ns, node]);
            x += 400;
          } else {
            const node = imageNode(asset, { x, y: at.y }, { title: f.name.replace(/\.\w+$/, "") });
            setNodes((ns) => [...ns, node]);
            x += (node.width ?? IMAGE_W) + 40;
          }
        } catch (e) {
          flash(`Upload failed: ${(e as Error).message}`);
        }
      }
    },
    [flash, setNodes],
  );

  const placeResults = useCallback(
    (toolId: string, outputs: JobOutput[], caption: string) => {
      const ns = nodesRef.current;
      const tool = ns.find((n) => n.id === toolId);
      if (!tool) return;
      const toolSize = nodeSize(tool);
      const prior = edgesRef.current
        .filter((e) => e.source === toolId)
        .map((e) => ns.find((n) => n.id === e.target))
        .filter(Boolean) as BoardNode[];
      // One row to the right of the block, top-aligned with it; later runs go in a new row just below.
      const x0 = tool.position.x + toolSize.w + 90;
      let y = prior.length ? Math.max(...prior.map((n) => n.position.y + nodeSize(n).h)) + 40 : tool.position.y;
      let x = x0;
      // Up to 4 in a row; bigger sets (e.g. 6 or 8 views) wrap into two rows.
      const perRow = outputs.length <= 4 ? outputs.length : Math.ceil(outputs.length / 2);
      let rowH = 0;
      const created: BoardNode[] = [];
      outputs.forEach((o, i) => {
        if (i > 0 && i % perRow === 0) {
          x = x0;
          y += rowH + 40;
          rowH = 0;
        }
        const w = o.kind === "video" ? 400 : 260;
        const size = fitSize(o.asset.width ?? o.poster?.width ?? 16, o.asset.height ?? o.poster?.height ?? 9, w);
        const pos = rowSpot([...ns, ...created], { x, y }, size.width, size.height + 20);
        x = pos.x + size.width + 24;
        rowH = Math.max(rowH, size.height + 20 + (pos.y - y));
        const view = typeof o.meta?.view === "string" ? o.meta.view : "";
        const label = view ? `${caption} · ${view}` : caption;
        if (o.kind === "video") {
          created.push({
            id: uid("vid"),
            type: "video",
            position: pos,
            width: size.width,
            height: size.height,
            data: {
              assetId: o.asset.id,
              url: o.asset.url,
              posterUrl: o.poster?.url,
              width: o.poster?.width ?? 1280,
              height: o.poster?.height ?? 720,
              caption: label,
            },
          });
        } else {
          created.push({ ...imageNode(o.asset, pos, { caption: label }), width: size.width, height: size.height });
        }
      });
      setNodes((cur) => [...cur, ...created]);
      setEdges((cur) => [
        ...cur,
        ...created.map((n) => ({
          id: uid("e"),
          source: toolId,
          sourceHandle: "out",
          target: n.id,
          targetHandle: "in",
          className: "edge-result",
        })),
      ]);
    },
    [setEdges, setNodes],
  );

  // ---------- jobs ----------
  const poll = useCallback(
    (toolId: string, jobId: string, caption: string) => {
      if (polls.current.has(jobId)) return;
      polls.current.add(jobId);
      const tick = async () => {
        try {
          const job = await api.job(jobId);
          if (job.status === "done") {
            polls.current.delete(jobId);
            const tool = nodesRef.current.find((n) => n.id === toolId) as ToolNodeT | undefined;
            updateNodeData(toolId, { status: "done", progress: 1, message: "", jobId: null, runs: (tool?.data.runs ?? 0) + 1 });
            placeResults(toolId, job.outputs, caption);
            return;
          }
          if (job.status === "error") {
            polls.current.delete(jobId);
            updateNodeData(toolId, { status: "error", error: job.error ?? "failed", jobId: null });
            return;
          }
          updateNodeData(toolId, { status: "running", progress: job.progress, message: job.message });
        } catch (e) {
          polls.current.delete(jobId);
          updateNodeData(toolId, { status: "error", error: `Lost track of the job: ${(e as Error).message}`, jobId: null });
          return;
        }
        window.setTimeout(tick, 700);
      };
      tick();
    },
    [placeResults, updateNodeData],
  );

  const runTool = useCallback(
    async (toolId: string) => {
      const tool = nodesRef.current.find((n) => n.id === toolId) as ToolNodeT | undefined;
      if (!tool || tool.data.status === "running") return;
      const wf = workflows.get(tool.data.workflow);
      if (!wf) return;
      const inputs: Record<string, string | null> = {};
      for (const e of edgesRef.current.filter((e) => e.target === toolId)) {
        const src = nodesRef.current.find((n) => n.id === e.source);
        if (!src || !e.targetHandle) continue;
        if (!IMAGE_INPUT_NODES.has(src.type ?? "")) continue;
        const d = (src as ImageNodeT).data;
        inputs[e.targetHandle] = d.assetId;
        if (e.targetHandle === "image" && d.maskAssetId && wf.inputs.some((i) => i.name === "mask")) inputs.mask = d.maskAssetId;
      }
      const missing = wf.inputs.filter((i) => i.kind === "image" && i.required && !inputs[i.name]);
      if (wf.inputs.some((i) => i.kind === "mask" && i.required) && inputs.image && !inputs.mask) {
        updateNodeData(toolId, { status: "error", error: "Paint a mask over the object first: Draw, then Mask (M)" });
        return;
      }
      if (missing.length) {
        updateNodeData(toolId, { status: "error", error: `Connect an image to ${missing.map((m) => m.label).join(", ")}` });
        return;
      }
      updateNodeData(toolId, { status: "running", progress: 0, message: "queued", error: null });
      try {
        const job = await api.submitJob(wf.id, inputs, tool.data.params);
        updateNodeData(toolId, { jobId: job.id });
        const prompt = String(tool.data.params.prompt ?? "").trim();
        poll(toolId, job.id, prompt ? `${wf.name}: ${prompt}` : wf.name);
      } catch (e) {
        updateNodeData(toolId, { status: "error", error: (e as Error).message });
      }
    },
    [poll, updateNodeData, workflows],
  );

  // Resume jobs that were running when the board was last open.
  useEffect(() => {
    for (const n of nodesRef.current) {
      if (n.type === "tool" && n.data.status === "running") {
        if (n.data.jobId) poll(n.id, n.data.jobId, "");
        else updateNodeData(n.id, { status: "idle" });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const addTool = useCallback(
    (workflow: string, pos: { x: number; y: number }, sources: string[] = [], exact = false, overrides: Record<string, unknown> = {}) => {
      const wf = workflows.get(workflow);
      if (!wf) return null;
      const params: Record<string, unknown> = {};
      wf.params.forEach((p) => (params[p.name] = p.default));
      Object.assign(params, overrides);
      const tool: ToolNodeT = {
        id: uid("tool"),
        type: "tool",
        // Reserve the taller of the block and its results so both fit on the same row.
        position: exact ? pos : rowSpot(nodesRef.current, pos, rowWidth(wf), Math.max(200 + wf.inputs.length * 30 + wf.params.length * 40, 300)),
        width: TOOL_W,
        data: { workflow, params, status: "idle" } satisfies ToolData,
      };
      const handles = wf.inputs.filter((i) => i.kind === "image").map((i) => i.name);
      const newEdges: Edge[] = sources.slice(0, handles.length).map((s, i) => ({
        id: uid("e"),
        source: s,
        sourceHandle: "out",
        target: tool.id,
        targetHandle: handles[i],
      }));
      setNodes((ns) => [...ns.map((n) => ({ ...n, selected: false })), { ...tool, selected: true }]);
      setEdges((es) => [...es, ...newEdges]);
      return tool.id;
    },
    [setEdges, setNodes, workflows],
  );

  const quickAction = useCallback(
    (nodeId: string, workflow: string) => {
      const ns = nodesRef.current;
      const node = ns.find((n) => n.id === nodeId);
      if (!node) return;
      // Edit takes extra selected images as references (@2, @3); other tools use just this one.
      // Edit takes extra selected images as references (@2, @3); Style takes one as the style.
      const selected =
        workflow === "edit" || workflow === "style"
          ? ns.filter((n) => n.selected && n.type === "image" && n.id !== nodeId).map((n) => n.id)
          : [];
      const size = nodeSize(node);
      const toolId = addTool(workflow, { x: node.position.x + size.w + 90, y: node.position.y }, [nodeId, ...selected]);
      const wf = workflows.get(workflow);
      const ready = workflow !== "style" || selected.length > 0;
      if (toolId && wf && ready && (AUTO_RUN.has(workflow) || wf.params.every((p) => p.kind !== "text"))) {
        window.setTimeout(() => runTool(toolId), 80);
      }
    },
    [addTool, runTool, workflows],
  );

  const addCompare = useCallback(
    (pos: { x: number; y: number }, before?: string | null, after?: string | null, exact = false) => {
      const ref = nodesRef.current.find((n) => n.id === (after ?? before)) as ImageNodeT | undefined;
      const w = 360;
      const h = Math.round(w * ((ref?.data.height ?? 3) / (ref?.data.width ?? 4))) + 32;
      const node: CompareNodeT = {
        id: uid("cmp"),
        type: "compare",
        position: exact ? pos : rowSpot(nodesRef.current, pos, w, h),
        width: w,
        height: h,
        data: { split: 0.5 },
      };
      const links: Edge[] = [];
      if (before) links.push({ id: uid("e"), source: before, sourceHandle: "out", target: node.id, targetHandle: "before" });
      if (after) links.push({ id: uid("e"), source: after, sourceHandle: "out", target: node.id, targetHandle: "after" });
      setNodes((ns) => [...ns.map((n) => ({ ...n, selected: false })), { ...node, selected: true }]);
      setEdges((es) => [...es, ...links]);
      return node.id;
    },
    [setEdges, setNodes],
  );

  /** Compare a result with the image that went into the block that made it. */
  const compareWith = useCallback(
    (nodeId: string) => {
      const ns = nodesRef.current, es = edgesRef.current;
      const node = ns.find((n) => n.id === nodeId);
      if (!node) return;
      const producer = es.find((e) => e.target === nodeId && ns.find((n) => n.id === e.source)?.type === "tool");
      const input = producer && es.find((e) => e.target === producer.source && e.targetHandle === "image");
      const size = nodeSize(node);
      const pos = { x: node.position.x + size.w + 60, y: node.position.y };
      if (input) addCompare(pos, input.source, nodeId);
      else addCompare(pos, nodeId, null);
    },
    [addCompare],
  );

  /** Erase what is masked; with no mask yet, open the editor on the mask brush first. */
  const eraseObject = useCallback(
    (nodeId: string) => {
      const n = nodesRef.current.find((x) => x.id === nodeId) as ImageNodeT | undefined;
      if (!n || n.type !== "image") return;
      if (n.data.maskAssetId) quickAction(nodeId, "erase");
      else setEditor({ nodeId, url: n.data.url, maskUrl: null, width: n.data.width, height: n.data.height, then: "erase" });
    },
    [quickAction],
  );

  const outpaint = useCallback(
    (nodeId: string, pads: { left: number; top: number; right: number; bottom: number }, prompt = "") => {
      const node = nodesRef.current.find((n) => n.id === nodeId);
      if (!node) return;
      const size = nodeSize(node);
      const toolId = addTool("outpaint", { x: node.position.x + size.w + 90, y: node.position.y }, [nodeId], false, { ...pads, prompt });
      if (toolId) window.setTimeout(() => runTool(toolId), 80);
    },
    [addTool, runTool],
  );

  const deleteNode = useCallback((nodeId: string) => rf.deleteElements({ nodes: [{ id: nodeId }] }), [rf]);

  const openEditor = useCallback((nodeId: string) => {
    const n = nodesRef.current.find((x) => x.id === nodeId) as ImageNodeT | undefined;
    if (!n || n.type !== "image") return;
    setEditor({ nodeId, url: n.data.url, maskUrl: n.data.maskUrl ?? null, width: n.data.width, height: n.data.height });
  }, []);

  const newSketch = useCallback(() => {
    const c = centre();
    setEditor({ nodeId: null, url: null, maskUrl: null, width: 1280, height: 896, at: { x: c.x - 150, y: c.y - 100 } });
  }, [centre]);

  const saveEditor = useCallback(
    async (res: EditorResult) => {
      const target = editor;
      setEditor(null);
      if (!target) return;
      try {
        const asset = await api.upload(res.image, "sketch.png");
        let mask: Asset | null | undefined = undefined;
        if (res.mask === null) mask = null;
        else if (res.mask) mask = await api.upload(res.mask, "mask.png");
        const maskPatch =
          mask === undefined ? {} : { maskAssetId: mask ? mask.id : null, maskUrl: mask ? mask.url : null };
        if (target.nodeId) {
          updateNodeData(target.nodeId, { assetId: asset.id, url: asset.url, width: asset.width, height: asset.height, ...maskPatch });
          if (target.then === "erase") {
            const nodeId = target.nodeId;
            if (mask) window.setTimeout(() => quickAction(nodeId, "erase"), 120);
            else flash("Nothing to erase: paint a mask over the object");
          }
        } else {
          const node = imageNode(asset, target.at ?? centre(), { sketch: true, title: "Sketch", ...maskPatch });
          setNodes((ns) => [...ns.map((n) => ({ ...n, selected: false })), { ...node, selected: true }]);
        }
      } catch (e) {
        flash(`Could not save: ${(e as Error).message}`);
      }
    },
    [centre, editor, flash, quickAction, setNodes, updateNodeData],
  );

  const saveVideoFrame = useCallback(
    async (nodeId: string, time: number) => {
      const n = nodesRef.current.find((x) => x.id === nodeId) as VideoNodeT | undefined;
      if (!n) return;
      try {
        const v = document.createElement("video");
        v.crossOrigin = "anonymous";
        v.muted = true;
        v.src = n.data.url;
        await new Promise<void>((ok, fail) => {
          v.onloadeddata = () => ok();
          v.onerror = () => fail(new Error("video failed to load"));
        });
        v.currentTime = Math.min(time, Math.max(0, v.duration - 0.05));
        await new Promise<void>((ok) => (v.onseeked = () => ok()));
        const c = document.createElement("canvas");
        c.width = v.videoWidth;
        c.height = v.videoHeight;
        c.getContext("2d")!.drawImage(v, 0, 0);
        const asset = await api.upload(await canvasToBlob(c), "frame.png");
        const size = nodeSize(n);
        const node = imageNode(asset, { x: n.position.x, y: n.position.y + size.h + 40 }, { caption: `Frame at ${time.toFixed(1)} s` });
        setNodes((ns) => [...ns, node]);
        setEdges((es) => [...es, { id: uid("e"), source: nodeId, sourceHandle: null, target: node.id, targetHandle: "in", className: "edge-result" }]);
      } catch (e) {
        flash(`Could not grab the frame: ${(e as Error).message}`);
      }
    },
    [flash, setEdges, setNodes],
  );

  const clearMask = useCallback((nodeId: string) => updateNodeData(nodeId, { maskAssetId: null, maskUrl: null }), [updateNodeData]);

  const actions: BoardActions = useMemo(
    () => ({
      catalogue,
      workflow: (id) => workflows.get(id),
      presets: catalogue.presets,
      runTool,
      updateNodeData,
      openEditor,
      quickAction,
      compareWith,
      eraseObject,
      outpaint,
      saveVideoFrame,
      clearMask,
      deleteNode,
    }),
    [catalogue, workflows, runTool, updateNodeData, openEditor, quickAction, compareWith, eraseObject, outpaint, saveVideoFrame, clearMask, deleteNode],
  );

  // ---------- connections ----------
  const isValidConnection: IsValidConnection = useCallback((c) => {
    const target = nodesRef.current.find((n) => n.id === c.target);
    const source = nodesRef.current.find((n) => n.id === c.source);
    if (source?.type !== "image" || c.source === c.target || !c.targetHandle) return false;
    if (target?.type === "compare") return c.targetHandle === "before" || c.targetHandle === "after";
    return target?.type === "tool" && c.targetHandle !== "out";
  }, []);

  const onConnect: OnConnect = useCallback(
    (c: Connection) =>
      setEdges((es) =>
        addEdge({ ...c, id: uid("e") }, es.filter((e) => !(e.target === c.target && e.targetHandle === c.targetHandle))),
      ),
    [setEdges],
  );

  // Dragging a connection out of an image and dropping it on empty canvas offers the tools.
  const [picker, setPicker] = useState<{ screen: { x: number; y: number }; flow: { x: number; y: number }; source: string } | null>(null);
  const onConnectEnd: OnConnectEnd = useCallback(
    (event, state) => {
      if (state.isValid || state.toNode || !state.fromNode || state.fromNode.type !== "image") return;
      if (state.fromHandle?.type !== "source") return;
      const pt = "changedTouches" in event ? event.changedTouches[0] : (event as MouseEvent);
      const box = (document.querySelector(".board") as HTMLElement | null)?.getBoundingClientRect();
      setPicker({
        screen: { x: pt.clientX - (box?.left ?? 0), y: pt.clientY - (box?.top ?? 0) },
        flow: rf.screenToFlowPosition({ x: pt.clientX, y: pt.clientY }),
        source: state.fromNode.id,
      });
    },
    [rf],
  );
  const pickTool = useCallback(
    (workflow: string) => {
      if (!picker) return;
      setPicker(null);
      if (workflow === "compare") {
        addCompare({ x: picker.flow.x + 20, y: picker.flow.y - 40 }, picker.source, null, true);
        return;
      }
      // The block's first input sits about 120 px below its top edge; line it up with the drop point.
      const toolId = addTool(workflow, { x: picker.flow.x + 20, y: picker.flow.y - 120 }, [picker.source], true);
      const wf = workflows.get(workflow);
      if (toolId && wf && wf.params.every((p) => p.kind !== "text")) window.setTimeout(() => runTool(toolId), 80);
    },
    [addCompare, addTool, picker, runTool, workflows],
  );

  // ---------- sections carry their contents ----------
  const dragGroup = useRef<{ id: string; start: { x: number; y: number }; members: Map<string, { x: number; y: number }> } | null>(null);
  const onNodeDragStart: OnNodeDrag<BoardNode> = useCallback((_, node) => {
    if (node.type !== "section") return;
    const members = new Map<string, { x: number; y: number }>();
    nodesRef.current.forEach((n) => {
      if (n.id !== node.id && n.type !== "section" && inside(n, node)) members.set(n.id, { ...n.position });
    });
    dragGroup.current = { id: node.id, start: { ...node.position }, members };
  }, []);
  const onNodeDrag: OnNodeDrag<BoardNode> = useCallback(
    (_, node) => {
      const g = dragGroup.current;
      if (!g || g.id !== node.id) return;
      const dx = node.position.x - g.start.x;
      const dy = node.position.y - g.start.y;
      setNodes((ns) => ns.map((n) => (g.members.has(n.id) ? { ...n, position: { x: g.members.get(n.id)!.x + dx, y: g.members.get(n.id)!.y + dy } } : n)));
    },
    [setNodes],
  );
  const onNodeDragStop = useCallback(() => (dragGroup.current = null), []);

  // ---------- adding things ----------
  const addNote = useCallback(() => {
    const c = centre();
    const n: NoteNodeT = { id: uid("note"), type: "note", position: freeSpot(nodesRef.current, { x: c.x - 100, y: c.y - 70 }, 200, 140), width: 200, height: 140, data: { text: "", color: "#fff4b8" } };
    setNodes((ns) => [...ns, n]);
  }, [centre, setNodes]);

  const addSection = useCallback(() => {
    const sel = nodesRef.current.filter((n) => n.selected && n.type !== "section");
    let box = { x: centre().x - 300, y: centre().y - 200, w: 600, h: 400 };
    if (sel.length) {
      const xs = sel.map((n) => n.position.x), ys = sel.map((n) => n.position.y);
      const xe = sel.map((n) => n.position.x + nodeSize(n).w), ye = sel.map((n) => n.position.y + nodeSize(n).h);
      box = { x: Math.min(...xs) - 40, y: Math.min(...ys) - 70, w: Math.max(...xe) - Math.min(...xs) + 80, h: Math.max(...ye) - Math.min(...ys) + 110 };
    }
    const s: SectionNodeT = { id: uid("sec"), type: "section", position: { x: box.x, y: box.y }, width: box.w, height: box.h, zIndex: -1, data: { title: "Section" } };
    setNodes((ns) => [s, ...ns]);
  }, [centre, setNodes]);

  const fileInput = useRef<HTMLInputElement>(null);
  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const files = Array.from(e.dataTransfer.files);
      if (files.length) addAssets(files, rf.screenToFlowPosition({ x: e.clientX, y: e.clientY }));
    },
    [addAssets, rf],
  );

  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, textarea")) return;
      const files = Array.from(e.clipboardData?.files ?? []);
      if (files.length) {
        e.preventDefault();
        addAssets(files, centre());
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, textarea, select") || editor) return;
      const sel = nodesRef.current.filter((n) => n.selected);
      if (e.key === "e" && sel[0]?.type === "image") quickAction(sel[0].id, "edit");
      else if (e.key === "n") addNote();
      else if (e.key === "s" && !e.metaKey && !e.ctrlKey) addSection();
      else if (e.key === "d" && !e.metaKey && !e.ctrlKey) newSketch();
      else if (e.key === "!" || (e.shiftKey && e.code === "Digit1")) rf.fitView({ padding: 0.15, duration: 300 });
      else if (e.shiftKey && e.code === "Digit2" && sel.length) rf.fitView({ nodes: sel, padding: 0.2, duration: 300 });
    };
    window.addEventListener("paste", onPaste);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("paste", onPaste);
      window.removeEventListener("keydown", onKey);
    };
  }, [addAssets, addNote, addSection, centre, editor, newSketch, quickAction, rf]);

  // ---------- autosave ----------
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    onSaveState("saving");
    const t = window.setTimeout(() => {
      const clean = nodes.map(({ selected: _s, dragging: _d, measured: _m, ...rest }) => rest) as BoardNode[];
      api
        .saveBoard({ ...doc, nodes: clean, edges, viewport: rf.getViewport() })
        .then(() => onSaveState("saved"))
        .catch(() => onSaveState("error"));
    }, 800);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges]);

  const empty = nodes.length === 0;

  return (
    <BoardContext.Provider value={actions}>
      <div className="board" onDragOver={(e) => e.preventDefault()} onDrop={onDrop}>
        <ReactFlow<BoardNode, Edge>
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onConnectEnd={onConnectEnd}
          onPaneClick={() => setPicker(null)}
          onMoveStart={() => setPicker(null)}
          isValidConnection={isValidConnection}
          onNodeDragStart={onNodeDragStart}
          onNodeDrag={onNodeDrag}
          onNodeDragStop={onNodeDragStop}
          defaultViewport={doc.viewport ?? { x: 0, y: 0, zoom: 1 }}
          minZoom={0.05}
          maxZoom={6}
          panOnScroll
          zoomOnPinch
          selectionOnDrag
          panOnDrag={[1, 2]}
          selectionMode={SelectionMode.Partial}
          deleteKeyCode={["Backspace", "Delete"]}
          multiSelectionKeyCode={["Shift", "Meta", "Control"]}
          proOptions={{ hideAttribution: true }}
          defaultEdgeOptions={{ type: "default" }}
          colorMode="dark"
        >
          <Background variant={BackgroundVariant.Dots} gap={24} size={1.4} color="var(--dots)" />
          <MiniMap pannable zoomable nodeColor={(n) => (n.type === "tool" ? "#ff8a3d" : n.type === "section" ? "#2a2c31" : "#6b7280")} maskColor="rgba(10,10,12,0.6)" />
          <Controls showInteractive={false} />
        </ReactFlow>
        <Toolbar
          workflows={catalogue.workflows}
          onSketch={newSketch}
          onUpload={() => fileInput.current?.click()}
          onNote={addNote}
          onSection={addSection}
          onTool={(w) => {
            const c = centre();
            const sel = nodesRef.current.filter((n) => n.selected && n.type === "image");
            if (sel.length) {
              const right = Math.max(...sel.map((n) => n.position.x + nodeSize(n).w));
              addTool(w, { x: right + 90, y: sel[0].position.y }, sel.map((n) => n.id));
            } else addTool(w, { x: c.x - TOOL_W / 2, y: c.y - 160 });
          }}
          onFit={() => rf.fitView({ padding: 0.15, duration: 300 })}
          onCompare={() => {
            const sel = nodesRef.current
              .filter((n) => n.selected && n.type === "image")
              .sort((a, b) => a.position.x - b.position.x || a.position.y - b.position.y);
            if (sel.length === 1) compareWith(sel[0].id);
            else if (sel.length >= 2) {
              const right = Math.max(...sel.map((n) => n.position.x + nodeSize(n).w));
              addCompare({ x: right + 60, y: sel[0].position.y }, sel[0].id, sel[1].id);
            } else {
              const c = centre();
              addCompare({ x: c.x - 180, y: c.y - 140 });
            }
          }}
        />
        <input
          ref={fileInput}
          type="file"
          accept="image/png,image/jpeg,image/webp,video/mp4"
          multiple
          hidden
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = "";
            const c = centre();
            addAssets(files, { x: c.x - 150, y: c.y - 100 });
          }}
        />
        {empty && (
          <div className="empty-hint">
            <h2>Start with a sketch, an image or an idea</h2>
            <div>
              <button onClick={newSketch}>Draw a sketch</button>
              <button onClick={() => fileInput.current?.click()}>Upload images</button>
              <button
                onClick={() => {
                  const c = centre();
                  addTool("create", { x: c.x - TOOL_W / 2, y: c.y - 200 });
                }}
              >
                Create from text
              </button>
            </div>
            <p>Drop or paste images anywhere. Connect images to tool blocks; results land beside the block.</p>
          </div>
        )}
        {picker && (
          <ToolPicker
            at={picker.screen}
            workflows={[
              ...catalogue.workflows.filter((w) => w.inputs.some((i) => i.kind === "image" && i.required)),
              COMPARE_ENTRY,
            ]}
            onPick={pickTool}
            onClose={() => setPicker(null)}
          />
        )}
        {toast && <div className="toast">{toast}</div>}
      </div>
      {editor && (
        <ImageEditor
          src={editor.url}
          maskSrc={editor.maskUrl}
          maskHint={editor.then === "erase" ? "Paint over what should disappear, then Save: it is erased and filled with background." : undefined}
          width={editor.width}
          height={editor.height}
          onCancel={() => setEditor(null)}
          onSave={saveEditor}
        />
      )}
    </BoardContext.Provider>
  );
}

