// Interface tests: the real Vue interface in WebKit (the engine of the Tauri window on Linux, WebKitGTK), with the
// Rust side and the engine simulated (e2e/mock-tauri.ts, e2e/fake.ts). Run from app/: pnpm exec playwright test
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  reporter: "list",
  use: {
    baseURL: "http://localhost:1430",
    viewport: { width: 460, height: 940 }, // the coach window (tauri.conf.json)
    trace: "retain-on-failure",
  },
  projects: [{ name: "webkit", use: { ...devices["Desktop Safari"], viewport: { width: 460, height: 940 } } }],
  webServer: {
    command: "pnpm exec vite --port 1430 --strictPort",
    url: "http://localhost:1430/e2e/harness.html",
    reuseExistingServer: !process.env.CI,
  },
});
