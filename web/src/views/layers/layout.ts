import { clusters, testCaseContent } from "../../api/selectors";
import type { ProjectState } from "../../api/state";

/** Pure layout of the layer view: no three.js here, so it is unit tested without WebGL.
 *  Three stacked planes, bottom to top in pipeline order: clusters (requirement points on
 *  cluster islands), test cases, matrix rows. Coordinates are world units, y is up. */

export type LayerKind = "cluster" | "requirement" | "test_case" | "matrix";

export interface ClusterIsland {
  /** Cluster node key; "" for the island of requirements in no cluster. */
  key: string;
  name: string;
  x: number;
  z: number;
  radius: number;
  count: number;
  uncovered: number;
}

export interface ReqPoint {
  key: string;
  id: string;
  x: number;
  z: number;
  covered: boolean;
  cluster: string;
}

export interface CasePoint {
  key: string;
  id: string;
  x: number;
  z: number;
  cluster: string;
}

export interface MatrixCell {
  /** Requirement node key of the row. */
  key: string;
  id: string;
  x: number;
  z: number;
  /** Edge length of the cell. */
  size: number;
  covered: boolean;
  warning: boolean;
}

export interface LayerLayout {
  islands: ClusterIsland[];
  reqs: ReqPoint[];
  cases: CasePoint[];
  matrix: MatrixCell[];
  /** Thread segments as xyz pairs: requirement → test case and test case → matrix row. */
  threads: Float32Array;
  /** First segment of each island's threads (length islands + 1). */
  threadStarts: number[];
  /** Far view threads: covered requirement → its island's test case hub, hub → matrix block. */
  bundles: Float32Array;
  bundleStarts: number[];
  levels: { clusters: number; cases: number; matrix: number };
  bounds: { minX: number; maxX: number; minZ: number; maxZ: number };
  uncovered: number;
}

export const LEVEL_GAP = 14;
/** Distance between neighbouring requirement points on an island (phyllotaxis constant). */
const SPACING = 0.62;
const ISLAND_MARGIN = 0.9;
const ISLAND_GAP = 1.6;
const GOLDEN = Math.PI * (3 - Math.sqrt(5));

const collator = new Intl.Collator("tr", { numeric: true });

/** Small deterministic hash (FNV-1a) for stable jitter. */
function hash(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

export function islandRadius(count: number): number {
  return SPACING * Math.sqrt(Math.max(count, 1)) + ISLAND_MARGIN;
}

/** Islands in the cluster view's reading order (sorted by name), packed row by row on a
 *  near-square grid; each row is as tall as its largest island. Centered on the origin. */
function packIslands(sizes: number[]): { x: number; z: number; r: number }[] {
  const n = sizes.length;
  const cols = Math.max(1, Math.ceil(Math.sqrt(n)));
  const out: { x: number; z: number; r: number }[] = [];
  let z = 0;
  for (let start = 0; start < n; start += cols) {
    const row = sizes.slice(start, start + cols).map(islandRadius);
    const rowR = Math.max(...row);
    let x = 0;
    row.forEach((r, i) => {
      if (i > 0) x += row[i - 1]! + ISLAND_GAP + r;
      out.push({ x, z: z + rowR, r });
    });
    z += 2 * rowR + ISLAND_GAP;
  }
  // Center each row and the whole block on the origin.
  const totalZ = z - ISLAND_GAP;
  for (let start = 0; start < n; start += cols) {
    const rowEnd = Math.min(start + cols, n) - 1;
    const shift = -out[rowEnd]!.x / 2;
    for (let i = start; i <= rowEnd; i++) out[i]!.x += shift;
  }
  for (const p of out) p.z -= totalZ / 2;
  return out;
}

/** Reads only nodes and matrix warnings, so the caller can memoize on those two. */
export function buildLayout(state: Pick<ProjectState, "nodes" | "warnings">): LayerLayout {
  // The cluster selector reads only `nodes`.
  const list = clusters(state as ProjectState);
  const levels = { clusters: 0, cases: LEVEL_GAP, matrix: 2 * LEVEL_GAP };

  // Requirements and the cluster each belongs to; the rest form a trailing "no cluster" island.
  const allReqs = Object.values(state.nodes).filter((n) => n.ref.kind === "requirement");
  const clustered = new Set<string>();
  const groups: { key: string; name: string; members: { key: string; id: string }[] }[] = list.map((c) => ({
    key: c.key,
    name: c.name,
    members: c.members.map((m) => {
      clustered.add(m.node.ref.key);
      return { key: m.node.ref.key, id: m.id };
    }),
  }));
  const loose = allReqs
    .filter((n) => !clustered.has(n.ref.key))
    .map((n) => ({ key: n.ref.key, id: typeof n.content?.["id"] === "string" ? (n.content["id"] as string) : n.ref.key }))
    .sort((a, b) => collator.compare(a.id, b.id));
  if (loose.length) groups.push({ key: "", name: "Öbeksiz", members: loose });

  // Coverage by requirement id, from the test cases (the matrix is derived the same way).
  const caseNodes = Object.values(state.nodes)
    .filter((n) => n.ref.kind === "test_case")
    .sort((a, b) => collator.compare(a.ref.key, b.ref.key));
  const covered = new Set<string>();
  for (const n of caseNodes) for (const id of testCaseContent(n)?.covers ?? []) covered.add(id);

  const centers = packIslands(groups.map((g) => g.members.length));
  const islands: ClusterIsland[] = [];
  const reqs: ReqPoint[] = [];
  const reqById = new Map<string, ReqPoint>();
  groups.forEach((g, gi) => {
    const c = centers[gi]!;
    let unc = 0;
    g.members.forEach((m, i) => {
      const r = SPACING * Math.sqrt(i + 0.5);
      const a = i * GOLDEN;
      const p: ReqPoint = { key: m.key, id: m.id, x: c.x + r * Math.cos(a), z: c.z + r * Math.sin(a), covered: covered.has(m.id), cluster: g.key };
      if (!p.covered) unc++;
      reqs.push(p);
      reqById.set(m.id, p);
    });
    islands.push({ key: g.key, name: g.name, x: c.x, z: c.z, radius: c.r, count: g.members.length, uncovered: unc });
  });

  let minX = 0;
  let maxX = 0;
  let minZ = 0;
  let maxZ = 0;
  for (const i of islands) {
    minX = Math.min(minX, i.x - i.radius);
    maxX = Math.max(maxX, i.x + i.radius);
    minZ = Math.min(minZ, i.z - i.radius);
    maxZ = Math.max(maxZ, i.z + i.radius);
  }
  const islandByKey = new Map(islands.map((i) => [i.key, i]));

  // Test cases above the centroid of the requirements they cover, with a small stable offset so
  // cases of the same requirement do not sit on top of each other.
  const cases: CasePoint[] = [];
  const caseCovers: ReqPoint[][] = [];
  for (const n of caseNodes) {
    const c = testCaseContent(n);
    const cov = (c?.covers ?? []).map((id) => reqById.get(id)).filter((r): r is ReqPoint => r !== undefined);
    const cluster = n.ref.key.split(":")[0] ?? "";
    let x: number;
    let z: number;
    if (cov.length) {
      x = cov.reduce((s, r) => s + r.x, 0) / cov.length;
      z = cov.reduce((s, r) => s + r.z, 0) / cov.length;
    } else {
      const isl = islandByKey.get(cluster);
      x = isl?.x ?? 0;
      z = isl?.z ?? 0;
    }
    const h = hash(n.ref.key);
    const a = ((h & 0xffff) / 0x10000) * Math.PI * 2;
    const rr = 0.2 + ((h >>> 16) / 0x10000) * 0.5;
    cases.push({ key: n.ref.key, id: c?.id ?? n.ref.key, x: x + rr * Math.cos(a), z: z + rr * Math.sin(a), cluster });
    caseCovers.push(cov);
  }

  // Matrix rows in blocks above their cluster's island (the matrix view's cluster column), in id
  // order inside a block: up-threads stay short on screen, which keeps software rendering fast.
  const matrix: MatrixCell[] = [];
  const cellById = new Map<string, MatrixCell>();
  groups.forEach((g, gi) => {
    const isl = islands[gi]!;
    const rows = g.members.map((m) => reqById.get(m.id)!).sort((a, b) => collator.compare(a.id, b.id));
    const cols = Math.max(1, Math.ceil(Math.sqrt(rows.length)));
    const side = isl.radius * Math.SQRT2;
    const size = side / cols;
    const x0 = isl.x - side / 2;
    const z0 = isl.z - (Math.ceil(rows.length / cols) * size) / 2;
    rows.forEach((r, i) => {
      const cell: MatrixCell = {
        key: r.key,
        id: r.id,
        x: x0 + ((i % cols) + 0.5) * size,
        z: z0 + (Math.floor(i / cols) + 0.5) * size,
        size,
        covered: r.covered,
        warning: !!state.warnings[r.id],
      };
      matrix.push(cell);
      cellById.set(r.id, cell);
    });
  });

  // Exact threads: requirement → covering case, case → that requirement's matrix row. Grouped by
  // the requirement's island so the view can draw the threads of a few islands only.
  const islandIndex = new Map(islands.map((isl, i) => [isl.key, i]));
  const pairs: { r: ReqPoint; tc: CasePoint }[][] = islands.map(() => []);
  cases.forEach((tc, i) => {
    for (const r of caseCovers[i]!) pairs[islandIndex.get(r.cluster)!]!.push({ r, tc });
  });
  const threads = new Float32Array(pairs.reduce((n, p) => n + p.length, 0) * 12);
  const threadStarts: number[] = [];
  let o = 0;
  const put = (arr: Float32Array, x: number, y: number, z: number) => {
    arr[o++] = x;
    arr[o++] = y;
    arr[o++] = z;
  };
  for (const list of pairs) {
    threadStarts.push(o / 6);
    for (const { r, tc } of list) {
      const cell = cellById.get(r.id)!;
      put(threads, r.x, levels.clusters, r.z);
      put(threads, tc.x, levels.cases, tc.z);
      put(threads, tc.x, levels.cases, tc.z);
      put(threads, cell.x, levels.matrix, cell.z);
    }
  }
  threadStarts.push(o / 6);

  // Bundled threads for the far view: every covered requirement sends one thread to its island's
  // test case hub (centroid of the island's cases), the hub one thread to the island's matrix
  // block. An uncovered requirement has no thread in either form.
  const hubs = islands.map(() => ({ x: 0, z: 0, n: 0 }));
  for (const c of cases) {
    const i = islandIndex.get(c.cluster);
    if (i === undefined) continue;
    const h = hubs[i]!;
    h.x += c.x;
    h.z += c.z;
    h.n++;
  }
  const coveredBy = islands.map((isl) => reqs.filter((r) => r.cluster === isl.key && r.covered));
  const bundles = new Float32Array(coveredBy.reduce((n, l) => n + (l.length ? l.length + 1 : 0), 0) * 6);
  const bundleStarts: number[] = [];
  o = 0;
  islands.forEach((isl, i) => {
    bundleStarts.push(o / 6);
    const list = coveredBy[i]!;
    if (!list.length) return;
    const h = hubs[i]!;
    const hx = h.n ? h.x / h.n : isl.x;
    const hz = h.n ? h.z / h.n : isl.z;
    for (const r of list) {
      put(bundles, r.x, levels.clusters, r.z);
      put(bundles, hx, levels.cases, hz);
    }
    put(bundles, hx, levels.cases, hz);
    put(bundles, isl.x, levels.matrix, isl.z);
  });
  bundleStarts.push(o / 6);

  return {
    islands,
    reqs,
    cases,
    matrix,
    threads,
    threadStarts,
    bundles,
    bundleStarts,
    levels,
    bounds: { minX, maxX, minZ, maxZ },
    uncovered: reqs.filter((r) => !r.covered).length,
  };
}
