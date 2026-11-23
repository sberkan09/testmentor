import { existsSync } from "node:fs";
import { defineConfig } from "@playwright/test";

// E2E_MOCK=1: sahte API (web/mock/server.mjs); aksi halde gerçek API (TESTMENTOR_FAKE_LLM=1).
// E2E_BASE_URL=http://127.0.0.1:18000: zaten çalışan uygulama (Compose, `harici` profili; API ve
// derlenmiş ön yüz aynı adreste). Bu durumda hiçbir sunucu açılmaz.
const mock = process.env["E2E_MOCK"] === "1";
const external = process.env["E2E_BASE_URL"];
const apiPort = process.env["E2E_API_PORT"] ?? "8000";
const webPort = process.env["E2E_WEB_PORT"] ?? "4173";

// Kuruluma göre Chromium yolu: PW_CHROMIUM_PATH ya da /opt/pw-browsers altındaki derleme.
const fallback = "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome";
const executablePath = process.env["PW_CHROMIUM_PATH"] ?? (existsSync(fallback) ? fallback : undefined);

export default defineConfig({
  testDir: "e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: external ?? `http://127.0.0.1:${webPort}`,
    viewport: { width: 1440, height: 900 },
    trace: "off",
    // Demo videosu için: E2E_VIDEO=on npm run e2e
    video: process.env["E2E_VIDEO"] === "on" ? { mode: "on", size: { width: 1440, height: 900 } } : "off",
    launchOptions: executablePath ? { executablePath } : {},
  },
  webServer: external
    ? []
    : [
        mock
          ? { command: "node mock/server.mjs", url: `http://127.0.0.1:${apiPort}/projects`, reuseExistingServer: true, env: { PORT: apiPort } }
          : {
              command: `uv run uvicorn api.main:app --host 127.0.0.1 --port ${apiPort}`,
              cwd: "..",
              url: `http://127.0.0.1:${apiPort}/projects`,
              reuseExistingServer: true,
              timeout: 60_000,
              env: { TESTMENTOR_FAKE_LLM: "1" },
            },
        {
          command: `npm run build && npx vite preview --host 127.0.0.1 --port ${webPort}`,
          url: `http://127.0.0.1:${webPort}`,
          reuseExistingServer: true,
          timeout: 120_000,
          env: { TESTMENTOR_API: `http://127.0.0.1:${apiPort}` },
        },
      ],
});
