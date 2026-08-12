import { createApp, defineComponent, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const {
  authState,
  createCategory,
  createSku,
  getProduct,
  getMargin,
  listCategories,
  routeProductId,
  saveCosts,
  updateProduct,
  updateSku,
} = vi.hoisted(() => ({
  authState: {
    user: { id: "2", username: "operator_content", role: "operator_content" },
  },
  createCategory: vi.fn(),
  createSku: vi.fn(),
  getProduct: vi.fn(),
  getMargin: vi.fn(),
  listCategories: vi.fn(),
  routeProductId: { value: "3" },
  saveCosts: vi.fn(),
  updateProduct: vi.fn(),
  updateSku: vi.fn(),
}));

vi.mock("../stores/product", () => ({
  useProductStore: () => ({
    categories: [
      { id: 1, name: "居家收纳", is_active: true },
      { id: 2, name: "旅行收纳", is_active: true },
    ],
    createCategory,
    createSku,
    getProduct,
    getMargin,
    listCategories,
    saveCosts,
    updateProduct,
    updateSku,
  }),
}));
vi.mock("../stores/auth", () => ({
  useAuthStore: () => authState,
}));
vi.mock("vue-router", () => ({
  useRoute: () => ({ params: { id: routeProductId.value } }),
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock("../api/client", () => ({
  errorMessage: (error: unknown) =>
    error instanceof Error ? error.message : String(error),
}));

import ProductDetail from "./ProductDetail.vue";

const mountedApps: Array<ReturnType<typeof createApp>> = [];
const persistedCosts = {
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
const readyMargin = {
  sku_id: 31,
  sale_price: 100,
  costs: persistedCosts,
  total_cost: 45,
  estimated_gross_profit: 55,
  estimated_gross_margin_rate: 0.55,
  status: "ready",
};

function productFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: Number(routeProductId.value),
    name: "栖纳收纳箱",
    category: "居家收纳",
    brand: "栖纳家居",
    description: "适合家庭收纳",
    status: "approved",
    created_at: "2026-07-31T10:00:00Z",
    updated_at: "2026-07-31T10:00:00Z",
    skus: [
      {
        id: 31,
        product_id: Number(routeProductId.value),
        sku_name: "标准款",
        spec: "50 × 40 cm",
        color: "米白",
        size: "L",
        image_url: "/uploads/reference.png",
        price: 100,
        status: "active",
        inventory: {
          stock_quantity: 10,
          locked_quantity: 1,
          safety_stock: 2,
        },
      },
    ],
    ...overrides,
  };
}

function registerStubs(app: ReturnType<typeof createApp>) {
  app.component(
    "el-alert",
    defineComponent({
      props: ["title", "type"],
      template: '<div role="alert" :data-type="type">{{ title }}<slot /></div>',
    }),
  );
  app.component("el-skeleton", defineComponent({ template: "<div><slot /></div>" }));
  app.component("el-form", defineComponent({ template: "<form><slot /></form>" }));
  app.component(
    "el-collapse",
    defineComponent({
      props: ["modelValue"],
      emits: ["update:modelValue"],
      template:
        '<div data-testid="sku-collapse" :data-open="(modelValue || []).join(\',\')"><slot /></div>',
    }),
  );
  app.component(
    "el-collapse-item",
    defineComponent({
      props: ["name", "title"],
      template:
        '<section class="sku-item" :data-sku-id="name"><h3 class="sku-title">{{ title }}</h3><slot /></section>',
    }),
  );
  app.component(
    "el-form-item",
    defineComponent({
      props: ["label", "error"],
      template: '<label>{{ label }}<slot /><span v-if="error">{{ error }}</span></label>',
    }),
  );
  app.component(
    "el-input",
    defineComponent({
      props: ["modelValue", "disabled", "type"],
      emits: ["update:modelValue", "blur"],
      template:
        '<input :value="modelValue ?? \'\'" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value)" @blur="$emit(\'blur\')" />',
    }),
  );
  app.component(
    "el-input-number",
    defineComponent({
      props: ["modelValue", "disabled"],
      emits: ["update:modelValue", "change"],
      methods: {
        emitNumber(event: Event) {
          const value = Number((event.target as HTMLInputElement).value);
          this.$emit("update:modelValue", value);
          this.$emit("change", value);
        },
      },
      template:
        '<input :value="modelValue" :disabled="disabled" @input="emitNumber" />',
    }),
  );
  app.component(
    "el-select",
    defineComponent({
      props: ["modelValue", "disabled", "loading", "filterable"],
      emits: ["update:modelValue"],
      template:
        '<select :value="modelValue" :disabled="disabled" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
    }),
  );
  app.component(
    "el-option",
    defineComponent({
      props: ["label", "value"],
      template: '<option :value="value">{{ label }}</option>',
    }),
  );
  app.component(
    "el-button",
    defineComponent({
      props: ["disabled", "loading", "type", "link"],
      emits: ["click"],
      template:
        '<button type="button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    }),
  );
}

async function flushUi() {
  for (let index = 0; index < 10; index += 1) await Promise.resolve();
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

function button(host: HTMLElement, label: string) {
  return Array.from(host.querySelectorAll("button")).find((candidate) =>
    candidate.textContent?.includes(label),
  ) as HTMLButtonElement | undefined;
}

async function setInput(host: HTMLElement, label: string, value: string) {
  const input = host.querySelector(`[aria-label="${label}"]`) as HTMLInputElement | null;
  expect(input, `missing input ${label}`).not.toBeNull();
  if (!input) return;
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  await nextTick();
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

describe("ProductDetail product, SKU, and cost maintenance", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    routeProductId.value = "3";
    authState.user = {
      id: "2",
      username: "operator_content",
      role: "operator_content",
    };
    listCategories.mockResolvedValue([
      { id: 1, name: "居家收纳", is_active: true },
      { id: 2, name: "旅行收纳", is_active: true },
    ]);
    getProduct.mockImplementation(async () => productFixture());
    getMargin.mockResolvedValue(readyMargin);
    saveCosts.mockResolvedValue(persistedCosts);
    updateProduct.mockImplementation(async (_id, payload) => ({
      ...productFixture(),
      ...payload,
      updated_at: "2026-08-11T10:00:00Z",
    }));
    updateSku.mockImplementation(async (id, payload) => ({
      ...productFixture().skus[0],
      id,
      ...payload,
    }));
    createSku.mockImplementation(async (productId, payload) => ({
      id: 91,
      product_id: productId,
      ...payload,
      status: "active",
    }));
  });

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("saves only product facts and shows a visible success result", async () => {
    updateProduct.mockResolvedValueOnce({
      ...productFixture(),
      name: "后端规范化商品名称",
      updated_at: "2026-08-11T12:00:00Z",
    });
    const host = await mountView();

    button(host, "保存商品信息")?.click();
    await flushUi();

    expect(updateProduct).toHaveBeenCalledTimes(1);
    expect(updateProduct).toHaveBeenCalledWith(3, {
      name: "栖纳收纳箱",
      category: "居家收纳",
      brand: "栖纳家居",
      description: "适合家庭收纳",
    });
    expect(updateProduct.mock.calls[0][1]).not.toHaveProperty("skus");
    expect(host.textContent).toContain("商品信息已保存");
    expect(host.textContent).toContain("后端规范化商品名称");
  });

  it("locks concurrent product saves and reports failure without retry", async () => {
    const pending = deferred<Record<string, unknown>>();
    updateProduct.mockReturnValueOnce(pending.promise);
    const host = await mountView();
    const save = button(host, "保存商品信息");

    save?.click();
    save?.click();
    await nextTick();
    expect(updateProduct).toHaveBeenCalledTimes(1);

    pending.reject(new Error("商品保存失败"));
    await flushUi();
    expect(host.textContent).toContain("商品保存失败");
    expect(updateProduct).toHaveBeenCalledTimes(1);
  });

  it("updates one dirty SKU with only editable facts and refreshes its snapshot", async () => {
    const host = await mountView();
    await setInput(host, "SKU 名称 31", "升级款");
    await setInput(host, "SKU 零售价 31", "128");

    expect(host.textContent).toContain("SKU 信息尚未保存");
    button(host, "保存 SKU 信息")?.click();
    await flushUi();

    expect(updateSku).toHaveBeenCalledTimes(1);
    expect(updateSku).toHaveBeenCalledWith(31, {
      sku_name: "升级款",
      spec: "50 × 40 cm",
      price: 128,
    });
    expect(updateSku.mock.calls[0][1]).not.toHaveProperty("color");
    expect(updateSku.mock.calls[0][1]).not.toHaveProperty("inventory");
    expect(host.textContent).toContain("升级款 · 零售价 ¥128.00");
    expect(host.textContent).toContain("SKU 信息已保存");

    button(host, "保存 SKU 信息")?.click();
    await flushUi();
    expect(updateSku).toHaveBeenCalledTimes(1);
    expect(host.textContent).not.toContain("SKU 信息尚未保存");
  });

  it("does not PUT an unchanged SKU", async () => {
    const host = await mountView();

    button(host, "保存 SKU 信息")?.click();
    await flushUi();

    expect(updateSku).not.toHaveBeenCalled();
  });

  it("allows only one in-flight SKU update", async () => {
    const pending = deferred<Record<string, unknown>>();
    updateSku.mockReturnValueOnce(pending.promise);
    const host = await mountView();
    await setInput(host, "SKU 规格 31", "升级规格");
    const save = button(host, "保存 SKU 信息");

    save?.click();
    save?.click();
    await nextTick();
    expect(updateSku).toHaveBeenCalledTimes(1);

    pending.resolve({
      ...productFixture().skus[0],
      spec: "升级规格",
    });
    await flushUi();
  });

  it("keeps unsaved SKU input after a failed update and never retries", async () => {
    updateSku.mockRejectedValueOnce(new Error("SKU 保存失败"));
    const host = await mountView();
    await setInput(host, "SKU 名称 31", "保留此输入");

    button(host, "保存 SKU 信息")?.click();
    await flushUi();

    expect(updateSku).toHaveBeenCalledTimes(1);
    expect((host.querySelector('[aria-label="SKU 名称 31"]') as HTMLInputElement).value).toBe(
      "保留此输入",
    );
    expect(host.textContent).toContain("SKU 保存失败");
    expect(host.textContent).toContain("SKU 信息尚未保存");
  });

  it.each(["admin", "operator_content"])(
    "shows the add-SKU entry for %s",
    async (role) => {
      authState.user = { id: "8", username: role, role };
      const host = await mountView();

      expect(button(host, "新增 SKU/规格")).toBeTruthy();
    },
  );

  it("keeps customer_service read-only without category or SKU write access", async () => {
    authState.user = {
      id: "3",
      username: "customer_service",
      role: "customer_service",
    };
    const host = await mountView();

    expect(listCategories).not.toHaveBeenCalled();
    expect(button(host, "新增 SKU/规格")).toBeUndefined();
    expect(button(host, "保存 SKU 信息")).toBeUndefined();
    expect(createSku).not.toHaveBeenCalled();
    expect(updateSku).not.toHaveBeenCalled();
  });

  it("creates a zero-price SKU for the routed product, appends it, and opens it", async () => {
    routeProductId.value = "47";
    const host = await mountView();
    button(host, "新增 SKU/规格")?.click();
    await nextTick();
    await setInput(host, "新 SKU 名称", "零价体验款");
    await setInput(host, "新 SKU 规格", "基础规格");
    await setInput(host, "新 SKU 零售价", "0");

    button(host, "创建 SKU")?.click();
    await flushUi();

    expect(createSku).toHaveBeenCalledTimes(1);
    expect(createSku).toHaveBeenCalledWith(47, {
      sku_name: "零价体验款",
      spec: "基础规格",
      price: 0,
    });
    expect(updateProduct).not.toHaveBeenCalled();
    expect(host.textContent).toContain("零价体验款 · 零售价 ¥0.00");
    expect(host.querySelector('[data-testid="sku-collapse"]')?.getAttribute("data-open")).toContain(
      "91",
    );
  });

  it.each([
    ["空白名称", " ", "0"],
    ["负价", "新规格", "-1"],
    ["NaN", "新规格", "NaN"],
    ["正无穷", "新规格", "Infinity"],
    ["负无穷", "新规格", "-Infinity"],
  ])("blocks invalid new SKU input: %s", async (_case, name, price) => {
    const host = await mountView();
    button(host, "新增 SKU/规格")?.click();
    await nextTick();
    await setInput(host, "新 SKU 名称", name);
    await setInput(host, "新 SKU 零售价", price);

    button(host, "创建 SKU")?.click();
    await flushUi();

    expect(createSku).not.toHaveBeenCalled();
    expect(host.textContent).toMatch(/SKU 名称不能为空|零售价必须是大于等于 0 的有限数字/);
  });

  it("does not append a fake SKU or retry when creation fails", async () => {
    createSku.mockRejectedValueOnce(new Error("SKU 新增失败"));
    const host = await mountView();
    button(host, "新增 SKU/规格")?.click();
    await nextTick();
    await setInput(host, "新 SKU 名称", "失败款");

    button(host, "创建 SKU")?.click();
    await flushUi();

    expect(createSku).toHaveBeenCalledTimes(1);
    expect(host.querySelectorAll(".sku-item")).toHaveLength(1);
    expect(host.textContent).toContain("SKU 新增失败");
  });

  it("shows a visible cost-save success result", async () => {
    const host = await mountView();

    button(host, "保存成本")?.click();
    await flushUi();

    expect(saveCosts).toHaveBeenCalledTimes(1);
    expect(getMargin).toHaveBeenCalledTimes(2);
    expect(updateSku).not.toHaveBeenCalled();
    expect(host.textContent).toContain("成本已保存");
  });

  it("treats a zero-price margin as a successful cost save that stays pending", async () => {
    getProduct.mockImplementation(async () =>
      productFixture({
        skus: [{ ...productFixture().skus[0], price: 0 }],
      }),
    );
    getMargin.mockResolvedValue({
      ...readyMargin,
      sale_price: 0,
      status: "pending_confirmation",
      estimated_gross_profit: null,
      estimated_gross_margin_rate: null,
    });
    const host = await mountView();

    button(host, "保存成本")?.click();
    await flushUi();

    expect(saveCosts).toHaveBeenCalledTimes(1);
    expect(host.textContent).toContain("成本已保存；零售价为 0，毛利继续待确认");
    expect(host.textContent).not.toContain("成本保存失败");
  });

  it("blocks cost saving when the unsaved SKU price changed", async () => {
    const host = await mountView();
    await setInput(host, "SKU 零售价 31", "80");

    button(host, "保存成本")?.click();
    await flushUi();

    expect(saveCosts).not.toHaveBeenCalled();
    expect(getMargin).toHaveBeenCalledTimes(1);
    expect(host.textContent).toContain("请先保存 SKU 信息");
  });

  it("allows only one in-flight cost POST", async () => {
    const pending = deferred<typeof persistedCosts>();
    saveCosts.mockReturnValueOnce(pending.promise);
    const host = await mountView();
    const save = button(host, "保存成本");

    save?.click();
    save?.click();
    await nextTick();
    expect(saveCosts).toHaveBeenCalledTimes(1);

    pending.resolve(persistedCosts);
    await flushUi();
  });

  it("reports a cost failure without retrying", async () => {
    saveCosts.mockRejectedValueOnce(new Error("成本保存失败"));
    const host = await mountView();

    button(host, "保存成本")?.click();
    await flushUi();

    expect(saveCosts).toHaveBeenCalledTimes(1);
    expect(host.textContent).toContain("成本保存失败");
  });

  it("loads persisted costs, margin, and the searchable category dictionary", async () => {
    const host = await mountView();

    expect(getMargin).toHaveBeenCalledWith(31);
    expect(host.textContent).toContain("55.00");
    expect(host.textContent).toContain("55.00%");
    expect(listCategories).toHaveBeenCalledTimes(1);
    const select = host.querySelector('select[aria-label="商品类目"]');
    expect(select?.textContent).toContain("居家收纳");
    expect(select?.textContent).toContain("旅行收纳");
  });
});
