import { existsSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { syntheticSnapshot } from "../src/test/synthetic";

/** Paket 9 bitti testi: 2.000 gereksinim ve ~5.000 test durumlu sentetik snapshot (API'siz, sabit
 *  veri; istekler ve WebSocket Playwright içinde karşılanır) ile katman görünümü açılır. 5 sn fareyle
 *  yörünge hareketinde çizilen karelerin ortalama süresi ≤ 33 ms olmalı; çizim yazılımla yapılır
 *  (SwiftShader). Sonra ışınla seçilen gereksinim öbek görünümünü, matris satırı matris görünümünü açar.
 *
 *  Ölçüm: sahne istek üzerine çizilir (frameloop "demand"); her çizilen karenin zamanı
 *  `window.__testmentorLayers.frames` içine yazılır. Ortalama = (son − ilk) / (kare sayısı − 1),
 *  yalnızca yörünge süresince. Fare her animasyon karesinde bir adım hareket eder. */

const REQUIREMENTS = Number(process.env["E2E_LAYERS_REQS"] ?? 2000);
const ORBIT_MS = 5000;
const MAX_MEAN_MS = 33;
const SNAP = syntheticSnapshot({ requirements: REQUIREMENTS, clusters: Math.max(4, Math.round(REQUIREMENTS / 25)), projectId: "SYN" });

// Yazılım çizimi: ANGLE üzerinden SwiftShader (GPU yok sayılır).
const SOFTWARE_GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"];
const fallback = "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome";
const executablePath = process.env["PW_CHROMIUM_PATH"] ?? (existsSync(fallback) ? fallback : undefined);
test.use({ launchOptions: { ...(executablePath ? { executablePath } : {}), args: SOFTWARE_GL } });

async function serveSnapshot(page: Page) {
  await page.addInitScript(() => localStorage.setItem("testmentor.user", "olcum"));
  await page.route("**/projects", (r) => r.fulfill({ json: [{ id: SNAP.project_id, name: SNAP.name }] }));
  await page.route(`**/projects/${SNAP.project_id}/snapshot`, (r) => r.fulfill({ json: SNAP }));
  // Sunucusuz WebSocket: bağlantı açılır, olay gelmez.
  await page.routeWebSocket(/\/projects\/SYN\/events/, () => undefined);
}

async function openLayers(page: Page) {
  await page.getByTestId("view-layers").click();
  await expect(page.getByTestId("layers-stage").locator("canvas")).toBeVisible();
  await page.waitForFunction(() => window.__testmentorLayers?.ready === true);
}

const nextFrame = (page: Page) => page.evaluate(() => new Promise<number>((r) => requestAnimationFrame(() => r(performance.now()))));

/** A point where a click selects exactly this item (nothing in front of it). */
async function clickable(page: Page, kind: "requirement" | "matrix", keys: string[]) {
  return page.evaluate(
    ({ kind, keys }) => {
      const h = window.__testmentorLayers!;
      for (const key of keys) {
        const p = h.screenPoint(kind, key);
        if (!p) continue;
        const hit = h.pickAt(p.x, p.y);
        if (hit && hit.kind === kind && hit.key === key) return { key, x: p.x, y: p.y };
      }
      return null;
    },
    { kind, keys },
  );
}

test("katman görünümü: 2.000 gereksinimde akıcı yörünge, seçim 2B görünümü açar", async ({ page }) => {
  await serveSnapshot(page);
  await page.goto("/");
  await page.getByTestId(`project-${SNAP.project_id}`).click();
  await expect(page.getByTestId("studio")).toBeVisible();

  await test.step("Katman görünümünü aç", async () => {
    await openLayers(page);
    const info = await page.evaluate(() => ({ counts: window.__testmentorLayers!.counts, renderer: window.__testmentorLayers!.renderer }));
    console.log(`[layers] renderer: ${info.renderer}`);
    console.log(`[layers] counts: ${JSON.stringify(info.counts)}`);
    expect(info.counts.requirements).toBe(REQUIREMENTS);
    expect(info.counts.testCases).toBeGreaterThan(REQUIREMENTS * 2.2);
    expect(info.counts.uncovered).toBeGreaterThan(0);
    await expect(page.getByTestId("layers-uncovered")).toHaveText(String(info.counts.uncovered));
  });

  await test.step("5 sn yörünge: ortalama kare süresi ≤ 33 ms", async () => {
    const box = await page.getByTestId("layers-stage").boundingBox();
    if (!box) throw new Error("tuval yok");
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    await page.mouse.move(cx, cy);
    await page.mouse.down();
    const t0 = await nextFrame(page);
    let now = t0;
    while (now - t0 < ORBIT_MS) {
      const t = (now - t0) / 1000;
      await page.mouse.move(cx + 260 * Math.sin((2 * Math.PI * t) / 2.5), cy + 70 * Math.sin((2 * Math.PI * t) / 5));
      now = await nextFrame(page);
    }
    await page.mouse.up();
    const frames = await page.evaluate(([a, b]) => window.__testmentorLayers!.frames.filter((f) => f >= a! && f <= b!), [t0, now]);
    const n = frames.length;
    const mean = n > 1 ? (frames[n - 1]! - frames[0]!) / (n - 1) : Infinity;
    const deltas = frames.slice(1).map((f, i) => f - frames[i]!);
    const sorted = [...deltas].sort((a, b) => a - b);
    const p95 = sorted[Math.floor(sorted.length * 0.95)] ?? Infinity;
    const result = { frames: n, windowMs: Math.round(now - t0), meanMs: +mean.toFixed(2), p95Ms: +p95.toFixed(2), maxMs: +(sorted.at(-1) ?? 0).toFixed(2) };
    console.log(`[layers] orbit: ${JSON.stringify(result)}`);
    test.info().annotations.push({ type: "frame-time", description: JSON.stringify(result) });
    // Sahne gerçekten çizildi mi: 5 sn'de en az 100 kare (30 fps'in 2/3'ü).
    expect(n, "yörüngede çizilen kare sayısı").toBeGreaterThanOrEqual(100);
    expect(mean, "ortalama kare süresi (ms)").toBeLessThanOrEqual(MAX_MEAN_MS);
  });

  const reqKeys = SNAP.nodes.filter((n) => n.ref.kind === "requirement").map((n) => n.ref.key).slice(0, 300);

  await test.step("Gereksinim seçilince öbek görünümü açılır", async () => {
    await page.getByTestId("layers-reset").click();
    await nextFrame(page);
    await nextFrame(page);
    const target = await clickable(page, "requirement", reqKeys);
    expect(target, "tıklanabilir gereksinim").not.toBeNull();
    await page.mouse.click(target!.x, target!.y);
    await expect(page.getByTestId("view-clusters")).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("inspector-requirement").locator("h2")).toHaveText(target!.key);
    const cluster = SNAP.nodes.find((n) => n.ref.kind === "cluster" && (n.content?.["members"] as string[]).includes(target!.key))!;
    await expect(page.getByTestId(`cluster-${cluster.ref.key}`)).toBeInViewport();
  });

  await test.step("Matris satırı seçilince matris görünümü açılır", async () => {
    await openLayers(page);
    await nextFrame(page);
    const target = await clickable(page, "matrix", reqKeys);
    expect(target, "tıklanabilir matris satırı").not.toBeNull();
    await page.mouse.click(target!.x, target!.y);
    await expect(page.getByTestId("view-matrix")).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId(`row-${target!.key}`)).toBeInViewport();
    await expect(page.getByTestId("inspector-requirement").locator("h2")).toHaveText(target!.key);
  });
});
