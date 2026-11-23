import { mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";

/** Demo videosu senaryosu (PoC). Altın set v1 KDH "Vatandaş Başvuru Portalı" (60 TR + 60 EN).
 *  Ekranın altında Türkçe açıklama şeridi çizilir. Uzun beklemelerin başlangıç ve bitişi
 *  `DEMO_MARKS` dosyasına yazılır; `demo/make_video.sh` bu aralıkları hızlandırır.
 *
 *  Koşu: DEMO=1 [DEMO_SHOTS=dizin] [DEMO_MARKS=dosya] npx playwright test e2e/demo.spec.ts --trace off
 *  (video için E2E_VIDEO=on). Gerçek modelle API ayrıca açılır (demo/README.md). */

test.skip(process.env["DEMO"] !== "1", "yalnızca DEMO=1 ile");
test.setTimeout(45 * 60_000);

const SHOTS = process.env["DEMO_SHOTS"];
/** Frame directory: Chromium screencast (CDP) frames with timestamps; demo/make_video.py builds
 *  the MP4 from them (Playwright's own video recorder needs an ffmpeg build not installed here). */
const FRAMES = process.env["DEMO_FRAMES"];
const MARKS = process.env["DEMO_MARKS"];
const KEY = process.env["DEMO_KEY"] ?? `KDH${Date.now().toString(36).slice(-4).toUpperCase()}`;
let started = Date.now(); // reset when the test (and its video) starts
const marks: { name: string; start: number; end?: number; t0: number; t1?: number }[] = [];
let shot = 0;

function kdhCsv(): string {
  const path = fileURLToPath(new URL("../../eval/golden/v1/kdh.json", import.meta.url));
  const data = JSON.parse(readFileSync(path, "utf8")) as {
    requirements: { id: string; language: string; text: string }[];
  };
  const esc = (s: string) => `"${s.replaceAll('"', '""')}"`;
  return ["id,language,text", ...data.requirements.map((r) => [r.id, r.language, esc(r.text)].join(","))].join("\n");
}

async function caption(page: Page, text: string, hold = 3500) {
  await page.evaluate((t) => {
    let el = document.getElementById("demo-caption");
    if (!el) {
      el = document.createElement("div");
      el.id = "demo-caption";
      Object.assign(el.style, {
        position: "fixed", left: "50%", bottom: "128px", transform: "translateX(-50%)", zIndex: "99999",
        maxWidth: "1100px", padding: "14px 22px", borderRadius: "12px", background: "rgba(17,24,39,0.88)",
        color: "#fff", font: "500 21px/1.4 system-ui, -apple-system, 'Segoe UI', sans-serif",
        boxShadow: "0 8px 30px rgba(0,0,0,0.35)", textAlign: "center", pointerEvents: "none",
      });
      document.body.appendChild(el);
    }
    el.textContent = t;
    el.style.display = t ? "block" : "none";
  }, text);
  if (SHOTS) {
    mkdirSync(SHOTS, { recursive: true });
    await page.screenshot({ path: `${SHOTS}/${String(++shot).padStart(2, "0")}.png` });
  }
  await page.waitForTimeout(hold);
}

const seconds = () => (Date.now() - started) / 1000;

async function banner(page: Page, text: string) {
  await page.evaluate((t) => {
    let el = document.getElementById("demo-fast");
    if (!el) {
      el = document.createElement("div");
      el.id = "demo-fast";
      Object.assign(el.style, {
        position: "fixed", left: "50%", top: "70px", transform: "translateX(-50%)", zIndex: "99999",
        padding: "10px 18px", borderRadius: "10px", background: "rgba(79,70,229,0.92)", color: "#fff",
        font: "600 19px/1.3 system-ui, -apple-system, 'Segoe UI', sans-serif", pointerEvents: "none",
      });
      document.body.appendChild(el);
    }
    el.textContent = t;
    el.style.display = t ? "block" : "none";
  }, text);
}

/** Wait until every stage is fresh (no stale, running or queued work); recorded as a mark (the
 *  video compresses it) and shown with a "sped up" banner. */
async function waitIdle(page: Page, name: string, timeoutS = 30 * 60) {
  await banner(page, "⏩ Yerel model üretiyor — bu bölüm videoda hızlandırıldı");
  const mark = { name, start: seconds(), t0: Date.now() / 1000 } as (typeof marks)[number];
  marks.push(mark);
  const deadline = Date.now() + timeoutS * 1000;
  for (;;) {
    const res = await page.request.get(`/projects/${KEY}/snapshot`);
    if (res.ok()) {
      const snap = (await res.json()) as { stages: { stale: number; running: number }[]; jobs: unknown[] };
      const busy = snap.stages.some((s) => s.stale + s.running > 0) || snap.jobs.length > 0;
      if (!busy) break;
    }
    if (Date.now() > deadline) throw new Error(`${name}: iş bitmedi`);
    await page.waitForTimeout(2000);
  }
  mark.end = seconds();
  mark.t1 = Date.now() / 1000;
  await banner(page, "");
}

const clusterSections = (page: Page) => page.locator('section[data-testid^="cluster-"]');

test("demo: Vatandaş Başvuru Portalı", async ({ page }) => {
  started = Date.now();
  const frames: { file: string; t: number }[] = [];
  let stopFrames = async () => {};
  if (FRAMES) {
    mkdirSync(FRAMES, { recursive: true });
    const cdp = await page.context().newCDPSession(page);
    cdp.on("Page.screencastFrame", (f: { data: string; sessionId: number; metadata: { timestamp?: number } }) => {
      const file = `${String(frames.length).padStart(6, "0")}.jpg`;
      writeFileSync(`${FRAMES}/${file}`, Buffer.from(f.data, "base64"));
      frames.push({ file, t: f.metadata.timestamp ?? Date.now() / 1000 });
      void cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => undefined);
    });
    await cdp.send("Page.startScreencast", { format: "jpeg", quality: 85, maxWidth: 1440, maxHeight: 900 });
    stopFrames = async () => {
      await cdp.send("Page.stopScreencast").catch(() => undefined);
      writeFileSync(`${FRAMES}/frames.json`, JSON.stringify({ frames, end: Date.now() / 1000 }));
    };
  }
  await test.step("Açılış", async () => {
    await page.goto("/");
    await caption(page, "testmentor: gereksinim setinden test durumlarına ve izlenebilirlik matrisine, yerel modelle", 4000);
    await page.getByTestId("user-name").fill("Ayşe");
    await page.getByTestId("user-submit").click();
    await expect(page.getByTestId("projects-page")).toBeVisible();
  });

  await test.step("İçe alma", async () => {
    await page.getByTestId("import-open").click();
    await page.getByTestId("import-file").setInputFiles({
      name: "vatandas-basvuru-portali.csv", mimeType: "text/csv", buffer: Buffer.from(kdhCsv(), "utf8"),
    });
    await expect(page.getByTestId("import-preview")).toBeVisible();
    await caption(page, "Gereksinim seti csv ya da xlsx olarak yüklenir; kolonlar eşlenir (120 gereksinim, 60 Türkçe, 60 İngilizce)", 4500);
    await page.getByTestId("import-name").fill("Vatandaş Başvuru Portalı");
    await page.getByTestId("import-key").fill(KEY);
    await page.waitForTimeout(1200);
    await page.getByTestId("import-submit").click();
    await expect(page.getByTestId("studio")).toBeVisible({ timeout: 120_000 });
  });

  await test.step("Öbekleme ve üretim", async () => {
    await expect(page.getByTestId("cluster-grid")).toBeVisible();
    await caption(page, "Gereksinimler embedding ile anlamına göre öbeklenir; öbekler kullanıcı düzenlemesine açıktır", 4500);
    await caption(page, "Yerel model her öbeğe ad ve gerekçe, her gereksinime doğrulama yöntemi ve öbek başına test durumları yazar", 1500);
    await waitIdle(page, "ilk üretim");
    await caption(page, "Üretim bitti: her öbeğin adı, gerekçesi ve test durumları hazır", 4000);
  });

  let caseTestId = "";
  await test.step("Test durumu ve elle düzeltme", async () => {
    const row = page.locator('[data-testid^="case-"]').first();
    await row.scrollIntoViewIfNeeded();
    caseTestId = (await row.getAttribute("data-testid")) ?? "";
    await row.click();
    await expect(page.getByTestId("inspector-test-case")).toBeVisible();
    await caption(page, "Her test durumunun adımları ayrıdır; her adımın kendi beklenen sonucu vardır", 4500);
    const expected = page.getByTestId("step-1-expected");
    const before = await expected.inputValue();
    await expected.fill(`${before} (Ayşe: sonuç ekranda başvuru numarasıyla doğrulanır.)`);
    await caption(page, "Uzman bir adımı düzeltir ve kaydeder", 2500);
    await page.getByTestId("save").click();
    if (await page.getByTestId("pin").isVisible()) await page.getByTestId("pin").click();
    await expect(page.getByTestId("pinned-pill")).toBeVisible();
    await caption(page, "Elle düzeltilen test sabitlenir: yeniden üretimde ezilmez, prompt'a değiştirilemez olarak girer", 4500);
  });

  await test.step("Gereksinimi başka öbeğe taşı", async () => {
    await page.getByTestId("view-clusters").click();
    const count = await clusterSections(page).count();
    let source = -1;
    for (let i = 1; i < count; i++) {
      if ((await clusterSections(page).nth(i).locator('[data-testid^="chip-"]').count()) >= 3) {
        source = i;
        break;
      }
    }
    expect(source).toBeGreaterThanOrEqual(0);
    const target = clusterSections(page).nth(source === 1 ? 2 : 1);
    const chip = clusterSections(page).nth(source).locator('[data-testid^="chip-"]').last();
    await chip.scrollIntoViewIfNeeded();
    await caption(page, "Bir gereksinim sürüklenip başka öbeğe taşınır", 2500);
    const a = await chip.boundingBox();
    const b = await target.boundingBox();
    if (!a || !b) throw new Error("sürükleme kutuları yok");
    await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
    await page.mouse.down();
    await page.mouse.move(a.x + a.width / 2 + 12, a.y + a.height / 2 + 12, { steps: 5 });
    await page.mouse.move(b.x + b.width / 2, b.y + 40, { steps: 30 });
    await page.waitForTimeout(500);
    await page.mouse.up();
    await caption(page, "Yalnızca etkilenen iki öbeğin seti ve adı yeniden üretilir: biri artımlı çağrıyla, diğeri çağrısız budanır; geri kalanı cache'ten gelir", 1500);
    await waitIdle(page, "taşıma");
    await caption(page, "Taşıma birkaç saniyede yansıdı; öbeğin mevcut test durumları korunarak yeni gereksinim için test eklendi", 4500);
  });

  await test.step("Matris ve dışa aktarım", async () => {
    await page.getByTestId("view-matrix").click();
    await expect(page.getByTestId("matrix-table")).toBeVisible();
    await caption(page, "İzlenebilirlik matrisi model çağırmadan türetilir: gereksinim, öbek, doğrulama yöntemi, test durumları, kapsama", 5000);
    await caption(page, "İki tutarlılık uyarısı: yöntemi Test olup testi olmayan ve yöntemi Test olmayıp test yazılmış gereksinim", 4500);
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("matrix-download").click()]);
    expect(statSync(await download.path()).size).toBeGreaterThan(0);
    await caption(page, "Matris ve test durumları xlsx olarak dışa aktarılır", 4000);
    await caption(page, "Tüm üretim tek GPU'lu yerel sunucuda; veri kurum dışına çıkmaz", 4500);
  });

  await stopFrames();
  if (MARKS) writeFileSync(MARKS, JSON.stringify({ marks, key: KEY, case: caseTestId }, null, 2));
});
