import { useStore } from "zustand";
import { createStore } from "zustand/vanilla";
import type { Command, CommandResult, ImportRequest, NodeRef, ServerEvent, Snapshot } from "../types";
import { ApiError, type StudioApi } from "./client";
import { ProjectConnection, browserSocketUrl, type ConnectionStatus, type SocketLike } from "./connection";
import { applyPending, expectedVersions, predict, type PendingOp } from "./optimistic";
import { applyEvent, fromSnapshot, type ProjectState } from "./state";

export interface Notice {
  id: number;
  kind: "error" | "info";
  text: string;
}

export interface Selection {
  kind: "requirement" | "cluster" | "test_case";
  key: string;
}

export type ViewName = "clusters" | "matrix" | "documents";

export interface StudioState {
  user: string | null;
  projects: { id: string; name: string }[];
  projectsLoaded: boolean;
  server: ProjectState | null;
  pending: PendingOp[];
  status: ConnectionStatus;
  notices: Notice[];
  selection: Selection | null;
  view: ViewName;
  /** Node key (`test_case:...`) whose diff screen is open. */
  diffFor: string | null;

  setUser(name: string): void;
  loadProjects(): Promise<void>;
  importProject(meta: ImportRequest, file: File): Promise<void>;
  openProject(id: string): Promise<void>;
  closeProject(): void;
  send(command: Command): Promise<CommandResult | null>;
  lock(ref: NodeRef): Promise<boolean>;
  select(sel: Selection | null): void;
  setView(v: ViewName): void;
  openDiff(key: string | null): void;
  notify(kind: Notice["kind"], text: string): void;
  dismiss(id: number): void;
  /** Used by the connection and by tests. */
  receiveEvent(ev: ServerEvent): void;
  receiveSnapshot(snap: Snapshot): void;
}

export interface StudioDeps {
  api: StudioApi;
  socketFactory?: (url: string) => SocketLike;
  socketUrl?: (projectId: string, after: number, user: string) => string;
  storage?: Pick<Storage, "getItem" | "setItem">;
  /** Delay before matrix warnings are re-read after matrix-relevant events; 0 disables it. */
  warningRefreshMs?: number;
  /** Time after which an accepted command's optimistic patch is dropped even if no event came. */
  settleTimeoutMs?: number;
  now?: () => number;
}

const USER_KEY = "testmentor.user";

export const REJECTIONS: Record<string, string> = {
  version_conflict: "Bu öğe başka biri tarafından değiştirildi. Güncel hali gösteriliyor, düzenlemeni yeniden yap.",
  locked: "Öğe kilitli: başka bir kullanıcı düzenliyor.",
  invalid: "Komut geçersiz.",
  nothing_to_undo: "Geri alınacak bir işlem yok.",
};

export function rejectionText(reason: string): string {
  const code = reason.split(/[\s:]/)[0] ?? "";
  const base = REJECTIONS[code];
  if (!base) return reason ? `Komut reddedildi: ${reason}` : "Komut reddedildi.";
  const rest = reason.slice(code.length).replace(/^[\s:]+/, "");
  return code === "invalid" && rest ? `${base} ${rest}` : base;
}

const MATRIX_KINDS = new Set(["test_case", "method", "matrix_row", "cluster"]);

export function createStudioStore(deps: StudioDeps) {
  const now = deps.now ?? (() => Date.now());
  const storage = deps.storage ?? (typeof localStorage !== "undefined" ? localStorage : undefined);
  let opId = 0;
  let noticeId = 0;
  let connection: ProjectConnection | null = null;
  let refreshTimer: ReturnType<typeof setTimeout> | null = null;

  const readUser = (): string | null => {
    try {
      return storage?.getItem(USER_KEY) ?? null;
    } catch {
      return null;
    }
  };

  const store = createStore<StudioState>()((set, get) => {
    const settle = () => {
      const { pending, server } = get();
      if (!server || pending.length === 0) return;
      const t = now();
      const keep = pending.filter((op) => op.seq === null || (server.seq < op.seq && t - op.createdAt < (deps.settleTimeoutMs ?? 10000)));
      if (keep.length !== pending.length) set({ pending: keep });
    };

    const dropOp = (id: number) => set((s) => ({ pending: s.pending.filter((o) => o.id !== id) }));

    const scheduleWarningRefresh = () => {
      const ms = deps.warningRefreshMs ?? 0;
      if (!ms || refreshTimer) return;
      refreshTimer = setTimeout(() => {
        refreshTimer = null;
        const id = get().server?.projectId;
        if (!id) return;
        deps.api
          .snapshot(id)
          .then((snap) => {
            const cur = get().server;
            if (!cur || cur.projectId !== id) return;
            const warnings = fromSnapshot(snap, cur).warnings;
            set({ server: { ...cur, warnings } });
          })
          .catch(() => undefined);
      }, ms);
    };

    return {
      user: readUser(),
      projects: [],
      projectsLoaded: false,
      server: null,
      pending: [],
      status: "closed",
      notices: [],
      selection: null,
      view: "clusters",
      diffFor: null,

      setUser(name) {
        const n = name.trim();
        if (!n) return;
        try {
          storage?.setItem(USER_KEY, n);
        } catch {
          /* private mode */
        }
        set({ user: n });
      },

      async loadProjects() {
        try {
          const projects = await deps.api.listProjects();
          set({ projects, projectsLoaded: true });
        } catch (e) {
          set({ projectsLoaded: true });
          get().notify("error", `Projeler yüklenemedi: ${(e as Error).message}`);
        }
      },

      async importProject(meta, file) {
        const snap = await deps.api.createProject(meta, file);
        await get().loadProjects().catch(() => undefined);
        get().receiveSnapshot(snap);
        startConnection(snap.project_id);
      },

      async openProject(id) {
        const snap = await deps.api.snapshot(id);
        set({ server: null, pending: [], selection: null, view: "clusters", diffFor: null });
        get().receiveSnapshot(snap);
        startConnection(id);
      },

      closeProject() {
        connection?.stop();
        connection = null;
        set({ server: null, pending: [], selection: null, status: "closed", diffFor: null });
      },

      async send(command) {
        const { server } = get();
        if (!server) return null;
        const patch = predict(command);
        const op: PendingOp = { id: ++opId, command, patch: patch ?? ((s) => s), seq: null, createdAt: now() };
        if (patch) set((s) => ({ pending: [...s.pending, op] }));
        try {
          const result = await deps.api.command(server.projectId, {
            command,
            expected_versions: expectedVersions(command, server),
          });
          if (result.accepted) {
            set((s) => ({ pending: s.pending.map((o) => (o.id === op.id ? { ...o, seq: result.seq } : o)) }));
            settle();
            const timeout = deps.settleTimeoutMs ?? 10000;
            setTimeout(() => dropOp(op.id), timeout);
          } else {
            dropOp(op.id);
            get().notify("error", rejectionText(result.reason ?? ""));
            if ((result.reason ?? "").startsWith("version_conflict")) {
              deps.api
                .snapshot(server.projectId)
                .then((snap) => get().receiveSnapshot(snap))
                .catch(() => undefined);
            }
          }
          return result;
        } catch (e) {
          dropOp(op.id);
          get().notify("error", e instanceof ApiError ? `Sunucu hatası: ${e.message}` : "Sunucuya ulaşılamadı.");
          return null;
        }
      },

      async lock(ref) {
        const id = get().server?.projectId;
        if (!id) return false;
        try {
          return await deps.api.lock(id, ref);
        } catch {
          return false;
        }
      },

      select(selection) {
        set({ selection });
      },
      setView(view) {
        set({ view });
      },
      openDiff(diffFor) {
        set({ diffFor });
      },
      notify(kind, text) {
        const id = ++noticeId;
        set((s) => ({ notices: [...s.notices.slice(-3), { id, kind, text }] }));
      },
      dismiss(id) {
        set((s) => ({ notices: s.notices.filter((n) => n.id !== id) }));
      },

      receiveEvent(ev) {
        const cur = get().server;
        if (!cur || ev.project_id !== cur.projectId) return;
        const next = applyEvent(cur, ev);
        if (next !== cur) set({ server: next });
        settle();
        const node = (ev.payload as { node?: { ref?: { kind?: string } } } | undefined)?.node;
        if (node?.ref?.kind && MATRIX_KINDS.has(node.ref.kind)) scheduleWarningRefresh();
      },
      receiveSnapshot(snap) {
        set((s) => ({ server: fromSnapshot(snap, s.server ?? undefined) }));
        settle();
      },
    };
  });

  function startConnection(projectId: string) {
    connection?.stop();
    const user = store.getState().user ?? "anonim";
    const factory = deps.socketFactory ?? ((url: string) => new WebSocket(url) as unknown as SocketLike);
    const urlFor = deps.socketUrl ?? browserSocketUrl;
    connection = new ProjectConnection({
      url: (after) => urlFor(projectId, after, user),
      socketFactory: factory,
      getAfter: () => store.getState().server?.seq ?? 0,
      onEvent: (ev) => store.getState().receiveEvent(ev),
      onSnapshot: (snap) => store.getState().receiveSnapshot(snap),
      onStatus: (status) => store.setState({ status }),
    });
    connection.start();
  }

  return store;
}

export type StudioStore = ReturnType<typeof createStudioStore>;

/** The state clients show: server state with the still-unconfirmed local predictions on top. */
export function viewState(s: Pick<StudioState, "server" | "pending">): ProjectState | null {
  return s.server ? applyPending(s.server, s.pending) : null;
}

export function useStudio<T>(store: StudioStore, selector: (s: StudioState) => T): T {
  return useStore(store, selector);
}
