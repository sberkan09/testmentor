import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, type Page } from "@playwright/test";

/** Altın set v0'ın ilk projesi (8 gereksinim) csv olarak. */
export function goldenCsv(): string {
  const path = fileURLToPath(new URL("../../eval/golden/altin-set-v0.json", import.meta.url));
  const data = JSON.parse(readFileSync(path, "utf8")) as { projects: { requirements: { id: string; language: string; text: string }[] }[] };
  const reqs = data.projects[0]?.requirements ?? [];
  const esc = (s: string) => `"${s.replaceAll('"', '""')}"`;
  return ["id,language,text", ...reqs.map((r) => [r.id, r.language, esc(r.text)].join(","))].join("\n");
}

/** Parolalı kipte (sunucu `auth.mode: password`) kullanılan parola; kullanıcılar koşudan önce
 *  `python -m api.users add` ile eklenir. Başlık kipinde parola alanı yoktur. */
export const PASSWORD = process.env["E2E_PASSWORD"] ?? "";

/** Giriş ekranı: kullanıcı adı, parolalı kipte parola. */
export async function login(page: Page, name: string, password = PASSWORD) {
  await page.goto("/");
  await page.getByTestId("user-name").fill(name);
  const pw = page.getByTestId("user-password");
  if (await pw.isVisible()) await pw.fill(password);
  await page.getByTestId("user-submit").click();
  await expect(page.getByTestId("projects-page")).toBeVisible();
}

/** Yeni bir proje içe alır ve stüdyo açılana kadar bekler. */
export async function importProject(page: Page, key: string, name: string) {
  await page.getByTestId("import-open").click();
  await page.getByTestId("import-file").setInputFiles({ name: "altin-set-v0.csv", mimeType: "text/csv", buffer: Buffer.from(goldenCsv(), "utf8") });
  await expect(page.getByTestId("import-preview")).toBeVisible();
  await page.getByTestId("import-name").fill(name);
  await page.getByTestId("import-key").fill(key);
  await page.getByTestId("import-submit").click();
  await expect(page.getByTestId("studio")).toBeVisible();
}

/** REST isteği başlıkları: tarayıcının kullandığı kimlikle (jeton varsa Bearer, yoksa X-User). */
export async function authHeaders(page: Page, name: string): Promise<Record<string, string>> {
  const token = await page.evaluate(() => sessionStorage.getItem("testmentor.token"));
  return token ? { Authorization: `Bearer ${token}` } : { "X-User": encodeURIComponent(name) };
}
