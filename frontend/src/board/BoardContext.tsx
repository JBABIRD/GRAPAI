import { createContext, useContext } from "react";
import type { Catalogue, Preset, Workflow } from "../types";

export type BoardActions = {
  catalogue: Catalogue;
  workflow: (id: string) => Workflow | undefined;
  presets: Preset[];
  runTool: (toolId: string) => void;
  updateNodeData: (id: string, patch: Record<string, unknown>) => void;
  openEditor: (nodeId: string) => void;
  quickAction: (nodeId: string, workflow: string) => void;
  compareWith: (nodeId: string) => void;
  saveVideoFrame: (nodeId: string, time: number) => void;
  clearMask: (nodeId: string) => void;
  deleteNode: (nodeId: string) => void;
};

export const BoardContext = createContext<BoardActions | null>(null);

export function useBoard(): BoardActions {
  const ctx = useContext(BoardContext);
  if (!ctx) throw new Error("useBoard outside BoardContext");
  return ctx;
}
