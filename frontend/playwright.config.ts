import { defineConfig, devices } from "@playwright/test";

const BASE_URL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000";

/**
 * The browser test runs against a built frontend and a real API, both started
 * outside Playwright. Running `next dev` here instead would test a bundle
 * nobody deploys, and the point of this test is the boundary between the two
 * as they actually ship.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: BASE_URL,
    // Kept only for a failure. The catalogue is public and seeded, so a trace
    // carries no personal data, but there is no reason to store passing runs.
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
