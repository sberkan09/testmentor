import type { Command, NodeView } from "../types";
import type { ProjectState } from "./state";

export type Patch = (s: ProjectState) => ProjectState;

export interface PendingOp {
  id: number;
  command: Command;
  patch: Patch;
  /** Set when the server accepted the command: dropped once the state reaches this seq. */
  seq: number | null;
  createdAt: number;
}

function setNode(s: ProjectState, key: string, fn: (n: NodeView) => NodeView): ProjectState {
  const n = s.nodes[key];
  return n ? { ...s, nodes: { ...s.nodes, [key]: fn(n) } } : s;
}

/** Local prediction of a command, shown until the server's events confirm it. The view is always
 *  `server state + pending patches`, so a rejection only has to drop the patch (server wins). */
export function predict(command: Command): Patch | null {
  switch (command.type) {
    case "move_requirement":
      return (s) => {
        const to = s.nodes[`cluster:${command.to_cluster}`];
        if (!to) return s;
        let next = s;
        for (const n of Object.values(s.nodes)) {
          if (n.ref.kind !== "cluster" || n.ref.key === command.to_cluster) continue;
          const members = (n.content?.["members"] as string[] | undefined) ?? [];
          if (members.includes(command.requirement)) {
            next = setNode(next, `cluster:${n.ref.key}`, (c) => ({
              ...c,
              content: { ...c.content, members: members.filter((m) => m !== command.requirement) },
            }));
          }
        }
        const toMembers = (to.content?.["members"] as string[] | undefined) ?? [];
        if (!toMembers.includes(command.requirement)) {
          next = setNode(next, `cluster:${command.to_cluster}`, (c) => ({
            ...c,
            content: { ...c.content, members: [...toMembers, command.requirement].sort() },
          }));
        }
        return next;
      };
    case "rename_cluster":
      return (s) =>
        setNode(s, `cluster_label:${command.cluster}`, (n) => ({ ...n, content: { ...n.content, name: command.name } }));
    case "edit_requirement":
      return (s) => setNode(s, `requirement:${command.requirement}`, (n) => ({ ...n, content: { ...n.content, text: command.text } }));
    case "edit_test_case":
      return (s) =>
        setNode(s, `test_case:${command.case}`, (n) => ({
          ...n,
          content: { ...command.content } as unknown as Record<string, unknown>,
          pinned: true,
          origin: "edited",
        }));
    case "edit_method":
      return (s) =>
        setNode(s, `method:${command.requirement}`, (n) => ({ ...n, content: { ...n.content, methods: [...command.methods] } }));
    case "pin":
      return (s) => setNode(s, `${command.node.kind}:${command.node.key}`, (n) => ({ ...n, pinned: true }));
    case "unpin":
      return (s) => setNode(s, `${command.node.kind}:${command.node.key}`, (n) => ({ ...n, pinned: false }));
    case "keep_mine":
      return (s) =>
        setNode(s, `${command.node.kind}:${command.node.key}`, (n) => ({ ...n, status: "fresh", pinned_warning: false }));
    case "set_stage_mode":
      return (s) => ({ ...s, stages: s.stages.map((g) => (g.stage === command.stage ? { ...g, mode: command.mode } : g)) });
    default:
      return null;
  }
}

/** Node versions the command expects (`expected_versions`, keyed by `str(NodeRef)`). */
export function expectedVersions(command: Command, s: ProjectState): Record<string, number> {
  let keys: string[];
  switch (command.type) {
    case "edit_test_case":
      keys = [`test_case:${command.case}`];
      break;
    case "edit_requirement":
      keys = [`requirement:${command.requirement}`];
      break;
    case "edit_method":
      keys = [`method:${command.requirement}`];
      break;
    case "rename_cluster":
      keys = [`cluster_label:${command.cluster}`];
      break;
    default:
      return {};
  }
  const out: Record<string, number> = {};
  for (const k of keys) {
    const n = s.nodes[k];
    if (n) out[k] = n.version;
  }
  return out;
}

export function applyPending(server: ProjectState, pending: PendingOp[]): ProjectState {
  return pending.reduce((s, op) => op.patch(s), server);
}
