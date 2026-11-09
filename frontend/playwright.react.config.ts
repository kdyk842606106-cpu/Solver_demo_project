import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e/react",
  fullyParallel: false,
  workers: 1,
  timeout: 90000,
  expect: { timeout: 15000 },
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report-react", open: "never" }],
  ],
  outputDir: "test-results-react",
  use: {
    channel:
      process.env.PLAYWRIGHT_CHANNEL ||
      (process.platform === "win32" ? "msedge" : undefined),
    baseURL: process.env.REACT_BASE_URL || "http://127.0.0.1:8016",
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
