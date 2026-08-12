import { createApp, defineComponent, h, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const {
  authState,
  categoryState,
  createCategory,
  createProduct,
  listCategories,
  prompt,
  routerPush,
} = vi.hoisted(() => ({
  authState: {
    user: { id: "1", username: "admin", role: "admin" },
  },
  categoryState: [
    { id: 1, name: "居家收纳", is_active: true },
    { id: 2, name: "旅行收纳", is_active: true },
  ],
  createCategory: vi.fn(),
  createProduct: vi.fn(),
  listCategories: vi.fn(),
  prompt: vi.fn(),
  routerPush: vi.fn(),
}));

vi.mock("../stores/product", () => ({
  useProductStore: () => ({
    categories: categoryState,
    createCategory,
    createProduct,
    listCategories,
  }),
}));
vi.mock("../stores/auth", () => ({
  useAuthStore: () => authState,
}));
vi.mock("vue-router", () => ({
  useRouter: () => ({ push: routerPush }),
}));
vi.mock("element-plus", () => ({
  ElMessageBox: { prompt },
}));
vi.mock("../api/client", () => ({
  errorMessage: (error: unknown) =>
    error instanceof Error ? error.message : String(error),
}));

import ProductEdit from "./ProductEdit.vue";

const mountedApps: Array<ReturnType<typeof createApp>> = [];

function registerStubs(app: ReturnType<typeof createApp>) {
  app.component(
    "el-form",
    defineComponent({
      setup(_props, { expose, slots }) {
        expose({ validate: () => Promise.resolve(true) });
        return () => h("form", slots.default?.());
      },
    }),
  );
  app.component(
    "el-form-item",
    defineComponent({
      props: ["label"],
      template: "<label>{{ label }}<slot /></label>",
    }),
  );
  app.component(
    "el-input",
    defineComponent({
      props: ["modelValue", "placeholder"],
      emits: ["update:modelValue"],
      template:
        '<input :aria-label="placeholder" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
    }),
  );
  app.component(
    "el-input-number",
    defineComponent({
      props: ["modelValue", "ariaLabel"],
      emits: ["update:modelValue"],
      template:
        '<input type="number" :aria-label="ariaLabel" :value="modelValue" @input="$emit(\'update:modelValue\', Number($event.target.value))" />',
    }),
  );
  app.component(
    "el-select",
    defineComponent({
      props: ["modelValue", "placeholder", "loading", "disabled", "filterable"],
      emits: ["update:modelValue"],
      template:
        '<select aria-label="商品类目" :value="modelValue" :disabled="disabled" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
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
      props: ["disabled", "loading", "type", "link", "plain"],
      emits: ["click"],
      template:
        '<button type="button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    }),
  );
  for (const name of ["el-row", "el-col", "el-divider"]) {
    app.component(name, defineComponent({ template: "<div><slot /></div>" }));
  }
  app.component(
    "el-alert",
    defineComponent({
      props: ["title"],
      template: "<div>{{ title }}<slot /></div>",
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
  const app = createApp(ProductEdit);
  registerStubs(app);
  app.mount(host);
  mountedApps.push(app);
  await flushUi();
  return host;
}

describe("ProductEdit category dictionary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.user = { id: "1", username: "admin", role: "admin" };
    categoryState.splice(
      0,
      categoryState.length,
      { id: 1, name: "居家收纳", is_active: true },
      { id: 2, name: "旅行收纳", is_active: true },
    );
    listCategories.mockResolvedValue([
      { id: 1, name: "居家收纳", is_active: true },
      { id: 2, name: "旅行收纳", is_active: true },
    ]);
    createCategory.mockImplementation(async () => {
      const created = { id: 3, name: "桌面收纳", is_active: true };
      categoryState.push(created);
      return created;
    });
    createProduct.mockResolvedValue({ id: 99 });
    prompt.mockResolvedValue({ value: "  桌面收纳  " });
  });

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("loads a searchable category select instead of a free-text category input", async () => {
    const host = await mountView();

    expect(listCategories).toHaveBeenCalledTimes(1);
    const select = host.querySelector('select[aria-label="商品类目"]');
    expect(select).not.toBeNull();
    expect(select?.textContent).toContain("居家收纳");
    expect(select?.textContent).toContain("旅行收纳");
  });

  it("lets admin add and auto-select a category without saving the product", async () => {
    const host = await mountView();
    const addButton = Array.from(host.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("新增一级类目"),
    ) as HTMLButtonElement;

    addButton.click();
    await flushUi();

    expect(createCategory).toHaveBeenCalledWith("桌面收纳");
    expect((host.querySelector('select[aria-label="商品类目"]') as HTMLSelectElement).value).toBe(
      "桌面收纳",
    );
    expect(createProduct).not.toHaveBeenCalled();
  });

  it("does not expose category creation to operator_content", async () => {
    authState.user = {
      id: "2",
      username: "operator_content",
      role: "operator_content",
    };
    const host = await mountView();

    expect(host.textContent).not.toContain("新增一级类目");
    expect(host.querySelector('select[aria-label="商品类目"]')).not.toBeNull();
  });

  it("shows explicit empty and load-failure messages", async () => {
    listCategories.mockRejectedValueOnce(new Error("类目加载失败，请稍后重试"));
    const failed = await mountView();
    expect(failed.textContent).toContain("类目加载失败，请稍后重试");

    mountedApps.pop()?.unmount();
    failed.remove();
    categoryState.splice(0, categoryState.length);
    listCategories.mockResolvedValueOnce(categoryState);
    const empty = await mountView();
    expect(empty.textContent).toContain("暂无可用一级类目");
  });

  it("allows zero price but blocks negative or non-finite SKU prices before submit", async () => {
    const host = await mountView();
    const inputs = host.querySelectorAll("input");
    const textInputs = Array.from(inputs).filter(
      (input) => input.type !== "number",
    ) as HTMLInputElement[];
    textInputs[0].value = "零价商品";
    textInputs[0].dispatchEvent(new Event("input", { bubbles: true }));
    textInputs.find((input) => input.getAttribute("aria-label") === "SKU 名称")!.value =
      "标准款";
    textInputs
      .find((input) => input.getAttribute("aria-label") === "SKU 名称")!
      .dispatchEvent(new Event("input", { bubbles: true }));
    const select = host.querySelector('select[aria-label="商品类目"]') as HTMLSelectElement;
    select.value = "居家收纳";
    select.dispatchEvent(new Event("change", { bubbles: true }));
    await flushUi();

    const createButton = Array.from(host.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("创建商品"),
    ) as HTMLButtonElement;
    createButton.click();
    await flushUi();
    expect(createProduct).toHaveBeenCalledTimes(1);
    expect(createProduct.mock.calls[0][0].skus[0].price).toBe(0);

    createProduct.mockClear();
    const price = host.querySelector('input[type="number"]') as HTMLInputElement;
    price.value = "-1";
    price.dispatchEvent(new Event("input", { bubbles: true }));
    createButton.click();
    await flushUi();
    expect(createProduct).not.toHaveBeenCalled();
    expect(host.textContent).toContain("SKU 零售价必须是大于或等于 0 的有限数字");
  });
});
