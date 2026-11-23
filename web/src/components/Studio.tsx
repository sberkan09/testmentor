import { Suspense, lazy, useEffect } from "react";
import { useActions, useStudio, useView } from "../context";
import { ClusterView } from "./ClusterView";
import { DiffDialog } from "./DiffDialog";
import { Inspector } from "./Inspector";
import { MatrixView } from "./MatrixView";
import { StageBar } from "./StageBar";
import { initials } from "./ui";

// The 3D layer view (three.js) is a separate chunk: the 2D views never load it.
const LayerView = lazy(() => import("../views/layers/LayerView"));

const CONN_LABEL = { connecting: "Bağlanıyor", open: "Canlı", reconnecting: "Yeniden bağlanıyor", closed: "Bağlantı yok" } as const;

function isEditable(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
}

export function Studio() {
  const state = useView();
  const view = useStudio((s) => s.view);
  const status = useStudio((s) => s.status);
  const user = useStudio((s) => s.user) ?? "";
  const { setView, closeProject, send } = useActions();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "z" && !isEditable(e.target)) {
        e.preventDefault();
        void send({ type: "undo" });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [send]);

  if (!state) return null;
  return (
    <div className="shell" data-testid="studio">
      <header className="topbar">
        <button className="brand" onClick={closeProject} aria-label="Projelere dön" data-testid="home">
          <span className="brand-mark">t</span>
          testmentor
        </button>
        <span className="crumb">/</span>
        <span className="project-name" data-testid="project-name">{state.name}</span>
        <div className="seg" role="tablist" aria-label="Görünüm">
          <button role="tab" aria-selected={view === "clusters"} data-testid="view-clusters" onClick={() => setView("clusters")}>
            Öbekler
          </button>
          <button role="tab" aria-selected={view === "matrix"} data-testid="view-matrix" onClick={() => setView("matrix")}>
            Matris
          </button>
          <button role="tab" aria-selected={view === "layers"} data-testid="view-layers" onClick={() => setView("layers")}>
            Katmanlar
          </button>
        </div>
        <div className="spacer" />
        <span className={`conn ${status}`} data-testid="connection">
          <span className="dot" />
          {CONN_LABEL[status]}
        </span>
        <span className="user-chip">
          <span className="avatar">{initials(user)}</span>
          {user}
        </span>
      </header>
      <div className="workspace">
        <main className="canvas">
          {view === "clusters" ? (
            <ClusterView />
          ) : view === "matrix" ? (
            <MatrixView />
          ) : (
            <Suspense fallback={<div className="empty">3B katman görünümü yükleniyor…</div>}>
              <LayerView />
            </Suspense>
          )}
        </main>
        <aside className="inspector" aria-label="Denetçi" data-testid="inspector">
          <Inspector />
        </aside>
      </div>
      <StageBar />
      <DiffDialog />
    </div>
  );
}
