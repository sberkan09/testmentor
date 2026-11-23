import type { NodeView, Snapshot, StageView } from "../types";

/** Seeded generator (mulberry32): the same seed always gives the same snapshot. */
function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function node(kind: NodeView["ref"]["kind"], key: string, content: Record<string, unknown>): NodeView {
  return { ref: { kind, key }, status: "fresh", pinned: false, origin: "generated", version: 1, content };
}

export interface SyntheticOptions {
  requirements?: number;
  clusters?: number;
  /** Mean test cases per requirement (the total is about requirements × casesPerRequirement). */
  casesPerRequirement?: number;
  /** Share of requirements no test case covers. */
  uncoveredShare?: number;
  seed?: number;
  projectId?: string;
}

/** A large, fixed project for the layer view performance test: no API, no model. Cluster sizes
 *  vary, test cases cover 1 to 3 requirements of their own cluster, and a share of requirements
 *  stays uncovered. Ids are zero padded so the numeric and plain sort agree. */
export function syntheticSnapshot(opts: SyntheticOptions = {}): Snapshot {
  const nReq = opts.requirements ?? 2000;
  const nClusters = opts.clusters ?? 80;
  const perReq = opts.casesPerRequirement ?? 2.5;
  const uncoveredShare = opts.uncoveredShare ?? 0.05;
  const rand = rng(opts.seed ?? 7);
  const pad = (n: number, w: number) => String(n).padStart(w, "0");

  const nodes: NodeView[] = [
    node("project_card", "card", { kind: "project_card", text: "Sentetik proje", methods: [{ name: "Test", criterion: "" }] }),
  ];
  const reqIds: string[] = [];
  for (let i = 1; i <= nReq; i++) {
    const id = `R${pad(i, 4)}`;
    reqIds.push(id);
    nodes.push(node("requirement", id, { kind: "requirement", id, text: `Sistem ${id} işlevini yerine getirmelidir.`, language: "tr", source: "" }));
    nodes.push(node("method", id, { kind: "method", methods: ["Test"], rationale: "" }));
  }

  // Uneven cluster sizes: weights from 0.3 to 2.3, every requirement in exactly one cluster.
  const weights = Array.from({ length: nClusters }, () => 0.3 + rand() * 2);
  const total = weights.reduce((a, b) => a + b, 0);
  const shuffled = [...reqIds];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j]!, shuffled[i]!];
  }
  let cursor = 0;
  let caseNo = 0;
  for (let c = 0; c < nClusters; c++) {
    const key = `C${pad(c + 1, 3)}`;
    const size = c === nClusters - 1 ? shuffled.length - cursor : Math.max(1, Math.round((weights[c]! / total) * nReq));
    const members = shuffled.slice(cursor, cursor + size).sort();
    cursor += size;
    nodes.push(node("cluster", key, { kind: "cluster", members, pinned_members: [] }));
    nodes.push(node("cluster_label", key, { kind: "cluster_label", name: `Öbek ${pad(c + 1, 3)}`, rationale: "" }));
    const coverable = members.filter(() => rand() >= uncoveredShare);
    const caseKeys: string[] = [];
    const nCases = coverable.length ? Math.round(members.length * perReq) : 0;
    for (let t = 0; t < nCases; t++) {
      caseNo++;
      const id = `TC-${pad(caseNo, 5)}`;
      // Every coverable requirement gets at least one case; the rest pick at random.
      const first = coverable[t % coverable.length]!;
      const covers = new Set([first]);
      const extra = Math.floor(rand() * 3);
      for (let e = 0; e < extra; e++) covers.add(coverable[Math.floor(rand() * coverable.length)]!);
      const caseKey = `${key}:${id}`;
      caseKeys.push(caseKey);
      nodes.push(
        node("test_case", caseKey, {
          kind: "test_case",
          id,
          title: `${first} için senaryo`,
          covers: [...covers].sort(),
          type: "Fonksiyonel",
          priority: "Orta",
          preconditions: "",
          test_inputs: "",
          assumptions: "",
          steps: [{ no: 1, action: "İşlemi başlat", expected: "İşlem tamamlanır" }],
        }),
      );
    }
    nodes.push(node("test_set", key, { kind: "test_set", case_keys: caseKeys }));
  }

  const count = (kind: string) => nodes.filter((n) => n.ref.kind === kind).length;
  const stage = (s: StageView["stage"]): StageView => ({ stage: s, mode: "auto", fresh: count(s), stale: 0, running: 0, failed: 0, waiting_approval: false });
  return {
    project_id: opts.projectId ?? "SYN",
    name: "Sentetik 2.000 gereksinim",
    seq: 1,
    nodes,
    stages: (["cluster", "cluster_label", "method", "test_set", "test_case"] as const).map(stage),
    jobs: [],
    matrix: [],
    locks: {},
  };
}
