import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against the REAL stack: FastAPI, PostgreSQL, Ollama.
 * Nothing is mocked. Start the backend first (docker compose up -d) with
 * Ollama running; see README.md.
 *
 * Serial, one worker: local Ollama serves one generation at a time, and the
 * API's LLM queue returns 503 when it is busy.
 */
export default defineConfig({
  testDir: "e2e",
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  // Real answers: p95 is ~20 s, plus model load on a cold start.
  timeout: 180_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
