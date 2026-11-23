import type { Command, JobView, NodeRef, NodeView, ServerEvent, Snapshot, StageView } from "../types";
import { refKey } from "../types";

export interface HistoryEntry {
  seq: number;
  version: number;
  origin: string;
  actor: string;
}

export interface ActivityEntry {
  seq: number;
  actor: string;
  type: string;
  command?: Command;
}

/** Client copy of the server state at event `seq`. Only `applyEvent` and `fromSnapshot` change it. */
export interface ProjectState {
  projectId: string;
  name: string;
  seq: number;
  nodes: Record<string, NodeView>;
  stages: StageView[];
  jobs: Record<string, JobView>;
  /** requirement id -> matrix warning (the only matrix part the client cannot derive). */
  warnings: Record<string, string>;
  locks: Record<string, string>;
  /** Streamed text of running jobs, by node key (`job_progress`, not persisted). */
  progress: Record<string, string>;
  history: Record<string, HistoryEntry[]>;
  activity: ActivityEntry[];
}

const HISTORY_LIMIT = 20;
const ACTIVITY_LIMIT = 30;
const SKIPPED_KINDS = new Set(["embedding", "clustering"]);

export function fromSnapshot(snap: Snapshot, prev?: ProjectState): ProjectState {
  const nodes: Record<string, NodeView> = {};
  for (const n of snap.nodes) {
    if (!SKIPPED_KINDS.has(n.ref.kind)) nodes[refKey(n.ref)] = n;
  }
  const jobs: Record<string, JobView> = {};
  for (const j of snap.jobs) jobs[j.id] = j;
  const warnings: Record<string, string> = {};
  for (const row of snap.matrix) if (row.warning) warnings[row.requirement_id] = row.warning;
  return {
    projectId: snap.project_id,
    name: snap.name,
    seq: snap.seq,
    nodes,
    stages: [...snap.stages],
    jobs,
    warnings,
    locks: { ...snap.locks },
    progress: {},
    history: prev?.projectId === snap.project_id ? prev.history : {},
    activity: prev?.projectId === snap.project_id ? prev.activity : [],
  };
}

function withoutKey<T>(rec: Record<string, T>, key: string): Record<string, T> {
  if (!(key in rec)) return rec;
  const next = { ...rec };
  delete next[key];
  return next;
}

function nodeOf(payload: Record<string, unknown>): NodeView | null {
  const n = payload["node"];
  return n && typeof n === "object" && "ref" in n ? (n as NodeView) : null;
}

function jobOf(payload: Record<string, unknown>): JobView | null {
  const j = payload["job"];
  return j && typeof j === "object" && "id" in j ? (j as JobView) : null;
}

function upsert(state: ProjectState, node: NodeView, ev: ServerEvent): ProjectState {
  if (SKIPPED_KINDS.has(node.ref.kind)) return state;
  const key = refKey(node.ref);
  const prev = state.nodes[key];
  let history = state.history;
  if (!prev || prev.version !== node.version) {
    const entry: HistoryEntry = { seq: ev.seq, version: node.version, origin: node.origin, actor: ev.actor ?? "" };
    history = { ...history, [key]: [...(history[key] ?? []), entry].slice(-HISTORY_LIMIT) };
  }
  return {
    ...state,
    nodes: { ...state.nodes, [key]: node },
    progress: node.status === "running" ? state.progress : withoutKey(state.progress, key),
    history,
  };
}

function applyCommand(state: ProjectState, command: Command): ProjectState {
  if (command.type === "set_stage_mode") {
    return { ...state, stages: state.stages.map((s) => (s.stage === command.stage ? { ...s, mode: command.mode } : s)) };
  }
  if (command.type === "approve_stage") {
    return {
      ...state,
      stages: state.stages.map((s) => (s.stage === command.stage ? { ...s, waiting_approval: false } : s)),
    };
  }
  return state;
}

/** Apply one server event. Duplicates (seq not above the current one) are ignored; gaps are
 *  accepted because `job_progress` events are not persisted and may not take part in the count. */
export function applyEvent(state: ProjectState, ev: ServerEvent): ProjectState {
  const payload = (ev.payload ?? {}) as Record<string, unknown>;

  if (ev.type === "job_progress") {
    const job = jobOf(payload);
    const text = typeof payload["text"] === "string" ? payload["text"] : "";
    if (!job || !text) return state;
    const key = refKey(job.node);
    return { ...state, progress: { ...state.progress, [key]: (state.progress[key] ?? "") + text } };
  }

  if (ev.seq <= state.seq) return state;
  let next: ProjectState = { ...state, seq: ev.seq };

  switch (ev.type) {
    case "node_created":
    case "node_updated":
    case "node_stale": {
      const node = nodeOf(payload);
      if (node) {
        next = upsert(next, node, ev);
      } else if (ev.type === "node_stale" && payload["ref"]) {
        const key = refKey(payload["ref"] as NodeRef);
        const cur = next.nodes[key];
        if (cur) next = { ...next, nodes: { ...next.nodes, [key]: { ...cur, status: "stale" } } };
      }
      break;
    }
    case "node_removed": {
      const r = payload["ref"] as NodeRef | undefined;
      if (r) {
        const key = refKey(r);
        next = { ...next, nodes: withoutKey(next.nodes, key), progress: withoutKey(next.progress, key) };
      }
      break;
    }
    case "job_started": {
      const job = jobOf(payload);
      if (job) next = { ...next, jobs: { ...next.jobs, [job.id]: { ...job, state: "running" } } };
      break;
    }
    case "job_done":
    case "job_failed": {
      const job = jobOf(payload);
      if (job) {
        next = { ...next, jobs: withoutKey(next.jobs, job.id), progress: withoutKey(next.progress, refKey(job.node)) };
      }
      break;
    }
    case "stage_waiting_approval": {
      const stage = payload["stage"];
      next = {
        ...next,
        stages: next.stages.map((s) => (s.stage === stage ? { ...s, waiting_approval: true } : s)),
      };
      break;
    }
    case "lock_changed": {
      const ref = payload["ref"];
      const user = payload["user"];
      if (typeof ref === "string") {
        next = { ...next, locks: typeof user === "string" && user ? { ...next.locks, [ref]: user } : withoutKey(next.locks, ref) };
      }
      break;
    }
    case "command_applied": {
      const command = payload["command"] as Command | undefined;
      if (command) {
        next = applyCommand(next, command);
        if (command.type !== "focus") {
          next = {
            ...next,
            activity: [...next.activity, { seq: ev.seq, actor: ev.actor ?? "", type: String(command.type), command }].slice(-ACTIVITY_LIMIT),
          };
        }
      }
      break;
    }
    case "command_rejected":
      break;
  }
  return next;
}
