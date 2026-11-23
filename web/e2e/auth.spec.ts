import { expect, test } from "@playwright/test";
import { PASSWORD, login } from "./helpers";

/** Paket 10: parolalı giriş. Sunucu `auth.mode: password` ile açılır (Compose'ta
 *  TESTMENTOR_AUTH_MODE=password) ve `ayse` kullanıcısı E2E_PASSWORD parolasıyla eklenir.
 *  Başlık kipinde (varsayılan) yalnızca parola alanının olmadığı denetlenir. */

const passwordMode = PASSWORD !== "";

test("başlık kipinde parola alanı yok", async ({ page }) => {
  test.skip(passwordMode, "sunucu parolalı kipte");
  await page.goto("/");
  await expect(page.getByTestId("user-name")).toBeVisible();
  await expect(page.getByTestId("user-password")).toHaveCount(0);
});

test("parolalı giriş: yanlış parola reddedilir, jetonsuz istek 401, bozuk jeton giriş ekranına döndürür", async ({ page }) => {
  test.skip(!passwordMode, "E2E_PASSWORD yok: sunucu başlık kipinde");

  await test.step("Sunucu parolalı kipte; jetonsuz REST isteği 401", async () => {
    const config = await page.request.get("/auth/config");
    expect(await config.json()).toEqual({ mode: "password" });
    expect((await page.request.get("/projects")).status()).toBe(401);
    expect((await page.request.get("/projects", { headers: { "X-User": "ayse" } })).status()).toBe(401);
  });

  await test.step("Yanlış parola hata gösterir", async () => {
    await page.goto("/");
    await page.getByTestId("user-name").fill("ayse");
    await page.getByTestId("user-password").fill("yanlis-parola");
    await page.getByTestId("user-submit").click();
    await expect(page.getByTestId("login-error")).toContainText("parola yanlış");
    await expect(page.getByTestId("projects-page")).toHaveCount(0);
  });

  await test.step("Doğru parolayla giriş; jeton REST'te geçerli", async () => {
    await login(page, "ayse");
    const token = await page.evaluate(() => sessionStorage.getItem("testmentor.token"));
    expect(token).toBeTruthy();
    const res = await page.request.get("/projects", { headers: { Authorization: `Bearer ${token}` } });
    expect(res.status()).toBe(200);
  });

  await test.step("Sayfa yenilenince oturum sürer", async () => {
    await page.reload();
    await expect(page.getByTestId("projects-page")).toBeVisible();
  });

  await test.step("Bozuk jeton giriş ekranına döndürür", async () => {
    await page.evaluate(() => sessionStorage.setItem("testmentor.token", "bozuk.jeton"));
    await page.reload();
    await expect(page.getByTestId("user-password")).toBeVisible();
  });
});
