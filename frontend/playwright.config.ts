import { defineConfig, devices } from "@playwright/test";
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:8080";
const realBackendRun = process.env.PLAYWRIGHT_REAL_BACKEND === "1";
if (realBackendRun && process.env.VITE_USE_MOCK !== "false") {
  throw new Error("Real-backend Playwright requires VITE_USE_MOCK=false");
}
const usesMemoryTokens = [
  process.env.E2E_ADMIN_TOKEN,
  process.env.E2E_OPERATOR_TOKEN,
  process.env.E2E_SERVICE_TOKEN,
].some(Boolean);
export default defineConfig({
  testDir: "./e2e", outputDir: "./test-results", reporter: [["list"]],
  use: { baseURL, trace: usesMemoryTokens ? "off" : "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chromium", use: { ...devices["Pixel 7"] } },
  ],
});
