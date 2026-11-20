import type { Edge, Node } from "@xyflow/react";

export type InputSpec = { name: string; kind: "image" | "mask"; required: boolean; label: string };
export type ParamSpec = {
  name: string;
  kind: "text" | "number" | "select" | "preset" | "seed";
  label: string;
  default: unknown;
  min?: number | null;
  max?: number | null;
  step?: number | null;
  options?: (string | number)[] | null;
};
export type Workflow = {
  id: string;
  name: string;
  description: string;
  output: "image" | "video" | "mesh";
  inputs: InputSpec[];
  params: ParamSpec[];
  model: string;
  license: string;
};
export type Preset = { id: string; name: string; prompt: string };
export type Catalogue = { workflows: Workflow[]; presets: Preset[] };

export type Asset = { id: string; mime: string; url: string; width: number | null; height: number | null };
export type JobOutput = { kind: "image" | "video" | "file"; asset: Asset; poster?: Asset; meta: Record<string, unknown> };
export type Job = {
  id: string;
  workflow: string;
  status: "queued" | "running" | "done" | "error";
  progress: number;
  message: string;
  error: string | null;
  outputs: JobOutput[];
};

export type ImageData = {
  assetId: string;
  url: string;
  width: number;
  height: number;
  title?: string;
  maskAssetId?: string | null;
  maskUrl?: string | null;
  sketch?: boolean;
  caption?: string;
};
export type VideoData = { assetId: string; url: string; posterUrl?: string; width: number; height: number; title?: string; caption?: string };
export type NoteData = { text: string; color: string };
export type SectionData = { title: string };
export type ToolStatus = "idle" | "running" | "done" | "error";
export type ToolData = {
  workflow: string;
  params: Record<string, unknown>;
  status: ToolStatus;
  progress?: number;
  message?: string;
  error?: string | null;
  jobId?: string | null;
  runs?: number;
};

export type ImageNodeT = Node<ImageData, "image">;
export type VideoNodeT = Node<VideoData, "video">;
export type NoteNodeT = Node<NoteData, "note">;
export type SectionNodeT = Node<SectionData, "section">;
export type ToolNodeT = Node<ToolData, "tool">;
export type CompareData = { split: number };
export type CompareNodeT = Node<CompareData, "compare">;
export type BoardNode = ImageNodeT | VideoNodeT | NoteNodeT | SectionNodeT | ToolNodeT | CompareNodeT;

export type BoardDoc = {
  id: string;
  name: string;
  nodes: BoardNode[];
  edges: Edge[];
  viewport?: { x: number; y: number; zoom: number };
  updated?: number;
};
export type BoardSummary = { id: string; name: string; updated: number; items: number };
