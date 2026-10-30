import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for the KisanSahayak AI end-to-end suite.
 *
 * Targets
 *  - Frontend : Next.js farmer voice UI  (http://localhost:3000)
 *  - Backend  : FastAPI pipeline + live data (http://127.0.0.1:8000)
 *
 * Artifacts
 *  - Screenshots : only-on-failure  -> test-results/
 *  - Video       : retain-on-failure-> test-results/
 *  - Trace       : retain-on-failure-> test-results/
 *  - HTML report : playwright-report/index.html (npx playwright show-report)
 *  - JUnit XML   : test-results/junit.xml  (CI ingestion)
 */
const PORT = process.env.E2E_PORT || "3000";
const BASE_URL = process.env.E2E_BASE_URL || `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./tests",
  outputDir: "./test-results",
  timeout: 90_000,
  expect: { timeout: 30_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: process.env.CI ? 2 : 3,
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "playwright-report" }],
    ["junit", { outputFile: "test-results/junit.xml" }]
  ],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    locale: "en-IN",
    timezoneId: "Asia/Kolkata"
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    },
    {
      // Fast smoke subset re-run on a phone-sized viewport.
      name: "mobile-chromium",
      testMatch: /(smoke|language)\.spec\.ts/,
      use: { ...devices["Pixel 5"] }
    }
  ],
  webServer: [
    {
      command:
        "backend\\venv\\Scripts\\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000",
      cwd: "..",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000
    },
    {
      command: "npm run dev",
      cwd: "../frontend",
      url: BASE_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000
    }
  ]
});
