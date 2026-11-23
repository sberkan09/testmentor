import { useEffect, useMemo, useRef, type MutableRefObject, type RefObject } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { Raycaster, Vector2, Vector3, type Intersection, type PerspectiveCamera } from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { LayerKind, LayerLayout } from "./layout";
import { ISLAND_SEGMENTS, POINT_SIZE, buildObjects } from "./objects";
import { EXACT_SEGMENT_BUDGET, EXACT_THREADS_BELOW, type ThreadTier } from "./tiers";

export interface LayerPick {
  kind: LayerKind;
  /** Node key: requirement key for "requirement" and "matrix", cluster key, test case key. */
  key: string;
  id: string;
  /** Cluster key the item belongs to ("" when none). */
  cluster: string;
}

export interface SceneHandle {
  reset(): void;
}

/** Test hook for the e2e performance test (`layers-perf.spec.ts`). Reading it costs nothing;
 *  `frames` is a ring of timestamps of rendered frames (the scene renders on demand). */
export interface LayersTestHook {
  ready: boolean;
  frames: number[];
  counts: { requirements: number; testCases: number; matrix: number; threads: number; bundled: number; uncovered: number };
  renderer: string;
  /** Thread tier of the last rendered frame and the segments it drew in each form. */
  view(): { tier: ThreadTier; exactSegments: number; bundledSegments: number; focusIslands: number; distanceRatio: number };
  /** Moves the camera to `ratio` × the framing distance, keeping the direction. */
  setDistanceRatio(ratio: number): void;
  screenPoint(kind: LayerKind, key: string): { x: number; y: number } | null;
  pickAt(x: number, y: number): LayerPick | null;
}

declare global {
  interface Window {
    __testmentorLayers?: LayersTestHook;
  }
}

const FRAME_RING = 4000;
const LABEL_POOL = 60;
const DIVE_MS = 550;
const CLICK_SLOP = 5;
const PICK_RADIUS_PX = 8;

interface Dive {
  t0: number;
  from: Vector3;
  fromTarget: Vector3;
  to: Vector3;
  toTarget: Vector3;
  pick: LayerPick;
}

interface Labeled {
  x: number;
  y: number;
  z: number;
  text: string;
  cls: string;
  /** Squared distance to the camera: nearer labels win the pool. */
  d: number;
}

export function LayerScene({
  layout,
  labelsRef,
  handleRef,
  onPick,
}: {
  layout: LayerLayout;
  labelsRef: RefObject<HTMLDivElement | null>;
  handleRef: MutableRefObject<SceneHandle | null>;
  onPick: (p: LayerPick) => void;
}) {
  const { camera, gl, invalidate } = useThree();
  const objects = useMemo(() => buildObjects(layout), [layout]);
  useEffect(() => () => objects.dispose(), [objects]);

  const controls = useMemo(() => new OrbitControls(camera, gl.domElement), [camera, gl]);
  const dive = useRef<Dive | null>(null);
  const onPickRef = useRef(onPick);
  useEffect(() => {
    onPickRef.current = onPick;
  }, [onPick]);

  // Camera distance that frames the whole stack; labels depend on the ratio to it.
  const fit = useMemo(() => {
    const { bounds, levels } = layout;
    const w = bounds.maxX - bounds.minX;
    const d = bounds.maxZ - bounds.minZ;
    const radius = Math.hypot(w, d, levels.matrix) / 2 + 2;
    const fov = ((camera as { fov?: number }).fov ?? 45) * (Math.PI / 180);
    // The stack is flat: its bounding sphere is a loose fit, so come in closer than that.
    const dist = (radius / Math.sin(fov / 2)) * 0.72;
    const target = new Vector3(0, levels.cases, 0);
    const dir = new Vector3(0, 0.62, 1).normalize();
    return { dist, target, position: target.clone().addScaledVector(dir, dist) };
  }, [layout, camera]);

  // Clip planes and zoom limits follow the layout; the camera itself is placed only on the first
  // mount and on "reset", so a layout rebuild after a server event does not move the view.
  useEffect(() => {
    camera.near = Math.max(fit.dist / 500, 0.05);
    camera.far = fit.dist * 6;
    camera.updateProjectionMatrix();
    controls.maxDistance = fit.dist * 2.5;
    controls.minDistance = 2;
    invalidate();
  }, [camera, controls, fit, invalidate]);

  const reset = useMemo(
    () => () => {
      dive.current = null;
      controls.enabled = true;
      camera.position.copy(fit.position);
      controls.target.copy(fit.target);
      controls.update();
      invalidate();
    },
    [camera, controls, fit, invalidate],
  );

  useEffect(() => {
    controls.enableDamping = true;
    controls.dampingFactor = 0.12;
    controls.zoomSpeed = 1.2;
    const onChange = () => invalidate();
    controls.addEventListener("change", onChange);
    return () => {
      controls.removeEventListener("change", onChange);
      controls.dispose();
    };
  }, [controls, invalidate]);

  const placed = useRef<OrbitControls | null>(null);
  useEffect(() => {
    handleRef.current = { reset };
    if (placed.current !== controls) {
      placed.current = controls;
      reset();
    }
  }, [reset, handleRef, controls]);

  // Picking: a ray against the points and matrix cells first, then the nearest point on screen within a
  // few pixels (points are small from afar), then the island under the cursor.
  const picker = useMemo(() => {
    const ray = new Raycaster();
    const ndc = new Vector2();
    const v = new Vector3();
    const levelOf: Record<LayerKind, number> = {
      cluster: layout.levels.clusters,
      requirement: layout.levels.clusters + 0.15,
      test_case: layout.levels.cases,
      matrix: layout.levels.matrix,
    };
    const itemOf = (kind: LayerKind, i: number): (LayerPick & { x: number; z: number }) | null => {
      if (kind === "requirement") {
        const r = layout.reqs[i];
        return r ? { kind, key: r.key, id: r.id, cluster: r.cluster, x: r.x, z: r.z } : null;
      }
      if (kind === "test_case") {
        const c = layout.cases[i];
        return c ? { kind, key: c.key, id: c.id, cluster: c.cluster, x: c.x, z: c.z } : null;
      }
      if (kind === "matrix") {
        const m = layout.matrix[i];
        const r = m ? layout.reqs.find((q) => q.key === m.key) : undefined;
        return m ? { kind, key: m.key, id: m.id, cluster: r?.cluster ?? "", x: m.x, z: m.z } : null;
      }
      const isl = layout.islands[i];
      return isl ? { kind, key: isl.key, id: isl.key, cluster: isl.key, x: isl.x, z: isl.z } : null;
    };
    const toScreen = (x: number, y: number, z: number, rect: DOMRect = gl.domElement.getBoundingClientRect()): { x: number; y: number } | null => {
      v.set(x, y, z).project(camera);
      if (v.z < -1 || v.z > 1) return null;
      return { x: rect.left + ((v.x + 1) / 2) * rect.width, y: rect.top + ((1 - v.y) / 2) * rect.height };
    };
    const lists: { kind: LayerKind; items: { x: number; z: number }[] }[] = [
      { kind: "requirement", items: layout.reqs },
      { kind: "test_case", items: layout.cases },
      { kind: "matrix", items: layout.matrix },
    ];
    const pickAt = (clientX: number, clientY: number): (LayerPick & { x: number; z: number }) | null => {
      const rect = gl.domElement.getBoundingClientRect();
      ndc.set(((clientX - rect.left) / rect.width) * 2 - 1, -((clientY - rect.top) / rect.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      ray.params.Points = { threshold: POINT_SIZE.requirement };
      const hits: (Intersection & { kind: LayerKind })[] = [];
      for (const [obj, kind] of [
        [objects.reqs, "requirement"],
        [objects.cases, "test_case"],
        [objects.matrix, "matrix"],
      ] as const) {
        for (const h of ray.intersectObject(obj, false)) hits.push({ ...h, kind });
      }
      hits.sort((a, b) => a.distance - b.distance);
      const hit = hits[0];
      if (hit) {
        // Points report the vertex index, the merged matrix mesh the triangle (two per cell).
        const i = hit.kind === "matrix" ? Math.floor((hit.faceIndex ?? 0) / 2) : (hit.index ?? -1);
        const item = itemOf(hit.kind, i);
        if (item) return item;
      }
      let best: { kind: LayerKind; i: number; d: number } | null = null;
      for (const { kind, items } of lists) {
        const y = levelOf[kind];
        items.forEach((it, i) => {
          const s = toScreen(it.x, y, it.z, rect);
          if (!s) return;
          const d = Math.hypot(s.x - clientX, s.y - clientY);
          if (d <= PICK_RADIUS_PX && (!best || d < best.d)) best = { kind, i, d };
        });
      }
      const found = best as { kind: LayerKind; i: number } | null;
      if (found) return itemOf(found.kind, found.i);
      const isl = ray.intersectObject(objects.islands, false)[0];
      return isl ? itemOf("cluster", Math.floor((isl.faceIndex ?? 0) / ISLAND_SEGMENTS)) : null;
    };
    const screenPoint = (kind: LayerKind, key: string) => {
      const list = kind === "requirement" ? layout.reqs : kind === "test_case" ? layout.cases : kind === "matrix" ? layout.matrix : layout.islands;
      const it = (list as { key: string; x: number; z: number }[]).find((x) => x.key === key);
      return it ? toScreen(it.x, levelOf[kind], it.z) : null;
    };
    return { pickAt, screenPoint, levelOf };
  }, [layout, objects, camera, gl]);

  // Click (not drag) selects: the camera dives to the item, then the 2D view opens.
  useEffect(() => {
    const el = gl.domElement;
    // A press is a click only if the pointer never left the slop radius: a drag that comes back
    // to its start point is still a drag.
    let down: { x: number; y: number; dragged: boolean } | null = null;
    const onDown = (e: PointerEvent) => {
      down = e.button === 0 ? { x: e.clientX, y: e.clientY, dragged: false } : null;
    };
    const onMove = (e: PointerEvent) => {
      if (down && !down.dragged && Math.hypot(e.clientX - down.x, e.clientY - down.y) > CLICK_SLOP) down.dragged = true;
    };
    const onUp = (e: PointerEvent) => {
      if (!down || dive.current) return;
      const dragged = down.dragged || Math.hypot(e.clientX - down.x, e.clientY - down.y) > CLICK_SLOP;
      down = null;
      if (dragged) return;
      const hit = picker.pickAt(e.clientX, e.clientY);
      if (!hit) return;
      const y = picker.levelOf[hit.kind];
      const toTarget = new Vector3(hit.x, y, hit.z);
      dive.current = {
        t0: performance.now(),
        from: camera.position.clone(),
        fromTarget: controls.target.clone(),
        toTarget,
        to: toTarget.clone().add(new Vector3(0, 9, 0.6)),
        pick: { kind: hit.kind, key: hit.key, id: hit.id, cluster: hit.cluster },
      };
      controls.enabled = false;
      invalidate();
    };
    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerup", onUp);
    return () => {
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerup", onUp);
    };
  }, [gl, picker, camera, controls, invalidate]);

  // HTML label overlay: a fixed pool of spans moved imperatively, only on rendered frames.
  const labels = useRef<{ levelSpans: HTMLSpanElement[]; pool: HTMLSpanElement[]; shown: number } | null>(null);
  useEffect(() => {
    const host = labelsRef.current;
    if (!host) return;
    const span = (cls: string, text = "") => {
      const s = document.createElement("span");
      s.className = cls;
      s.textContent = text;
      s.style.display = "none";
      host.appendChild(s);
      return s;
    };
    const levelSpans = ["Öbekler", "Test durumları", "Matris"].map((t) => span("layer-label level", t));
    const pool = Array.from({ length: LABEL_POOL }, () => span("layer-label"));
    labels.current = { levelSpans, pool, shown: 0 };
    invalidate();
    return () => {
      labels.current = null;
      host.replaceChildren();
    };
  }, [labelsRef, invalidate]);

  const scratch = useMemo(() => new Vector3(), []);
  const lastRatio = useRef(1);
  const focus = useRef({ tier: "bundled" as ThreadTier, x: 0, z: 0, islands: 0, exact: 0, bundled: 0, ratio: 1, stale: true });
  useEffect(() => {
    // New objects (layout changed): recompute the focus on the next frame.
    focus.current = { ...focus.current, stale: true };
  }, [objects]);
  useFrame(({ size }) => {
    const now = performance.now();
    const hook = window.__testmentorLayers;
    if (hook) {
      hook.frames.push(now);
      if (hook.frames.length > FRAME_RING) hook.frames.splice(0, hook.frames.length - FRAME_RING);
    }

    const dv = dive.current;
    if (dv) {
      const t = Math.min((now - dv.t0) / DIVE_MS, 1);
      const e = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
      camera.position.lerpVectors(dv.from, dv.to, e);
      controls.target.lerpVectors(dv.fromTarget, dv.toTarget, e);
      camera.lookAt(controls.target);
      if (t >= 1) {
        dive.current = null;
        controls.enabled = true;
        onPickRef.current(dv.pick);
      } else invalidate();
    } else {
      controls.update();
    }

    // Thread tier by camera distance; the focus follows the target in steps (an island set change
    // rewrites the index buffers, so it is not done on every frame).
    const ratio = camera.position.distanceTo(controls.target) / fit.dist;
    lastRatio.current = ratio;
    const t = controls.target;
    const exact = ratio < EXACT_THREADS_BELOW;
    const f = focus.current;
    const moved = exact && (Math.hypot(t.x - f.x, t.z - f.z) > 1.5 || Math.abs(ratio - f.ratio) > 0.05);
    if (f.stale || exact !== (f.tier === "exact") || moved) {
      const chosen = new Set<number>();
      if (exact) {
        const order = layout.islands.map((isl, i) => ({ i, d: Math.hypot(isl.x - t.x, isl.z - t.z) })).sort((a, b) => a.d - b.d);
        // Closer means longer threads on screen: the budget shrinks with the distance.
        const budget = EXACT_SEGMENT_BUDGET * Math.min(1, Math.max(0.5, ratio / EXACT_THREADS_BELOW));
        let used = 0;
        for (const { i } of order) {
          const n = layout.threadStarts[i + 1]! - layout.threadStarts[i]!;
          if (used + n > budget && chosen.size > 0) break;
          chosen.add(i);
          used += n;
        }
      }
      const counts = objects.setFocus(exact ? chosen : null);
      focus.current = { tier: exact ? "exact" : "bundled", x: t.x, z: t.z, islands: chosen.size, ratio, stale: false, ...counts };
    }
    const fov = (camera as PerspectiveCamera).fov * (Math.PI / 180);
    objects.setPointScale(size.height / (2 * Math.tan(fov / 2)));

    const lab = labels.current;
    if (!lab) return;
    // Overlay coordinates are canvas pixels: no layout reads inside the frame.
    const w = size.width;
    const h = size.height;
    const local = (x: number, y: number, z: number): { x: number; y: number } | null => {
      scratch.set(x, y, z).project(camera);
      if (scratch.z < -1 || scratch.z > 1) return null;
      const px = ((scratch.x + 1) / 2) * w;
      const py = ((1 - scratch.y) / 2) * h;
      return px < 0 || py < 0 || px > w || py > h ? null : { x: px, y: py };
    };
    const { bounds, levels } = layout;
    const levelYs = [levels.clusters, levels.cases, levels.matrix];
    lab.levelSpans.forEach((s, i) => place(s, local(bounds.minX - 2, levelYs[i]!, bounds.maxZ + 2)));

    // Text only when zoomed in: cluster names at mid range, item ids up close.
    const dist = camera.position.distanceTo(controls.target);
    const items: Labeled[] = [];
    const cam = camera.position;
    const push = (x: number, y: number, z: number, text: string, cls: string) =>
      items.push({ x, y, z, text, cls, d: (x - cam.x) ** 2 + (y - cam.y) ** 2 + (z - cam.z) ** 2 });
    if (dist < fit.dist * 0.6) {
      for (const isl of layout.islands) {
        const extra = isl.uncovered ? ` · ${isl.uncovered} kapsanmamış` : "";
        push(isl.x, levels.clusters, isl.z - isl.radius, `${isl.name} · ${isl.count}${extra}`, "cluster");
      }
    }
    if (dist < fit.dist * 0.2) {
      const near2 = (dist * 0.9) ** 2;
      const t = controls.target;
      const add = (x: number, y: number, z: number, text: string, cls: string) => {
        if ((x - t.x) ** 2 + (y - t.y) ** 2 + (z - t.z) ** 2 < near2) push(x, y, z, text, cls);
      };
      const ry = picker.levelOf.requirement;
      for (const r of layout.reqs) add(r.x, ry, r.z, r.id, r.covered ? "req" : "req uncovered");
      for (const c of layout.cases) add(c.x, levels.cases, c.z, c.id, "case");
      for (const m of layout.matrix) add(m.x, levels.matrix, m.z, m.id, m.covered ? "row" : "row uncovered");
    }
    items.sort((a, b) => a.d - b.d);
    let n = 0;
    // Nearer labels first; a label that would overlap one already placed is skipped. The box is
    // estimated from the text length (no layout reads in the frame loop).
    const boxes: { x0: number; x1: number; y0: number; y1: number }[] = [];
    for (const it of items) {
      if (n >= LABEL_POOL) break;
      const p = local(it.x, it.y, it.z);
      if (!p) continue;
      const half = it.text.length * 3.3 + 6;
      const box = { x0: p.x - half, x1: p.x + half, y0: p.y - 22, y1: p.y - 4 };
      if (boxes.some((b) => b.x0 < box.x1 && box.x0 < b.x1 && b.y0 < box.y1 && box.y0 < b.y1)) continue;
      boxes.push(box);
      const s = lab.pool[n]!;
      if (s.textContent !== it.text) s.textContent = it.text;
      const cls = `layer-label ${it.cls}`;
      if (s.className !== cls) s.className = cls;
      place(s, p);
      n++;
    }
    for (let i = n; i < lab.shown; i++) lab.pool[i]!.style.display = "none";
    lab.shown = n;
  });

  // Test hook: counts, renderer, projection and picking for the e2e test.
  useEffect(() => {
    const ctx = gl.getContext();
    const ext = ctx.getExtension("WEBGL_debug_renderer_info");
    const renderer = ext ? String(ctx.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : String(ctx.getParameter(ctx.RENDERER));
    const prev = window.__testmentorLayers;
    window.__testmentorLayers = {
      ready: true,
      frames: prev?.frames ?? [],
      renderer,
      counts: {
        requirements: layout.reqs.length,
        testCases: layout.cases.length,
        matrix: layout.matrix.length,
        threads: layout.threads.length / 6,
        bundled: layout.bundles.length / 6,
        uncovered: layout.uncovered,
      },
      view: () => {
        const f = focus.current;
        return { tier: f.tier, exactSegments: f.exact, bundledSegments: f.bundled, focusIslands: f.islands, distanceRatio: lastRatio.current };
      },
      setDistanceRatio: (r) => {
        const dir = camera.position.clone().sub(controls.target).normalize();
        camera.position.copy(controls.target).addScaledVector(dir, r * fit.dist);
        controls.update();
        invalidate();
      },
      screenPoint: picker.screenPoint,
      pickAt: (x, y) => {
        const p = picker.pickAt(x, y);
        return p ? { kind: p.kind, key: p.key, id: p.id, cluster: p.cluster } : null;
      },
    };
    invalidate();
    return () => {
      if (window.__testmentorLayers) window.__testmentorLayers.ready = false;
    };
  }, [gl, layout, picker, invalidate, camera, controls, fit]);

  return <primitive object={objects.group} />;
}

/** Positions a label at a canvas point; hides it when off screen. */
function place(s: HTMLElement, p: { x: number; y: number } | null): void {
  if (!p) {
    if (s.style.display !== "none") s.style.display = "none";
    return;
  }
  if (s.style.display === "none") s.style.display = "";
  s.style.transform = `translate(${Math.round(p.x)}px, ${Math.round(p.y)}px)`;
}
