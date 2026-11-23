import {
  BufferAttribute,
  BufferGeometry,
  CircleGeometry,
  Color,
  DoubleSide,
  Group,
  LineBasicMaterial,
  LineSegments,
  Mesh,
  MeshBasicMaterial,
  Points,
  ShaderMaterial,
  type Material,
} from "three";
import type { LayerLayout } from "./layout";

/** three.js objects of the layer view, built once per layout. Target: software rendering
 *  (SwiftShader) stays fast. Measured there (paket 9 planı): instanced drawing costs about
 *  20 µs per instance and long lines cost per pixel, so
 *  - requirement and test case points are `Points` (one vertex each, round or square sprite),
 *  - uncovered requirements get a second, larger ring-shaped sprite on top (no extra mesh),
 *  - islands and matrix cells are merged static meshes (one draw call, no instancing),
 *  - threads are `LineSegments` in two forms: bundled per island (far view) or exact for the
 *    islands nearest the camera target within a segment budget (near view),
 *  - colors are given and written in sRGB as is (no per-fragment color space conversion). */

export const COLORS = {
  background: "#f4f5f9",
  island: "#e1e4ef",
  requirement: "#4f46e5",
  uncovered: "#c2410c",
  testCase: "#0d9488",
  matrixCovered: "#16a34a",
  matrixUncovered: "#c2410c",
  matrixWarning: "#b7791f",
  thread: "#6366f1",
  outline: "#b4bbd0",
} as const;

/** World sizes of the point sprites. */
export const POINT_SIZE = { requirement: 0.36, uncovered: 1.0, testCase: 0.3 } as const;
export const ISLAND_SEGMENTS = 40;

export interface LayerObjects {
  group: Group;
  islands: Mesh;
  reqs: Points;
  cases: Points;
  matrix: Mesh;
  exactThreads: LineSegments;
  bundledThreads: LineSegments;
  /** Exact threads of the given islands only (near view), or bundled threads of every island
   *  (null, far view). Returns the segment counts drawn. */
  setFocus(islands: ReadonlySet<number> | null): { exact: number; bundled: number };
  /** Viewport height in pixels over 2·tan(fov/2): converts world sizes to point sizes. */
  setPointScale(scale: number): void;
  dispose(): void;
}

const VERTEX = /* glsl */ `
attribute vec3 aColor;
attribute float aSize;
uniform float uScale;
varying vec3 vColor;
void main() {
  vColor = aColor;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_PointSize = max(aSize * uScale / -mv.z, 2.0);
  gl_Position = projectionMatrix * mv;
}`;

const FRAGMENT = /* glsl */ `
uniform float uShape;
varying vec3 vColor;
void main() {
  // 0: square, 1: disc, 2: ring around a dot (uncovered requirement).
  if (uShape > 0.5) {
    vec2 c = gl_PointCoord - 0.5;
    float d = dot(c, c);
    if (d > 0.25) discard;
    if (uShape > 1.5 && d > 0.07 && d < 0.13) discard;
  }
  gl_FragColor = vec4(vColor, 1.0);
}`;

type Shape = "square" | "disc" | "ring";
const SHAPE: Record<Shape, number> = { square: 0, disc: 1, ring: 2 };

function points(items: { x: number; y: number; z: number; color: string; size: number }[], shape: Shape): Points {
  const pos = new Float32Array(items.length * 3);
  const col = new Float32Array(items.length * 3);
  const size = new Float32Array(items.length);
  const c = new Color();
  items.forEach((it, i) => {
    pos.set([it.x, it.y, it.z], i * 3);
    c.set(it.color);
    col.set([c.r, c.g, c.b], i * 3);
    size[i] = it.size;
  });
  const g = new BufferGeometry();
  g.setAttribute("position", new BufferAttribute(pos, 3));
  g.setAttribute("aColor", new BufferAttribute(col, 3));
  g.setAttribute("aSize", new BufferAttribute(size, 1));
  g.computeBoundingSphere();
  const m = new ShaderMaterial({ vertexShader: VERTEX, fragmentShader: FRAGMENT, uniforms: { uScale: { value: 800 }, uShape: { value: SHAPE[shape] } } });
  return new Points(g, m);
}

/** Copies of a flat base shape (in the xz plane), translated, scaled and colored, as one mesh. */
function merged(base: BufferGeometry, items: { x: number; y: number; z: number; s: number; color: string }[], side = DoubleSide): Mesh {
  const flat = (base.index ? base.toNonIndexed() : base).getAttribute("position") as BufferAttribute;
  const n = flat.count;
  const pos = new Float32Array(items.length * n * 3);
  const col = new Float32Array(items.length * n * 3);
  const c = new Color();
  items.forEach((it, i) => {
    c.set(it.color);
    for (let k = 0; k < n; k++) {
      const o = (i * n + k) * 3;
      // Base shapes are built in the xy plane; lay them flat (y up): (x, y) → (x, -y) on xz.
      pos[o] = it.x + flat.getX(k) * it.s;
      pos[o + 1] = it.y;
      pos[o + 2] = it.z - flat.getY(k) * it.s;
      col[o] = c.r;
      col[o + 1] = c.g;
      col[o + 2] = c.b;
    }
  });
  base.dispose();
  const g = new BufferGeometry();
  g.setAttribute("position", new BufferAttribute(pos, 3));
  g.setAttribute("color", new BufferAttribute(col, 3));
  g.computeBoundingSphere();
  return new Mesh(g, new MeshBasicMaterial({ vertexColors: true, side, toneMapped: false }));
}

function lines(arr: Float32Array, color: string, opacity: number, indexed = false): LineSegments {
  const g = new BufferGeometry();
  g.setAttribute("position", new BufferAttribute(arr, 3));
  if (indexed) g.setIndex(new BufferAttribute(new Uint32Array(arr.length / 3), 1));
  g.computeBoundingSphere();
  const m = new LineBasicMaterial({ color, transparent: opacity < 1, opacity, depthWrite: opacity >= 1, toneMapped: false });
  const l = new LineSegments(g, m);
  l.renderOrder = 1;
  return l;
}

export function buildObjects(layout: LayerLayout): LayerObjects {
  const { levels, bounds } = layout;
  const group = new Group();

  const islands = merged(
    new CircleGeometry(1, ISLAND_SEGMENTS),
    layout.islands.map((i) => ({ x: i.x, y: levels.clusters - 0.05, z: i.z, s: i.radius, color: COLORS.island })),
  );

  const reqs = points(
    layout.reqs.map((r) => ({
      x: r.x,
      y: levels.clusters + 0.15,
      z: r.z,
      color: r.covered ? COLORS.requirement : COLORS.uncovered,
      size: POINT_SIZE.requirement,
    })),
    "disc",
  );

  // Uncovered requirements: a larger ring sprite over the point, visible from afar.
  const rings = points(
    layout.reqs.filter((r) => !r.covered).map((r) => ({ x: r.x, y: levels.clusters + 0.2, z: r.z, color: COLORS.uncovered, size: POINT_SIZE.uncovered })),
    "ring",
  );

  const cases = points(
    layout.cases.map((c) => ({ x: c.x, y: levels.cases, z: c.z, color: COLORS.testCase, size: POINT_SIZE.testCase })),
    "square",
  );

  // Matrix cells: unit squares (two triangles each) scaled to the cell.
  const square = new BufferGeometry();
  square.setAttribute("position", new BufferAttribute(new Float32Array([-0.5, -0.5, 0, 0.5, -0.5, 0, 0.5, 0.5, 0, -0.5, -0.5, 0, 0.5, 0.5, 0, -0.5, 0.5, 0]), 3));
  const matrix = merged(
    square,
    layout.matrix.map((m) => ({
      x: m.x,
      y: levels.matrix,
      z: m.z,
      s: m.size * 0.62,
      color: m.warning ? COLORS.matrixWarning : m.covered ? COLORS.matrixCovered : COLORS.matrixUncovered,
    })),
  );

  const exactThreads = lines(layout.threads, COLORS.thread, 0.16, true);
  const bundledThreads = lines(layout.bundles, COLORS.thread, 0.2, true);
  /** Writes the segments of the chosen islands into the index buffer of a thread object. */
  const fill = (obj: LineSegments, starts: number[], take: (island: number) => boolean): number => {
    const index = obj.geometry.getIndex()!;
    const out = index.array as Uint32Array;
    let n = 0;
    for (let i = 0; i + 1 < starts.length; i++) {
      if (!take(i)) continue;
      for (let v = starts[i]! * 2; v < starts[i + 1]! * 2; v++) out[n++] = v;
    }
    index.needsUpdate = true;
    obj.geometry.setDrawRange(0, n);
    obj.visible = n > 0;
    return n / 2;
  };
  const setFocus = (focus: ReadonlySet<number> | null) => ({
    exact: fill(exactThreads, layout.threadStarts, (i) => !!focus?.has(i)),
    bundled: fill(bundledThreads, layout.bundleStarts, () => !focus),
  });
  setFocus(null);

  // Plane outlines (rectangles), no filled translucent planes.
  const pad = 2;
  const x0 = bounds.minX - pad;
  const x1 = bounds.maxX + pad;
  const z0 = bounds.minZ - pad;
  const z1 = bounds.maxZ + pad;
  const outline: number[] = [];
  for (const y of [levels.clusters, levels.cases, levels.matrix]) {
    outline.push(x0, y, z0, x1, y, z0, x1, y, z0, x1, y, z1, x1, y, z1, x0, y, z1, x0, y, z1, x0, y, z0);
  }
  const outlines = lines(new Float32Array(outline), COLORS.outline, 1);

  group.add(islands, rings, reqs, cases, matrix, outlines, bundledThreads, exactThreads);

  return {
    group,
    islands,
    reqs,
    cases,
    matrix,
    exactThreads,
    bundledThreads,
    setFocus,
    setPointScale(scale) {
      for (const p of [reqs, rings, cases]) (p.material as ShaderMaterial).uniforms["uScale"]!.value = scale;
    },
    dispose() {
      group.traverse((o) => {
        const obj = o as { geometry?: BufferGeometry; material?: Material | Material[] };
        obj.geometry?.dispose();
        if (Array.isArray(obj.material)) obj.material.forEach((m) => m.dispose());
        else obj.material?.dispose();
      });
    },
  };
}
