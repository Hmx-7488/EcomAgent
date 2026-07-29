import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const adminUsername = process.env.E2E_ADMIN_USERNAME || "admin";
const adminPassword = process.env.E2E_ADMIN_PASSWORD;
const operatorUsername =
  process.env.E2E_OPERATOR_USERNAME || "operator_content";
const operatorPassword = process.env.E2E_OPERATOR_PASSWORD;
const serviceUsername =
  process.env.E2E_SERVICE_USERNAME || "customer_service";
const servicePassword = process.env.E2E_SERVICE_PASSWORD;

function requireCredential(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(`${name} is required; no default Demo password is embedded`);
  }
  return value;
}

async function login(page: Page, username: string, password: string) {
  await page.goto("/login");
  await page.locator('input[autocomplete="username"]').fill(username);
  await page.locator('input[autocomplete="current-password"]').fill(password);
  await page.locator('button[type="submit"]').click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/);
}

async function capture(page: Page, name: string) {
  const output = path.join(
    "test-results",
    "p0-evidence",
    test.info().project.name,
    `${name}.png`,
  );
  await page.screenshot({ path: output, fullPage: true });
  test.info().annotations.push({ type: "evidence", description: output });
}

async function completeLowRiskConsultation(page: Page) {
  await page.goto("/consult");
  await expect(page.locator(".consult-shell")).toBeVisible();
  await expect(page.locator(".product-select")).toContainText("栖纳");
  await page.locator(".conversation-empty button").click();
  await expect(page.locator(".composer")).toBeVisible();
  await page.locator(".composer textarea").fill("这款商品是什么材质？");
  await page.locator('.composer button[type="submit"]').click();
  await expect(page.locator(".message.system")).toBeVisible();
  await expect(page.locator(".message-list")).toContainText("材质");
}
test("anonymous user is redirected from the product workbench", async ({
  page,
}) => {
  await page.goto("/products");
  await expect(page).toHaveURL(/\/login\?redirect=(?:%2F|\/)products$/);
  await expect(page.locator(".login-card")).toBeVisible();
  await capture(page, "anonymous-login-redirect");
});

test("real admin login opens the backend workbench", async ({ page }) => {
  await login(
    page,
    adminUsername,
    requireCredential("E2E_ADMIN_PASSWORD", adminPassword),
  );
  await expect(page).toHaveURL(/\/products$/);
  if (test.info().project.name.startsWith("mobile")) {
    await expect(page.locator(".sidebar")).toBeHidden();
  } else {
    await expect(page.locator(".sidebar")).toBeVisible();
  }
  await expect(page.locator(".workspace")).toBeVisible();
  const productRows = page.locator(".el-table__row");
  await expect(productRows.first()).toContainText("栖纳");
  await expect(page.locator("body")).not.toContainText("M4 acceptance product");
  await capture(page, "admin-products");
});

test("operator cannot enter the service route", async ({ page }) => {
  await login(
    page,
    operatorUsername,
    requireCredential("E2E_OPERATOR_PASSWORD", operatorPassword),
  );
  await page.goto("/service");
  await expect(page).toHaveURL(/\/forbidden$/);
  await capture(page, "operator-service-forbidden");
});

test("customer service can enter service but not financial products", async ({
  page,
}) => {
  await login(
    page,
    serviceUsername,
    requireCredential("E2E_SERVICE_PASSWORD", servicePassword),
  );
  await expect(page).toHaveURL(/\/service$/);
  await expect(page.locator(".service-grid")).toBeVisible();
  await expect(page.locator(".queue-row").first()).toBeVisible();
  await page.locator(".queue-row").first().click();
  await expect(page.locator(".case-panel")).toBeVisible();
  await expect(page.locator(".timeline-item").first()).toBeVisible();
  await expect(page.locator(".source-row").first()).toBeVisible();
  await expect(page.locator(".review-panel")).toBeVisible();
  await expect(page.locator(".original-draft p")).not.toBeEmpty();
  await capture(page, "service-workspace");
  await page.goto("/products");
  await expect(page).toHaveURL(/\/forbidden$/);
});

test("public consultation page is separate from the back office", async ({
  page,
}) => {
  await completeLowRiskConsultation(page);
  await expect(page.locator(".sidebar")).toHaveCount(0);
  await expect(page.locator("body")).not.toContainText(/purchase_cost|gross_margin/i);
  await capture(page, "customer-consult");
});

test("mobile consultation has no horizontal overflow", async ({ page }) => {
  test.skip(
    !test.info().project.name.startsWith("mobile"),
    "mobile viewport assertion",
  );
  await completeLowRiskConsultation(page);
  const dimensions = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
  await capture(page, "customer-consult-mobile");
});
