/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const api = process.env.TESTMENTOR_API ?? "http://127.0.0.1:8000";
const proxy = {
  "/projects": { target: api, ws: true, changeOrigin: true },
  "/auth": { target: api, changeOrigin: true },
};

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy },
  preview: { port: 4173, proxy },
  // The lazily loaded layer view chunk carries three.js (~900 kB); the main chunk stays small.
  build: { chunkSizeWarningLimit: 1000 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
