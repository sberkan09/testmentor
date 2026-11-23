import {
  BoxGeometry,
  BufferAttribute,
  BufferGeometry,
  CircleGeometry,
  Color,
  DoubleSide,
  Group,
  InstancedMesh,
  LineBasicMaterial,
  LineSegments,
  Matrix4,
  MeshBasicMaterial,
  OctahedronGeometry,
  PlaneGeometry,
  Quaternion,
  RingGeometry,
  Vector3,
  type Material,
} from "three";
import type { LayerKind, LayerLayout } from "./layout";

/** three.js objects of the layer view, built once per layout: one draw call per kind
 *  (InstancedMesh for points, LineSegments for threads), unlit materials, no transparency
 *  except the thin threads. Software rendering (SwiftShader) is the target to stay fast on. */

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

export interface LayerObjects {
  group: Group;
  islands: InstancedMesh;
  reqs: InstancedMesh;
  cases: InstancedMesh;
  matrix: InstancedMesh;
  /** Instanced meshes a ray can select, with the item kind each one draws. */
  pickable: { mesh: InstancedMesh; kind: LayerKind }[];
  dispose(): void;
}

const FLAT = new Quaternion().setFromAxisAngle(new Vector3(1, 0, 0), -Math.PI / 2);
const NO_ROT = new Quaternion();

function instanced(
  geometry: BufferGeometry,
  count: number,
  place: (i: number, pos: Vector3, scale: Vector3) => string,
  rotation: Quaternion = NO_ROT,
): InstancedMesh {
  const material = new MeshBasicMaterial({ color: 0xffffff, toneMapped: false });
  const mesh = new InstancedMesh(geometry, material, Math.max(count, 1));
  mesh.count = count;
  const m = new Matrix4();
  const pos = new Vector3();
  const scale = new Vector3();
  const color = new Color();
  const cache = new Map<string, Color>();
  for (let i = 0; i < count; i++) {
    scale.set(1, 1, 1);
    const hex = place(i, pos, scale);
    let c = cache.get(hex);
    if (!c) {
      c = color.clone().set(hex);
      cache.set(hex, c);
    }
    m.compose(pos, rotation, scale);
    mesh.setMatrixAt(i, m);
    mesh.setColorAt(i, c);
  }
  mesh.instanceMatrix.needsUpdate = true;
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  // Needed for frustum culling and for the ray test to see every instance.
  mesh.computeBoundingSphere();
  return mesh;
}

export function buildObjects(layout: LayerLayout): LayerObjects {
  const { levels, bounds } = layout;
  const group = new Group();

  const islands = instanced(
    new CircleGeometry(1, 40),
    layout.islands.length,
    (i, pos, scale) => {
      const isl = layout.islands[i]!;
      pos.set(isl.x, levels.clusters - 0.05, isl.z);
      scale.setScalar(isl.radius);
      return COLORS.island;
    },
    FLAT,
  );

  const reqs = instanced(new OctahedronGeometry(0.2, 0), layout.reqs.length, (i, pos, scale) => {
    const r = layout.reqs[i]!;
    pos.set(r.x, levels.clusters + 0.15, r.z);
    if (!r.covered) scale.setScalar(1.6);
    return r.covered ? COLORS.requirement : COLORS.uncovered;
  });

  // Uncovered requirements: a ring around the point, visible from afar.
  const uncovered = layout.reqs.filter((r) => !r.covered);
  const rings = instanced(
    new RingGeometry(0.42, 0.56, 20),
    uncovered.length,
    (i, pos) => {
      const r = uncovered[i]!;
      pos.set(r.x, levels.clusters + 0.01, r.z);
      return COLORS.uncovered;
    },
    FLAT,
  );

  const cases = instanced(new BoxGeometry(0.2, 0.2, 0.2), layout.cases.length, (i, pos) => {
    const c = layout.cases[i]!;
    pos.set(c.x, levels.cases, c.z);
    return COLORS.testCase;
  });

  const cell = layout.matrixCell * 0.82;
  const matrix = instanced(
    new PlaneGeometry(1, 1),
    layout.matrix.length,
    (i, pos, scale) => {
      const m = layout.matrix[i]!;
      pos.set(m.x, levels.matrix, m.z);
      scale.set(cell, cell, 1);
      return m.warning ? COLORS.matrixWarning : m.covered ? COLORS.matrixCovered : COLORS.matrixUncovered;
    },
    FLAT,
  );
  // The matrix plane is seen from below as well.
  (matrix.material as MeshBasicMaterial).side = DoubleSide;

  const threadGeometry = new BufferGeometry();
  threadGeometry.setAttribute("position", new BufferAttribute(layout.threads, 3));
  threadGeometry.computeBoundingSphere();
  const threads = new LineSegments(
    threadGeometry,
    new LineBasicMaterial({ color: COLORS.thread, transparent: true, opacity: 0.16, depthWrite: false, toneMapped: false }),
  );
  threads.renderOrder = 1;

  // Plane outlines (rectangles), no filled translucent planes: full-screen blending is the
  // expensive part of software rendering.
  const pad = 2;
  const x0 = bounds.minX - pad;
  const x1 = bounds.maxX + pad;
  const z0 = bounds.minZ - pad;
  const z1 = bounds.maxZ + pad;
  const outline: number[] = [];
  for (const y of [levels.clusters, levels.cases, levels.matrix]) {
    const c = [
      [x0, z0],
      [x1, z0],
      [x1, z1],
      [x0, z1],
    ];
    for (let k = 0; k < 4; k++) {
      const a = c[k]!;
      const b = c[(k + 1) % 4]!;
      outline.push(a[0]!, y, a[1]!, b[0]!, y, b[1]!);
    }
  }
  const outlineGeometry = new BufferGeometry();
  outlineGeometry.setAttribute("position", new BufferAttribute(new Float32Array(outline), 3));
  const outlines = new LineSegments(outlineGeometry, new LineBasicMaterial({ color: COLORS.outline, toneMapped: false }));

  group.add(islands, rings, reqs, cases, matrix, outlines, threads);

  return {
    group,
    islands,
    reqs,
    cases,
    matrix,
    pickable: [
      { mesh: reqs, kind: "requirement" },
      { mesh: cases, kind: "test_case" },
      { mesh: matrix, kind: "matrix" },
    ],
    dispose() {
      group.traverse((o) => {
        const obj = o as { geometry?: BufferGeometry; material?: Material | Material[] };
        obj.geometry?.dispose();
        if (Array.isArray(obj.material)) obj.material.forEach((m) => m.dispose());
        else obj.material?.dispose();
      });
      for (const m of [islands, rings, reqs, cases, matrix]) m.dispose();
    },
  };
}
