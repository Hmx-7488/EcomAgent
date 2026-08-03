import { createApp, defineComponent, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { getProduct, getMargin, saveCosts, updateProduct } = vi.hoisted(() => ({
  getProduct: vi.fn(),
  getMargin: vi.fn(),
  saveCosts: vi.fn(),
  updateProduct: vi.fn(),
}));

vi.mock("../stores/product", () => ({
  useProductStore: () => ({
    getProduct,
    getMargin,
    saveCosts,
    updateProduct,
  }),
}));
vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({
    user: { id: "2", username: "operator_content", role: "operator_content" },
  }),
}));
vi.mock("vue-router", () => ({
  useRoute: () => ({ params: { id: "3" } }),
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock("../api/client", () => ({
  errorMessage: (error: unknown) => String(error),
}));

import ProductDetail from "./ProductDetail.vue";

const mountedApps: Array<ReturnType<typeof createApp>> = [];
const costs = {
  sku_id: 31,
  purchase_cost: 30,
  packaging_cost: 2,
  shipping_subsidy: 5,
  platform_fee: 4,
  marketing_allocation: 3,
  after_sales_loss: 1,
  completeness: [],
  status: "ready",
};
const margin = {
  sku_id: 31,
  sale_price: 100,
  costs,
  total_cost: 45,
  estimated_gross_profit: 55,
  estimated_gross_margin_rate: 0.55,
  status: "ready",
};

function registerStubs(app: ReturnType<typeof createApp>) {
  for (const name of [
    "el-alert",
    "el-skeleton",
    "el-form",
    "el-collapse",
    "el-collapse-item",
  ]) {
    app.component(name, defineComponent({ template: "<div><slot /></div>" }));
  }
  app.component(
    "el-form-item",
    defineComponent({
      props: ["label", "error"],
      template: "<label>{{ label }}<slot /></label>",
    }),
  );
  app.component(
    "el-input",
    defineComponent({
      props: ["modelValue", "disabled"],
      template: '<input :value="modelValue" :disabled="disabled" />',
    }),
  );
  app.component(
    "el-input-number",
    defineComponent({
      props: ["modelValue", "disabled"],
      emits: ["update:modelValue", "change"],
      template: '<input type="number" :value="modelValue" :disabled="disabled" />',
    }),
  );
  app.component(
    "el-button",
    defineComponent({
      props: ["disabled", "loading", "type", "link"],
      emits: ["click"],
      template:
        '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    }),
  );
}

async function flushUi() {
  await Promise.resolve();
  await Promise.resolve();
  await nextTick();
}

async function mountView() {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const app = createApp(ProductDetail);
  registerStubs(app);
  app.mount(host);
  mountedApps.push(app);
  await flushUi();
  return host;
}

describe("ProductDetail persisted six-part costs", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getProduct.mockResolvedValue({
      id: 3,
      name: "栖纳收纳箱",
      category: "居家收纳",
      status: "approved",
      created_at: "2026-07-31T10:00:00Z",
      updated_at: "2026-07-31T10:00:00Z",
      skus: [
        {
          id: 31,
          product_id: 3,
          sku_name: "标准款",
          price: 100,
          status: "active",
        },
      ],
    });
    getMargin.mockResolvedValue(margin);
    saveCosts.mockResolvedValue(costs);
  });

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("loads backend costs, displays margin, and POST-saves the same six facts", async () => {
    const host = await mountView();

    expect(getMargin).toHaveBeenCalledWith(31);
    expect(host.textContent).toContain("55.00");
    expect(host.textContent).toContain("55.00%");
    const saveButton = Array.from(host.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("保存成本"),
    ) as HTMLButtonElement;
    saveButton.click();
    await flushUi();

    expect(saveCosts).toHaveBeenCalledWith(31, {
      purchase_cost: 30,
      packaging_cost: 2,
      shipping_subsidy: 5,
      platform_fee: 4,
      marketing_allocation: 3,
      after_sales_loss: 1,
    });
    expect(getMargin).toHaveBeenCalledTimes(2);
  });
});
