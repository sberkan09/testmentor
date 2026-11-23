import type { MatrixRowView, MethodDef, NodeView, StageView, TestCaseContent } from "../types";
import type { ProjectState } from "./state";

export interface ReqItem {
  id: string;
  text: string;
  language: string;
  node: NodeView;
  covered: boolean;
}

export interface ClusterItem {
  key: string;
  name: string;
  rationale: string;
  labelNode: NodeView | undefined;
  node: NodeView;
  members: ReqItem[];
  pinnedMembers: string[];
  caseKeys: string[];
}

export function nodesOfKind(state: ProjectState, kind: string): NodeView[] {
  return Object.values(state.nodes).filter((n) => n.ref.kind === kind);
}

function str(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}

export function testCaseContent(node: NodeView | undefined): TestCaseContent | null {
  const c = node?.content;
  if (!c || c["kind"] !== "test_case") return null;
  return c as unknown as TestCaseContent;
}

/** Test case nodes keyed by node key (`<cluster>:<case id>`). */
export function testCases(state: ProjectState): NodeView[] {
  return nodesOfKind(state, "test_case").sort((a, b) => a.ref.key.localeCompare(b.ref.key, "tr", { numeric: true }));
}

export function coverageIndex(state: ProjectState): Map<string, string[]> {
  const idx = new Map<string, string[]>();
  for (const n of testCases(state)) {
    for (const rid of testCaseContent(n)?.covers ?? []) {
      const list = idx.get(rid);
      if (list) list.push(n.ref.key);
      else idx.set(rid, [n.ref.key]);
    }
  }
  return idx;
}

export function requirements(state: ProjectState): Map<string, ReqItem> {
  const cov = coverageIndex(state);
  const out = new Map<string, ReqItem>();
  for (const n of nodesOfKind(state, "requirement")) {
    const c = n.content ?? {};
    const id = str(c["id"], n.ref.key);
    out.set(n.ref.key, {
      id,
      text: str(c["text"]),
      language: str(c["language"]),
      node: n,
      covered: (cov.get(id)?.length ?? 0) > 0,
    });
  }
  return out;
}

export function clusters(state: ProjectState): ClusterItem[] {
  const reqs = requirements(state);
  const items: ClusterItem[] = [];
  for (const n of nodesOfKind(state, "cluster")) {
    const c = n.content ?? {};
    const memberKeys = Array.isArray(c["members"]) ? (c["members"] as string[]) : [];
    const label = state.nodes[`cluster_label:${n.ref.key}`];
    const set = state.nodes[`test_set:${n.ref.key}`];
    const setKeys = set?.content && Array.isArray(set.content["case_keys"]) ? (set.content["case_keys"] as string[]) : null;
    const caseKeys =
      setKeys ??
      testCases(state)
        .map((t) => t.ref.key)
        .filter((k) => k.startsWith(`${n.ref.key}:`));
    items.push({
      key: n.ref.key,
      name: str(label?.content?.["name"], n.ref.key),
      rationale: str(label?.content?.["rationale"]),
      labelNode: label,
      node: n,
      members: memberKeys.map((k) => reqs.get(k)).filter((r): r is ReqItem => r !== undefined),
      pinnedMembers: Array.isArray(c["pinned_members"]) ? (c["pinned_members"] as string[]) : [],
      caseKeys,
    });
  }
  return items.sort((a, b) => a.name.localeCompare(b.name, "tr", { numeric: true }));
}

export function projectMethods(state: ProjectState): MethodDef[] {
  const card = state.nodes["project_card:card"];
  const m = card?.content?.["methods"];
  return Array.isArray(m) ? (m as MethodDef[]) : [];
}

export function matrixRows(state: ProjectState): MatrixRowView[] {
  const cov = coverageIndex(state);
  const owner = new Map<string, ClusterItem>();
  for (const c of clusters(state)) for (const m of c.members) owner.set(m.id, c);
  const rows: MatrixRowView[] = [];
  for (const r of requirements(state).values()) {
    const methodNode = state.nodes[`method:${r.node.ref.key}`];
    const methods = Array.isArray(methodNode?.content?.["methods"]) ? (methodNode?.content?.["methods"] as string[]) : [];
    const keys = cov.get(r.id) ?? [];
    const cl = owner.get(r.id);
    const w = state.warnings[r.id] ?? "";
    rows.push({
      requirement_id: r.id,
      text: r.text,
      language: r.language,
      cluster: cl?.key ?? "",
      cluster_name: cl?.name ?? "",
      methods,
      test_case_keys: keys,
      covered: keys.length > 0,
      warning: w === "test_without_case" || w === "case_without_test_method" ? w : "",
    });
  }
  return rows.sort((a, b) => a.requirement_id.localeCompare(b.requirement_id, "tr", { numeric: true }));
}

export const STAGE_LABELS: Record<string, string> = {
  requirement: "Gereksinimler",
  project_card: "Proje kartı",
  kb_index: "Bilgi havuzu",
  cluster: "Öbekler",
  embedding: "Embedding",
  clustering: "Öbekleme",
  method: "Doğrulama yöntemi",
  cluster_label: "Öbek adı",
  retrieval: "Arama",
  test_set: "Test seti",
  test_case: "Test durumu",
  matrix_row: "Matris",
};

/** Stages shown in the bar: counts come from the node map (they follow events), mode and
 *  approval flag from the stage list. */
export function stageViews(state: ProjectState): StageView[] {
  return state.stages.map((s) => {
    const nodes = nodesOfKind(state, s.stage);
    if (nodes.length === 0) return s;
    const count = (st: string) => nodes.filter((n) => n.status === st).length;
    return { ...s, fresh: count("fresh"), stale: count("stale"), running: count("running"), failed: count("failed") };
  });
}

export function runningText(state: ProjectState): { key: string; text: string } | null {
  const keys = Object.keys(state.progress);
  const last = keys[keys.length - 1];
  return last ? { key: last, text: state.progress[last] ?? "" } : null;
}
