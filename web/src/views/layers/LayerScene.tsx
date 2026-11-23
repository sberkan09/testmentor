import { useEffect, useMemo, useRef, type MutableRefObject, type RefObject } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { Raycaster, Vector2, Vector3, type InstancedMesh } from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { LayerKind, LayerLayout } from "./layout";
import { buildObjects } from "./objects";

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
  counts: { requirements: number; testCases: number; matrix: number; threads: number; uncovered: number };
  renderer: string;
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
    const dist = radius / Math.sin(fov / 2);
    const target = new Vector3(0, levels.cases, 0);
    const dir = new Vector3(0, 0.62, 1).normalize();
    return { dist, target, position: target.clone().addScaledVector(dir, dist) };
  }, [layout, camera]);

  const reset = useMemo(
    () => () => {
      dive.current = null;
      controls.enabled = true;
      camera.position.copy(fit.position);
      controls.target.copy(fit.target);
      camera.near = Math.max(fit.dist / 500, 0.05);
      camera.far = fit.dist * 6;
      camera.updateProjectionMatrix();
      controls.maxDistance = fit.dist * 2.5;
      controls.minDistance = 2;
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

  useEffect(() => {
    reset();
    handleRef.current = { reset };
  }, [reset, handleRef]);

  // Picking: a ray against the instanced points first, then the nearest point on screen within a
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
      const hits = ray.intersectObjects(
        objects.pickable.map((p) => p.mesh),
        false,
      );
      const hit = hits.find((h) => h.instanceId !== undefined);
      if (hit && hit.instanceId !== undefined) {
        const kind = objects.pickable.find((p) => p.mesh === (hit.object as InstancedMesh))?.kind;
        if (kind) return itemOf(kind, hit.instanceId);
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
      const isl = ray.intersectObject(objects.islands, false).find((h) => h.instanceId !== undefined);
      return isl && isl.instanceId !== undefined ? itemOf("cluster", isl.instanceId) : null;
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
    let down: { x: number; y: number } | null = null;
    const onDown = (e: PointerEvent) => {
      down = e.button === 0 ? { x: e.clientX, y: e.clientY } : null;
    };
    const onUp = (e: PointerEvent) => {
      if (!down || dive.current) return;
      const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
      down = null;
      if (moved > CLICK_SLOP) return;
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
    el.addEventListener("pointerup", onUp);
    return () => {
      el.removeEventListener("pointerdown", onDown);
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
    for (const it of items) {
      if (n >= LABEL_POOL) break;
      const p = local(it.x, it.y, it.z);
      if (!p) continue;
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
        uncovered: layout.uncovered,
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
  }, [gl, layout, picker, invalidate]);

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
