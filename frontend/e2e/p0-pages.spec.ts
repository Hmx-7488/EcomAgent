import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const adminUsername = process.env.E2E_ADMIN_USERNAME || "admin";
const adminPassword = process.env.E2E_ADMIN_PASSWORD;
const adminToken = process.env.E2E_ADMIN_TOKEN;
const operatorUsername =
  process.env.E2E_OPERATOR_USERNAME || "operator_content";
const operatorPassword = process.env.E2E_OPERATOR_PASSWORD;
const operatorToken = process.env.E2E_OPERATOR_TOKEN;
const serviceUsername =
  process.env.E2E_SERVICE_USERNAME || "customer_service";
const servicePassword = process.env.E2E_SERVICE_PASSWORD;
const serviceToken = process.env.E2E_SERVICE_TOKEN;
const verifyExistingWriteEvidence =
  process.env.E2E_DEMO_READINESS_VERIFY_ONLY === "1";
const existingPackageId = Number(
  process.env.E2E_DEMO_READINESS_PACKAGE_ID || 0,
);
type BackofficeRole = "admin" | "operator_content" | "customer_service";
const passwordEnvironmentNames: Record<BackofficeRole, string> = {
  admin: "E2E_ADMIN_PASSWORD",
  operator_content: "E2E_OPERATOR_PASSWORD",
  customer_service: "E2E_SERVICE_PASSWORD",
};

function requireCredential(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(`${name} is required; no default Demo password is embedded`);
  }
  return value;
}

async function login(
  page: Page,
  username: string,
  password: string | undefined,
  role: BackofficeRole,
  token?: string,
) {
  await page.goto("/login");
  if (token) {
    await page.evaluate(
      ({ accessToken, user }) => {
        sessionStorage.setItem("ecomagent_token", accessToken);
        sessionStorage.setItem("ecomagent_user", JSON.stringify(user));
      },
      {
        accessToken: token,
        user: { id: username, username, role },
      },
    );
    await page.goto(role === "customer_service" ? "/service" : "/products");
    await expect(page).not.toHaveURL(/\/login(?:\?|$)/);
    return;
  }
  await page.locator('input[autocomplete="username"]').fill(username);
  await page
    .locator('input[autocomplete="current-password"]')
    .fill(requireCredential(passwordEnvironmentNames[role], password));
  await page.locator('button[type="submit"]').click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/);
}

async function installGenerationGuard(page: Page) {
  const blocked: string[] = [];
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const isForbidden =
      (method === "POST" && path === "/api/images/tasks") ||
      (method === "POST" && /\/api\/images\/tasks\/\d+\/retry$/.test(path)) ||
      (method === "POST" &&
        /\/api\/content\/packages\/\d+\/generate$/.test(path));
    if (isForbidden) {
      blocked.push(`${method} ${path}`);
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });
  return blocked;
}

async function approvedProducts(page: Page) {
  return page.evaluate(async () => {
    const token = sessionStorage.getItem("ecomagent_token");
    const response = await fetch(
      "/api/products?page=1&page_size=100&status=approved",
      { headers: { Authorization: `Bearer ${token}` } },
    );
    if (!response.ok) throw new Error(`products request failed: ${response.status}`);
    return response.json() as Promise<{
      items: Array<{
        id: number;
        name: string;
        skus: Array<{ id: number; sku_name: string }>;
      }>;
      total: number;
    }>;
  });
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
  await expect(page.locator("body")).not.toContainText("密码可任意填写");
  await expect(page.locator("body")).not.toContainText("P0 本地 Mock 账号");
  await capture(page, "anonymous-login-redirect");
});

test("real admin login opens the backend workbench", async ({ page }) => {
  await login(
    page,
    adminUsername,
    adminPassword,
    "admin",
    adminToken,
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
    operatorPassword,
    "operator_content",
    operatorToken,
  );
  await page.goto("/service");
  await expect(page).toHaveURL(/\/forbidden$/);
  await capture(page, "operator-service-forbidden");
});

test("real operator completes the bounded demo-readiness content and cost flow", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop-chromium",
    "bounded database writes run once on desktop",
  );
  const blockedGenerationRequests = await installGenerationGuard(page);
  await login(
    page,
    operatorUsername,
    operatorPassword,
    "operator_content",
    operatorToken,
  );

  const products = await approvedProducts(page);
  expect(products.items.map((item) => item.id)).toEqual(
    expect.arrayContaining([3, 4, 5]),
  );
  const contentProduct = products.items.find((item) => item.id === 5);
  expect(contentProduct).toBeTruthy();

  await page.goto("/content");
  let createdPackage: {
    id: number;
    product_id: number;
    current_version_no: number;
    versions: Array<{ id: number }>;
  };
  if (verifyExistingWriteEvidence) {
    expect(existingPackageId).toBeGreaterThan(0);
    createdPackage = await page.evaluate(async (packageId) => {
      const token = sessionStorage.getItem("ecomagent_token");
      const response = await fetch(`/api/content/packages/${packageId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        throw new Error(`content package request failed: ${response.status}`);
      }
      return response.json();
    }, existingPackageId);
  } else {
    await page.locator(".heading-actions .el-select").click();
    await page
      .locator(".el-select-dropdown:visible .el-select-dropdown__item")
      .filter({ hasText: contentProduct!.name })
      .click();
    const packageResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/content/packages",
    );
    await page
      .locator(".heading-actions button")
      .filter({ hasText: "新建内容包" })
      .click();
    const packageResponse = await packageResponsePromise;
    expect(packageResponse.status()).toBe(201);
    createdPackage = await packageResponse.json();
  }
  expect(createdPackage.product_id).toBe(5);
  expect(createdPackage.current_version_no).toBe(1);
  expect(createdPackage.versions).toHaveLength(1);
  await expect(page.locator(".package-list")).toContainText(
    contentProduct!.name,
  );

  const authorizedProducts = products.items.filter((product) =>
    [3, 4, 5].includes(product.id),
  );
  const marginBaseline = await page.evaluate(async (candidateProducts) => {
    const token = sessionStorage.getItem("ecomagent_token");
    for (const product of candidateProducts) {
      for (const sku of product.skus) {
        const response = await fetch(`/api/skus/${sku.id}/margin`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) continue;
        const margin = (await response.json()) as {
          sku_id: number;
          sale_price: number;
          status: string;
          costs: Record<string, number | string | string[]>;
          estimated_gross_profit: number;
          estimated_gross_margin_rate: number;
        };
        if (margin.status === "ready") {
          return {
            productId: product.id,
            skuId: sku.id,
            skuName: sku.sku_name,
            margin,
          };
        }
      }
    }
    return null;
  }, authorizedProducts);
  expect(marginBaseline).not.toBeNull();

  await page.goto(`/products/${marginBaseline!.productId}`);
  const skuPanel = page
    .locator(".el-collapse-item")
    .filter({ hasText: marginBaseline!.skuName });
  await expect(skuPanel).toBeVisible();
  const expectedCosts = {
    purchase_cost: Number(marginBaseline!.margin.costs.purchase_cost),
    packaging_cost: Number(marginBaseline!.margin.costs.packaging_cost),
    shipping_subsidy: Number(
      marginBaseline!.margin.costs.shipping_subsidy,
    ),
    platform_fee: Number(marginBaseline!.margin.costs.platform_fee),
    marketing_allocation: Number(
      marginBaseline!.margin.costs.marketing_allocation,
    ),
    after_sales_loss: Number(
      marginBaseline!.margin.costs.after_sales_loss,
    ),
  };
  if (!verifyExistingWriteEvidence) {
    const costResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname ===
          `/api/skus/${marginBaseline!.skuId}/costs`,
    );
    await skuPanel.getByRole("button", { name: "保存成本" }).click();
    const costResponse = await costResponsePromise;
    expect(costResponse.status()).toBe(200);
    expect(costResponse.request().postDataJSON()).toEqual(expectedCosts);
    const savedCosts = (await costResponse.json()) as Record<string, unknown>;
    expect(savedCosts).toEqual(expect.objectContaining(expectedCosts));
  }

  await page.reload();
  const reloadedPanel = page
    .locator(".el-collapse-item")
    .filter({ hasText: marginBaseline!.skuName });
  await expect(reloadedPanel).toContainText(
    Number(marginBaseline!.margin.estimated_gross_profit).toFixed(2),
  );
  const expectedByLabel: Array<[string, number]> = [
    ["采购成本", expectedCosts.purchase_cost],
    ["包装成本", expectedCosts.packaging_cost],
    ["运费补贴", expectedCosts.shipping_subsidy],
    ["平台费", expectedCosts.platform_fee],
    ["推广分摊", expectedCosts.marketing_allocation],
    ["售后损失", expectedCosts.after_sales_loss],
  ];
  for (const [label, value] of expectedByLabel) {
    await expect(
      reloadedPanel
        .locator(".el-form-item")
        .filter({ hasText: label })
        .locator("input"),
    ).toHaveValue(Number(value).toFixed(2));
  }
  expect(blockedGenerationRequests).toEqual([]);
  await testInfo.attach("demo-readiness-write-evidence", {
    body: JSON.stringify({
      package_id: createdPackage.id,
      version_id: createdPackage.versions[0].id,
      product_id: createdPackage.product_id,
      sku_id: marginBaseline!.skuId,
      cost_values_unchanged: true,
      provider_requests: 0,
    }),
    contentType: "application/json",
  });
  await capture(page, "operator-demo-readiness-cost");
});

test("real image workspace renders all Task 6-11 result assets without generation", async ({
  page,
}) => {
  const blockedGenerationRequests = await installGenerationGuard(page);
  await login(
    page,
    operatorUsername,
    operatorPassword,
    "operator_content",
    operatorToken,
  );
  await page.goto("/image-tasks");

  const expectedAssets = new Map<number, number[]>([
    [6, [10, 11, 12]],
    [7, [15, 16, 17]],
    [8, [18, 19, 20]],
    [9, [21, 22, 23]],
    [10, [24, 25, 26]],
    [11, [27, 28, 29]],
  ]);
  let renderedResults = 0;
  for (const [taskId, assetIds] of expectedAssets) {
    const task = page
      .locator(".task-card")
      .filter({ hasText: `TASK ${taskId}` });
    await expect(task).toBeVisible();
    await expect(task.locator(".result-asset")).toHaveCount(3);
    for (const assetId of assetIds) {
      await expect(task).toContainText(`Asset #${assetId}`);
    }
    renderedResults += await task.locator(".result-asset").count();
  }
  expect(renderedResults).toBe(18);
  expect(blockedGenerationRequests).toEqual([]);
  await capture(page, "operator-image-tasks-18-results");
});

test("customer service can enter service but not financial products", async ({
  page,
}) => {
  await login(
    page,
    serviceUsername,
    servicePassword,
    "customer_service",
    serviceToken,
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
