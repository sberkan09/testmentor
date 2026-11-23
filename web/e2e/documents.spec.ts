import { expect, test, type Page } from "@playwright/test";
import { authHeaders, importProject, login } from "./helpers";

/** Paket 10: bilgi havuzuna belge yükleme. Yüklemeden sonra öbeğin arama düğümünde belgenin parça
 *  kimlikleri görünür ve o parçalara bağlı test setleri yeniden üretilir. Sahte API'de
 *  (E2E_MOCK=1) bu uç noktalar yoktur. */

test.skip(process.env["E2E_MOCK"] === "1", "sahte API'de bilgi havuzu yok");

const DOC = [
  "# Kimlik doğrulama",
  "",
  "Vatandaş portala e-Devlet Kapısı ile giriş yapar. 15 dakika işlem yapılmayan oturum sonlandırılır.",
  "",
  "# Başvuru belgeleri",
  "",
  "Başvuru formuna PDF, JPEG ya da PNG biçiminde belge eklenir; her belge en fazla 10 MB olabilir.",
  "",
  "# Kişisel veriler",
  "",
  "Kişisel veriler yalnızca Türkiye sınırları içindeki veri merkezlerinde saklanır.",
].join("\n");

interface SnapNode {
  ref: { kind: string; key: string };
  status: string;
  version: number;
  content: Record<string, unknown> | null;
}

async function idleSnapshot(page: Page, key: string, user: string): Promise<SnapNode[]> {
  const headers = await authHeaders(page, user);
  let nodes: SnapNode[] = [];
  await expect
    .poll(
      async () => {
        const res = await page.request.get(`/projects/${key}/snapshot`, { headers });
        const snap = (await res.json()) as { jobs: unknown[]; nodes: SnapNode[] };
        nodes = snap.nodes;
        return snap.jobs.length === 0 && snap.nodes.every((n) => n.status === "fresh");
      },
      { timeout: 60_000 },
    )
    .toBe(true);
  return nodes;
}

const versions = (nodes: SnapNode[], kind: string) =>
  Object.fromEntries(nodes.filter((n) => n.ref.kind === kind).map((n) => [n.ref.key, n.version]));

test("belge yükle, arama düğümünde parça kimliklerini gör, test setleri yeniden üretilsin", async ({ page }) => {
  const key = `D${Date.now().toString(36).toUpperCase()}`;
  const user = "ayse";
  let before: SnapNode[] = [];

  await test.step("Giriş yap ve gereksinim setini yükle", async () => {
    await login(page, user);
    await importProject(page, key, "Belge denemesi");
    before = await idleSnapshot(page, key, user);
  });

  await test.step("Belge yüklenmeden önce öbeğin parçası yok", async () => {
    await page.locator('[data-testid^="cluster-name-"]').first().click();
    await expect(page.getByTestId("inspector-cluster")).toBeVisible();
    await expect(page.getByTestId("passages-empty")).toBeVisible();
  });

  await test.step("Belgeler sekmesinden belge yükle", async () => {
    await page.getByTestId("view-documents").click();
    await expect(page.getByTestId("documents-empty")).toBeVisible();
    await page.getByTestId("document-file").setInputFiles({ name: "Portal Politikası.md", mimeType: "text/markdown", buffer: Buffer.from(DOC, "utf8") });
    await expect(page.getByTestId("document-Portal-Politikası.md")).toBeVisible();
    await expect(page.getByTestId("documents-count")).toHaveText("1");
  });

  await test.step("Arama düğümünde parça kimlikleri görünür", async () => {
    await page.getByTestId("view-clusters").click();
    await page.locator('[data-testid^="cluster-name-"]').first().click();
    await expect(page.getByTestId("passage-id").first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("passage-id").first()).toHaveText(/^Portal-Politikası\.md#\d+$/);
  });

  await test.step("Test setleri yeniden üretildi", async () => {
    const after = await idleSnapshot(page, key, user);
    const old = versions(before, "test_set");
    const now = versions(after, "test_set");
    expect(Object.keys(old).length).toBeGreaterThan(0);
    for (const [k, v] of Object.entries(old)) expect(now[k], `test_set:${k}`).toBeGreaterThan(v);
    const retrieval = after.filter((n) => n.ref.kind === "retrieval");
    expect(retrieval.every((n) => ((n.content?.["passage_ids"] as string[]) ?? []).length > 0)).toBe(true);
  });
});
