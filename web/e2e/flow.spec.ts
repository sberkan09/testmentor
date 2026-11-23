import { readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";

/** Paket 8 bitti testi: yükle, öbekleri gör, taşı, test durumunu düzenle ve sabitle, matrisi gör,
 *  xlsx indir; iki sekmede çakışma. Her adım `test.step` ve `data-testid` ile adlandırılır, böylece
 *  koşu (E2E_VIDEO=on) olduğu gibi demo videosuna dönüşür. */

const VIDEO = process.env["E2E_VIDEO"] === "on";
const pace = (page: Page, ms = 1200) => (VIDEO ? page.waitForTimeout(ms) : Promise.resolve());

function goldenCsv(): string {
  const path = fileURLToPath(new URL("../../eval/golden/altin-set-v0.json", import.meta.url));
  const data = JSON.parse(readFileSync(path, "utf8")) as { projects: { requirements: { id: string; language: string; text: string }[] }[] };
  const reqs = data.projects[0]?.requirements ?? [];
  const esc = (s: string) => `"${s.replaceAll('"', '""')}"`;
  return ["id,language,text", ...reqs.map((r) => [r.id, r.language, esc(r.text)].join(","))].join("\n");
}

const clusterSections = (page: Page) => page.locator('section[data-testid^="cluster-"]');

async function login(page: Page, name: string) {
  await page.goto("/");
  await page.getByTestId("user-name").fill(name);
  await page.getByTestId("user-submit").click();
  await expect(page.getByTestId("projects-page")).toBeVisible();
}

test("yükle, öbekle, taşı, düzenle, sabitle, matrisi dışa aktar", async ({ page, browser }) => {
  const key = `E${Date.now().toString(36).toUpperCase()}`;
  let movedChip = "";
  let caseTestId = "";

  await test.step("Kullanıcı adını gir", async () => {
    await login(page, "ayse");
    await expect(page.getByTestId("projects-empty").or(page.locator('[data-testid^="project-"]').first())).toBeVisible();
    await pace(page);
  });

  await test.step("Gereksinim setini yükle ve kolonları eşle", async () => {
    await page.getByTestId("import-open").click();
    await page.getByTestId("import-file").setInputFiles({ name: "altin-set-v0.csv", mimeType: "text/csv", buffer: Buffer.from(goldenCsv(), "utf8") });
    await expect(page.getByTestId("import-preview")).toBeVisible();
    await expect(page.getByTestId("map-text")).toHaveValue("text");
    await expect(page.getByTestId("map-id")).toHaveValue("id");
    await page.getByTestId("import-name").fill("e-Başvuru Portalı");
    await page.getByTestId("import-key").fill(key);
    await pace(page, 2000);
    await page.getByTestId("import-submit").click();
  });

  await test.step("Öbekler ve aşama çubuğu görünür", async () => {
    await expect(page.getByTestId("studio")).toBeVisible();
    await expect(page.getByTestId("project-name")).toHaveText("e-Başvuru Portalı");
    await expect(page.getByTestId("cluster-grid")).toBeVisible();
    await expect(clusterSections(page).nth(1)).toBeVisible();
    await expect(page.getByTestId("stagebar")).toBeVisible();
    await expect(page.getByTestId("connection")).toHaveText(/Canlı/);
    await pace(page, 2500);
  });

  await test.step("Bir gereksinimi sürükleyip başka öbeğe taşı", async () => {
    const count = await clusterSections(page).count();
    let source = -1;
    for (let i = 0; i < count; i++) {
      if ((await clusterSections(page).nth(i).locator('[data-testid^="chip-"]').count()) >= 2) {
        source = i;
        break;
      }
    }
    expect(source, "en az iki gereksinimli bir öbek").toBeGreaterThanOrEqual(0);
    const target = clusterSections(page).nth(source === 0 ? 1 : 0);
    const chip = clusterSections(page).nth(source).locator('[data-testid^="chip-"]').first();
    movedChip = (await chip.getAttribute("data-testid")) ?? "";
    const a = await chip.boundingBox();
    const b = await target.boundingBox();
    if (!a || !b) throw new Error("sürükleme kutuları yok");
    await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
    await page.mouse.down();
    await page.mouse.move(a.x + a.width / 2 + 12, a.y + a.height / 2 + 12, { steps: 4 });
    await page.mouse.move(b.x + b.width / 2, b.y + 30, { steps: 25 });
    await pace(page, 600);
    await page.mouse.up();
    await expect(target.getByTestId(movedChip)).toBeVisible();
    await expect(clusterSections(page).nth(source).getByTestId(movedChip)).toHaveCount(0);
    await pace(page, 1500);
  });

  await test.step("Bir test durumunu aç, adımını düzenle ve sabitle", async () => {
    const row = page.locator('[data-testid^="case-"]').first();
    await expect(row).toBeVisible({ timeout: 60_000 });
    caseTestId = (await row.getAttribute("data-testid")) ?? "";
    await row.click();
    await expect(page.getByTestId("inspector-test-case")).toBeVisible();
    await expect(page.getByTestId("status-running")).toHaveCount(0, { timeout: 60_000 });
    const expected = page.getByTestId("step-1-expected");
    await expected.fill("Beklenen sonuç elle düzeltildi: sistem işlemi tamamlar.");
    await pace(page, 800);
    await page.getByTestId("save").click();
    if (await page.getByTestId("pin").isVisible()) await page.getByTestId("pin").click();
    await expect(page.getByTestId("pinned-pill")).toBeVisible();
    await expect(page.getByTestId("step-1-expected")).toHaveValue(/elle düzeltildi/);
    await pace(page, 1500);
  });

  await test.step("Matris görünümünde kapsama görünür", async () => {
    await page.getByTestId("view-matrix").click();
    await expect(page.getByTestId("matrix-table")).toBeVisible();
    await expect(page.getByTestId("matrix-coverage")).toHaveText(/%\d+/);
    await expect(page.locator('[data-testid^="covered-"]').first()).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId("matrix-covered")).not.toHaveText("0");
    await pace(page, 2500);
  });

  await test.step("xlsx indir, dosya boş değil", async () => {
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("matrix-download").click()]);
    const path = await download.path();
    expect(download.suggestedFilename()).toMatch(/\.xlsx$/);
    expect(statSync(path).size).toBeGreaterThan(0);
  });

  await test.step("İkinci sekme: güncel durum ve kilit görünür", async () => {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await ctx.addInitScript(() => localStorage.setItem("testmentor.user", "mehmet"));
    const second = await ctx.newPage();
    await second.goto("/");
    await second.getByTestId(`project-${key}`).click();
    await expect(second.getByTestId("studio")).toBeVisible();
    // Birinci sekme: kümeleri göster, test durumunu seç, başlığı değiştirmeye başla (kilit alınır).
    await page.getByTestId("view-clusters").click();
    await page.getByTestId(caseTestId).click();
    await second.getByTestId(caseTestId).click();
    await page.getByTestId("tc-title").fill("Ayşe'nin yeni başlığı");
    await expect(second.getByTestId("lock-banner")).toBeVisible();
    await expect(second.getByTestId("tc-title")).toBeDisabled();
    // Kaydedince ikinci sekmede yeni başlık görünür.
    await page.getByTestId("save").click();
    await expect(second.getByTestId("tc-title")).toHaveValue("Ayşe'nin yeni başlığı");
    // Taşınan gereksinim ikinci sekmede de yeni öbekte.
    await expect(second.getByTestId(movedChip).first()).toBeVisible();
    await ctx.close();
  });
});
