import { createContext, useContext, useMemo, useState } from "react";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { clusters, testCaseContent, type ClusterItem, type ReqItem } from "../api/selectors";
import type { ProjectState } from "../api/state";
import { useActions, useStudio, useView } from "../context";
import { PinIcon, StatusPill } from "./ui";

type Zoom = "far" | "ids" | "text";

// Marking chips (shift/ctrl click) goes through a context so chips stay light.
const MarksContext = createContext<(key: string) => void>(() => undefined);
const useMarks = () => useContext(MarksContext);

const ZOOM_LABEL: Record<Zoom, string> = { far: "Uzak", ids: "Orta", text: "Yakın" };

function Chip({
  req,
  from,
  zoom,
  selected,
  marked,
  showWarn,
  onOpenMove,
}: {
  req: ReqItem;
  from: string;
  zoom: Zoom;
  selected: boolean;
  marked: boolean;
  showWarn: boolean;
  onOpenMove: (key: string) => void;
}) {
  const { select } = useActions();
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `req:${req.node.ref.key}`,
    data: { requirement: req.node.ref.key, from },
  });
  const toggleMark = useMarks();
  const cls = ["chip", selected && "selected", marked && "marked", isDragging && "dragging", req.node.status === "stale" && "stale"]
    .filter(Boolean)
    .join(" ");
  return (
    <button
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      className={cls}
      data-testid={`chip-${req.id}`}
      title={req.text}
      onClick={(e) => {
        if (e.shiftKey || e.metaKey || e.ctrlKey) toggleMark(req.node.ref.key);
        else select({ kind: "requirement", key: req.node.ref.key });
      }}
      onKeyDown={(e) => {
        if (e.key === "m" || e.key === "M") {
          e.preventDefault();
          onOpenMove(req.node.ref.key);
        } else listeners?.["onKeyDown"]?.(e);
      }}
    >
      <span className="cid">{req.id}</span>
      {zoom === "text" && <span className="ctext">{req.text}</span>}
      {req.node.pinned && <PinIcon size={12} />}
      {showWarn && !req.covered && (
        <span className="warn-badge" title="Kapsanmamış gereksinim" data-testid={`uncovered-${req.id}`}>
          !
        </span>
      )}
    </button>
  );
}

function ClusterCard({
  cluster,
  state,
  zoom,
  selectedReq,
  selectedCluster,
  selectedCase,
  marks,
  clusterMarked,
  anyCases,
  onToggleCluster,
  onOpenMove,
  onDelete,
}: {
  cluster: ClusterItem;
  state: ProjectState;
  zoom: Zoom;
  selectedReq: string | null;
  selectedCluster: boolean;
  selectedCase: string | null;
  marks: Set<string>;
  clusterMarked: boolean;
  anyCases: boolean;
  onToggleCluster: (key: string) => void;
  onOpenMove: (key: string) => void;
  onDelete: (key: string) => void;
}) {
  const { select, send } = useActions();
  const { setNodeRef, isOver } = useDroppable({ id: `cluster:${cluster.key}` });
  const [renaming, setRenaming] = useState<string | null>(null);
  const label = cluster.labelNode;
  const status = label?.status === "failed" || cluster.node.status === "failed" ? "failed" : label?.status === "stale" ? "stale" : "";
  const streamed = state.progress[`cluster_label:${cluster.key}`] ?? state.progress[`test_set:${cluster.key}`];
  const cls = ["cluster-card", selectedCluster && "selected", isOver && "over", status].filter(Boolean).join(" ");

  function commitRename() {
    const name = renaming?.trim();
    setRenaming(null);
    if (name && name !== cluster.name) void send({ type: "rename_cluster", cluster: cluster.key, name });
  }

  return (
    <section ref={setNodeRef} className={cls} data-testid={`cluster-${cluster.key}`} aria-label={cluster.name}>
      <div className="cluster-head">
        <input
          type="checkbox"
          aria-label={`${cluster.name} öbeğini seç`}
          checked={clusterMarked}
          onChange={() => onToggleCluster(cluster.key)}
          data-testid={`cluster-mark-${cluster.key}`}
          style={{ marginTop: 4 }}
        />
        {renaming !== null ? (
          <input
            className="input"
            autoFocus
            value={renaming}
            data-testid={`cluster-rename-input-${cluster.key}`}
            onChange={(e) => setRenaming(e.target.value)}
            onBlur={commitRename}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitRename();
              if (e.key === "Escape") setRenaming(null);
            }}
          />
        ) : (
          <h3 data-testid={`cluster-name-${cluster.key}`} onClick={() => select({ kind: "cluster", key: cluster.key })} onDoubleClick={() => setRenaming(cluster.name)}>
            {cluster.name}
          </h3>
        )}
        {label?.pinned && <PinIcon />}
        <span className="count" title="Gereksinim sayısı">{cluster.members.length}</span>
      </div>
      {label?.status === "running" || streamed ? (
        <div className="streaming" data-testid={`stream-${cluster.key}`}>{streamed ?? "Üretiliyor…"}</div>
      ) : (
        cluster.rationale && zoom !== "far" && <p className="rationale">{cluster.rationale}</p>
      )}
      {zoom !== "far" && (
        <div className={`chips${zoom === "text" ? " verbose" : ""}`}>
          {cluster.members.map((r) => (
            <Chip
              key={r.node.ref.key}
              req={r}
              from={cluster.key}
              zoom={zoom}
              selected={selectedReq === r.node.ref.key}
              marked={marks.has(r.node.ref.key)}
              showWarn={anyCases}
              onOpenMove={onOpenMove}
            />
          ))}
        </div>
      )}
      {zoom !== "far" && cluster.caseKeys.length > 0 && (
        <div className="cluster-cases">
          {cluster.caseKeys.map((k) => {
            const n = state.nodes[`test_case:${k}`];
            if (!n) return null;
            const c = testCaseContent(n);
            const stream = state.progress[`test_case:${k}`];
            return (
              <button
                key={k}
                className={`case-row ${n.status === "stale" ? "stale" : ""} ${n.status === "failed" ? "failed" : ""} ${selectedCase === k ? "selected" : ""}`}
                data-testid={`case-${k}`}
                onClick={() => select({ kind: "test_case", key: k })}
              >
                <span className="cid">{c?.id ?? k}</span>
                <span className="ctitle">{stream ?? c?.title ?? "Üretiliyor…"}</span>
                {n.pinned && <PinIcon size={12} />}
                {n.status !== "fresh" && <StatusPill node={n} />}
              </button>
            );
          })}
        </div>
      )}
      <div className="card-actions">
        <button className="btn ghost small" onClick={() => setRenaming(cluster.name)} data-testid={`cluster-rename-${cluster.key}`}>
          Yeniden adlandır
        </button>
        <button className="btn ghost small" onClick={() => onDelete(cluster.key)} data-testid={`cluster-delete-${cluster.key}`}>
          Sil
        </button>
        {status === "failed" && (
          <button className="btn small danger" onClick={() => void send({ type: "regenerate", node: label?.ref ?? cluster.node.ref })}>
            Yeniden dene
          </button>
        )}
      </div>
    </section>
  );
}

function MoveDialog({ reqKey, clusterList, current, onClose }: { reqKey: string; clusterList: ClusterItem[]; current: string; onClose: () => void }) {
  const { send } = useActions();
  const [to, setTo] = useState(clusterList.find((c) => c.key !== current)?.key ?? "");
  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Gereksinimi taşı" onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <div className="dialog" style={{ width: 420 }} data-testid="move-dialog">
        <h2>{reqKey} gereksinimini taşı</h2>
        <p className="sub">Hedef öbeği seç.</p>
        <div className="field">
          <label htmlFor="move-to">Hedef öbek</label>
          <select id="move-to" className="select" autoFocus value={to} onChange={(e) => setTo(e.target.value)} data-testid="move-target">
            {clusterList
              .filter((c) => c.key !== current)
              .map((c) => (
                <option key={c.key} value={c.key}>
                  {c.name}
                </option>
              ))}
          </select>
        </div>
        <div className="dialog-actions">
          <button className="btn" onClick={onClose}>
            Vazgeç
          </button>
          <button
            className="btn primary"
            data-testid="move-confirm"
            disabled={!to}
            onClick={() => {
              void send({ type: "move_requirement", requirement: reqKey, to_cluster: to });
              onClose();
            }}
          >
            Taşı
          </button>
        </div>
      </div>
    </div>
  );
}

function DeleteDialog({ cluster, clusterList, onClose }: { cluster: ClusterItem; clusterList: ClusterItem[]; onClose: () => void }) {
  const { send } = useActions();
  const others = clusterList.filter((c) => c.key !== cluster.key);
  const [to, setTo] = useState(others[0]?.key ?? "");
  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Öbeği sil">
      <div className="dialog" style={{ width: 460 }}>
        <h2>"{cluster.name}" öbeği silinsin mi?</h2>
        <p className="sub">{cluster.members.length} gereksinim seçtiğin öbeğe taşınır. Sabit test durumları kaybolmaz.</p>
        <div className="field">
          <label htmlFor="del-to">Gereksinimlerin yeni öbeği</label>
          <select id="del-to" className="select" value={to} onChange={(e) => setTo(e.target.value)}>
            {others.map((c) => (
              <option key={c.key} value={c.key}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <div className="dialog-actions">
          <button className="btn" onClick={onClose}>
            Vazgeç
          </button>
          <button
            className="btn danger"
            disabled={!to}
            data-testid="delete-confirm"
            onClick={() => {
              const destinations: Record<string, string> = {};
              for (const m of cluster.members) destinations[m.node.ref.key] = to;
              void send({ type: "delete_cluster", cluster: cluster.key, destinations });
              onClose();
            }}
          >
            Sil
          </button>
        </div>
      </div>
    </div>
  );
}

export function ClusterView() {
  const state = useView();
  const selection = useStudio((s) => s.selection);
  const { send } = useActions();
  const [zoom, setZoom] = useState<Zoom | null>(null);
  // Starts at the first cut's distance threshold (config/pipeline.yaml clustering.distance_threshold;
  // D6: 0.35); the snapshot does not carry it.
  const [granularity, setGranularity] = useState(0.35);
  const [marks, setMarks] = useState<Set<string>>(new Set());
  const [markedClusters, setMarkedClusters] = useState<Set<string>>(new Set());
  const [dragging, setDragging] = useState<string | null>(null);
  const [moveReq, setMoveReq] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { keyboardCodes: { start: ["Space"], cancel: ["Escape"], end: ["Space"] } }),
  );

  const list = useMemo(() => (state ? clusters(state) : []), [state]);
  if (!state) return null;

  const total = list.reduce((n, c) => n + c.members.length, 0);
  const effZoom: Zoom = zoom ?? (total > 150 ? "far" : "ids");
  const anyCases = Object.keys(state.nodes).some((k) => k.startsWith("test_case:"));
  const reqIndex = new Map<string, ReqItem>();
  for (const c of list) for (const m of c.members) reqIndex.set(m.node.ref.key, m);
  const selReq = selection?.kind === "requirement" ? selection.key : null;
  const selCase = selection?.kind === "test_case" ? selection.key : null;

  const toggleMark = (key: string) =>
    setMarks((prev) => {
      const n = new Set(prev);
      if (n.has(key)) n.delete(key);
      else n.add(key);
      return n;
    });
  const toggleCluster = (key: string) =>
    setMarkedClusters((prev) => {
      const n = new Set(prev);
      if (n.has(key)) n.delete(key);
      else n.add(key);
      return n;
    });

  function onDragStart(e: DragStartEvent) {
    setDragging(String(e.active.data.current?.["requirement"] ?? ""));
  }
  function onDragEnd(e: DragEndEvent) {
    setDragging(null);
    const requirement = e.active.data.current?.["requirement"] as string | undefined;
    const from = e.active.data.current?.["from"] as string | undefined;
    const over = e.over ? String(e.over.id) : "";
    if (!requirement || !over.startsWith("cluster:")) return;
    const to = over.slice("cluster:".length);
    if (to !== from) void send({ type: "move_requirement", requirement, to_cluster: to });
  }

  const fromCluster = (req: string) => list.find((c) => c.members.some((m) => m.node.ref.key === req))?.key ?? "";
  const deleteTarget = list.find((c) => c.key === deleting);

  return (
    <MarksContext.Provider value={toggleMark}>
      <div className="canvas-toolbar" data-testid="cluster-toolbar">
        <div className="summary">
          <span>
            <strong data-testid="cluster-count">{list.length}</strong> öbek
          </span>
          <span>
            <strong>{total}</strong> gereksinim
          </span>
        </div>
        <label className="slider">
          Ayrıntı
          <input
            type="range"
            min={0.1}
            max={1.9}
            step={0.05}
            value={granularity}
            data-testid="granularity"
            aria-label="Öbek ayrıntısı"
            onChange={(e) => setGranularity(Number(e.target.value))}
            onPointerUp={() => void send({ type: "set_granularity", distance_threshold: granularity })}
            onKeyUp={() => void send({ type: "set_granularity", distance_threshold: granularity })}
          />
          <span style={{ width: 32 }}>{granularity.toFixed(2)}</span>
        </label>
        <div className="seg" role="group" aria-label="Yakınlaştırma">
          {(Object.keys(ZOOM_LABEL) as Zoom[]).map((z) => (
            <button key={z} aria-pressed={effZoom === z} onClick={() => setZoom(z)} data-testid={`zoom-${z}`}>
              {ZOOM_LABEL[z]}
            </button>
          ))}
        </div>
        <div className="spacer" />
        {marks.size > 0 && (
          <button
            className="btn small"
            data-testid="create-cluster"
            onClick={() => {
              void send({ type: "create_cluster", members: [...marks].sort() as [string, ...string[]] });
              setMarks(new Set());
            }}
          >
            Seçilenlerden yeni öbek ({marks.size})
          </button>
        )}
        {markedClusters.size >= 2 && (
          <button
            className="btn small"
            data-testid="merge-clusters"
            onClick={() => {
              void send({ type: "merge_clusters", sources: [...markedClusters].sort() as [string, string, ...string[]] });
              setMarkedClusters(new Set());
            }}
          >
            Öbekleri birleştir ({markedClusters.size})
          </button>
        )}
      </div>
      <div className="canvas-body">
        {list.length === 0 ? (
          <div className="empty" data-testid="clusters-empty">
            <strong>Öbekler hazırlanıyor</strong>
            <span>İlk kesim bitince öbekler burada görünür.</span>
          </div>
        ) : (
          <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd} onDragCancel={() => setDragging(null)}>
            <div className="cluster-grid" data-testid="cluster-grid">
              {list.map((c) => (
                <ClusterCard
                  key={c.key}
                  cluster={c}
                  state={state}
                  zoom={effZoom}
                  selectedReq={selReq}
                  selectedCluster={selection?.kind === "cluster" && selection.key === c.key}
                  selectedCase={selCase}
                  marks={marks}
                  clusterMarked={markedClusters.has(c.key)}
                  anyCases={anyCases}
                  onToggleCluster={toggleCluster}
                  onOpenMove={setMoveReq}
                  onDelete={setDeleting}
                />
              ))}
            </div>
            <DragOverlay>
              {dragging && reqIndex.get(dragging) ? (
                <span className="chip overlay">
                  <span className="cid">{reqIndex.get(dragging)?.id}</span>
                </span>
              ) : null}
            </DragOverlay>
          </DndContext>
        )}
      </div>
      {moveReq && <MoveDialog reqKey={moveReq} clusterList={list} current={fromCluster(moveReq)} onClose={() => setMoveReq(null)} />}
      {deleteTarget && <DeleteDialog cluster={deleteTarget} clusterList={list} onClose={() => setDeleting(null)} />}
    </MarksContext.Provider>
  );
}
