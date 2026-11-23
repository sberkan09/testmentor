import { describe, expect, it } from "vitest";
import { fromSnapshot } from "../../api/state";
import { snapshot } from "../../test/fixtures";
import { syntheticSnapshot } from "../../test/synthetic";
import { buildLayout, islandRadius } from "./layout";

describe("katman düzeni", () => {
  it("küçük projede adaları, noktaları, matris satırlarını ve ipleri üretir", () => {
    const layout = buildLayout(fromSnapshot(snapshot()));
    // Öbek görünümündeki sıra: ada göre (Giriş, Rapor).
    expect(layout.islands.map((i) => i.key)).toEqual(["A", "B"]);
    expect(layout.reqs.map((r) => r.id).sort()).toEqual(["R1", "R2", "R3"]);
    expect(layout.cases.map((c) => c.key)).toEqual(["A:TC-1"]);
    expect(layout.matrix.map((m) => m.id)).toEqual(["R1", "R2", "R3"]);
    // Yalnızca R1 kapsanmış: iki parça (gereksinim → test, test → matris satırı).
    expect(layout.threads.length).toBe(2 * 2 * 3);
    expect(layout.uncovered).toBe(2);
    expect(layout.reqs.find((r) => r.id === "R1")?.covered).toBe(true);
    expect(layout.reqs.find((r) => r.id === "R3")?.covered).toBe(false);
    expect(layout.islands.find((i) => i.key === "A")?.uncovered).toBe(1);
  });

  it("test durumu kapsadığı gereksinimlerin ağırlık merkezinin üstündedir", () => {
    const layout = buildLayout(fromSnapshot(snapshot()));
    const r1 = layout.reqs.find((r) => r.id === "R1")!;
    const tc = layout.cases[0]!;
    expect(Math.hypot(tc.x - r1.x, tc.z - r1.z)).toBeLessThan(0.75);
    // İpin ilk parçası gereksinimden (taban düzlemi) test durumuna (orta düzlem) gider.
    expect([...layout.threads.slice(0, 6)]).toEqual([
      expect.closeTo(r1.x, 4),
      layout.levels.clusters,
      expect.closeTo(r1.z, 4),
      expect.closeTo(tc.x, 4),
      layout.levels.cases,
      expect.closeTo(tc.z, 4),
    ]);
  });

  it("gereksinim noktaları kendi adasının içinde kalır, adalar çakışmaz", () => {
    const layout = buildLayout(fromSnapshot(syntheticSnapshot({ requirements: 400, clusters: 20 })));
    const byKey = new Map(layout.islands.map((i) => [i.key, i]));
    for (const r of layout.reqs) {
      const isl = byKey.get(r.cluster)!;
      expect(Math.hypot(r.x - isl.x, r.z - isl.z)).toBeLessThanOrEqual(isl.radius);
    }
    for (let a = 0; a < layout.islands.length; a++) {
      for (let b = a + 1; b < layout.islands.length; b++) {
        const p = layout.islands[a]!;
        const q = layout.islands[b]!;
        expect(Math.hypot(p.x - q.x, p.z - q.z)).toBeGreaterThanOrEqual(p.radius + q.radius);
      }
    }
    expect(islandRadius(100)).toBeGreaterThan(islandRadius(10));
  });

  it("öbeksiz gereksinimler ayrı bir adada durur", () => {
    const snap = snapshot();
    snap.nodes.push({ ref: { kind: "requirement", key: "R9" }, status: "fresh", pinned: false, origin: "generated", version: 1, content: { id: "R9", text: "x" } });
    const layout = buildLayout(fromSnapshot(snap));
    expect(layout.islands.at(-1)).toMatchObject({ key: "", count: 1, uncovered: 1 });
  });

  it("aynı girdiden aynı düzeni üretir; 2.000 gereksinimde boyutlar doğru", () => {
    const snap = syntheticSnapshot();
    const a = buildLayout(fromSnapshot(snap));
    const b = buildLayout(fromSnapshot(syntheticSnapshot()));
    expect(a.reqs).toEqual(b.reqs);
    expect(a.cases).toEqual(b.cases);
    expect(a.reqs).toHaveLength(2000);
    expect(a.matrix).toHaveLength(2000);
    expect(a.cases.length).toBeGreaterThan(4500);
    expect(a.cases.length).toBeLessThan(5500);
    expect(a.uncovered).toBeGreaterThan(0);
    // Kapsanmamış gereksinimden ip çıkmaz.
    const starts = new Set<string>();
    for (let i = 0; i < a.threads.length; i += 12) starts.add(`${a.threads[i]!.toFixed(3)},${a.threads[i + 2]!.toFixed(3)}`);
    for (const r of a.reqs.filter((x) => !x.covered)) expect(starts.has(`${r.x.toFixed(3)},${r.z.toFixed(3)}`)).toBe(false);
  });
});
