import { ReactFlowProvider } from "@xyflow/react";
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import Board from "./board/Board";
import type { BoardDoc, BoardSummary, Catalogue } from "./types";

const LAST_BOARD = "ductus.lastBoard";

function readLast(): string | null {
  try {
    return localStorage.getItem(LAST_BOARD);
  } catch {
    return null;
  }
}
function writeLast(id: string) {
  try {
    localStorage.setItem(LAST_BOARD, id);
  } catch {
    /* private mode */
  }
}

export default function App() {
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [provider, setProvider] = useState<string>("");
  const [boards, setBoards] = useState<BoardSummary[]>([]);
  const [doc, setDoc] = useState<BoardDoc | null>(null);
  const [saveState, setSaveState] = useState<"saved" | "saving" | "error">("saved");
  const [menu, setMenu] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = useCallback(async (id: string) => {
    const d = await api.board(id);
    setDoc(d);
    writeLast(id);
    setMenu(false);
  }, []);

  const refreshBoards = useCallback(() => api.boards().then(setBoards), []);

  useEffect(() => {
    (async () => {
      try {
        const [cat, health, list] = await Promise.all([api.catalogue(), api.health(), api.boards()]);
        setCatalogue(cat);
        setProvider(health.provider);
        setBoards(list);
        const last = readLast();
        const pick = list.find((b) => b.id === last) ?? list[0];
        if (pick) await open(pick.id);
        else {
          const created = await api.createBoard("My first board");
          setDoc(created);
          writeLast(created.id);
          refreshBoards();
        }
      } catch (e) {
        setError(`Cannot reach the Ductus API (${(e as Error).message}). Start it with: uvicorn ductus.api:app`);
      }
    })();
  }, [open, refreshBoards]);

  const newBoard = async () => {
    const d = await api.createBoard("Untitled board");
    await refreshBoards();
    setDoc(d);
    writeLast(d.id);
    setMenu(false);
  };

  const rename = async (name: string) => {
    if (!doc) return;
    const next = { ...doc, name };
    setDoc(next);
    const current = await api.board(doc.id);
    await api.saveBoard({ ...current, name });
    refreshBoards();
  };

  if (error) return <div className="fatal">{error}</div>;
  if (!catalogue || !doc) return <div className="fatal">Loading Ductus…</div>;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <svg viewBox="0 0 32 32" width="22" height="22" aria-hidden>
            <path d="M5 22c5-12 13-12 19-4" stroke="var(--accent)" strokeWidth="3.2" fill="none" strokeLinecap="round" />
            <circle cx="24.5" cy="18" r="2.6" fill="var(--accent)" />
          </svg>
          <span>Ductus</span>
        </div>
        <div className="board-switch">
          <input
            className="board-name"
            value={doc.name}
            onChange={(e) => setDoc({ ...doc, name: e.target.value })}
            onBlur={(e) => rename(e.target.value || "Untitled board")}
            aria-label="Board name"
          />
          <button onClick={() => (refreshBoards(), setMenu((m) => !m))} title="All boards">
            ▾
          </button>
          {menu && (
            <div className="board-menu" onMouseLeave={() => setMenu(false)}>
              <button className="new" onClick={newBoard}>
                + New board
              </button>
              {boards.map((b) => (
                <button key={b.id} className={b.id === doc.id ? "on" : ""} onClick={() => open(b.id)}>
                  <span>{b.name}</span>
                  <em>{b.items} items</em>
                </button>
              ))}
            </div>
          )}
        </div>
        <span className={`save-state ${saveState}`}>{{ saved: "Saved", saving: "Saving…", error: "Not saved" }[saveState]}</span>
        <div className="spacer" />
        <span className={`provider ${provider}`} title="Model backend">
          {provider === "mock" ? "Preview mode (no GPU)" : `Models: ${provider}`}
        </span>
      </header>
      <ReactFlowProvider key={doc.id}>
        <Board doc={doc} catalogue={catalogue} onSaveState={setSaveState} />
      </ReactFlowProvider>
    </div>
  );
}
