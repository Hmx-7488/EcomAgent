import { createApp, defineComponent, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { listApprovedProducts, listPackages, createPackage } = vi.hoisted(() => ({
  listApprovedProducts: vi.fn(),
  listPackages: vi.fn(),
  createPackage: vi.fn(),
}));

vi.mock("../api/milestone2", () => ({
  m2Api: {
    listApprovedProducts,
    listPackages,
    createPackage,
    updatePackage: vi.fn(),
    generatePackage: vi.fn(),
    packageAction: vi.fn(),
  },
}));
vi.mock("../api/client", () => ({
  errorMessage: (error: unknown) => String(error),
}));
vi.mock("element-plus", () => ({
  ElMessage: { success: vi.fn() },
}));

import ContentWorkspace from "./ContentWorkspace.vue";

const mountedApps: Array<ReturnType<typeof createApp>> = [];

function registerStubs(app: ReturnType<typeof createApp>) {
  app.component(
    "el-select",
    defineComponent({
      props: ["modelValue", "loading", "disabled"],
      emits: ["update:modelValue"],
      methods: {
        change(event: Event) {
          this.$emit(
            "update:modelValue",
            Number((event.target as HTMLSelectElement).value),
          );
        },
      },
      template:
        '<select :value="modelValue ?? \'\'" :disabled="disabled" @change="change"><option value="">请选择商品</option><slot /></select>',
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
      props: ["disabled", "loading", "type"],
      emits: ["click"],
      template:
        '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    }),
  );
  for (const name of ["el-alert", "el-tag", "el-tabs", "el-tab-pane"]) {
    app.component(name, defineComponent({ template: "<div><slot /></div>" }));
  }
  app.component(
    "el-input",
    defineComponent({
      props: ["modelValue"],
      emits: ["update:modelValue", "blur"],
      template: '<textarea :value="modelValue" @blur="$emit(\'blur\')" />',
    }),
  );
  app.directive("loading", () => undefined);
}

async function flushUi() {
  await Promise.resolve();
  await Promise.resolve();
  await nextTick();
}

async function mountView() {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const app = createApp(ContentWorkspace);
  registerStubs(app);
  app.mount(host);
  mountedApps.push(app);
  await flushUi();
  return host;
}

describe("ContentWorkspace real product selection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listApprovedProducts.mockResolvedValue([
      { id: 3, name: "栖纳收纳箱", status: "approved" },
      { id: 5, name: "栖纳真空袋", status: "approved" },
    ]);
    listPackages.mockResolvedValue([
      {
        id: 40,
        product_id: 3,
        fact_version: "product-3:v1",
        input_summary: "approved facts",
        title: "",
        selling_points: "",
        detail: "",
        parameters: "",
        faq: "",
        presale_script: "",
        promotion_material: "",
        version: 1,
        status: "draft",
        updated_at: "2026-07-31T10:00:00Z",
      },
    ]);
    createPackage.mockResolvedValue({
      id: 41,
      product_id: 5,
      status: "draft",
    });
  });

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("loads approved non-1 products and creates with the selected id", async () => {
    const host = await mountView();
    const select = host.querySelector("select") as HTMLSelectElement;

    expect(listApprovedProducts).toHaveBeenCalledOnce();
    expect(host.textContent).toContain("栖纳收纳箱");
    expect(host.textContent).toContain("栖纳真空袋");

    select.value = "5";
    select.dispatchEvent(new Event("change", { bubbles: true }));
    await nextTick();
    const createButton = Array.from(host.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("新建内容包"),
    ) as HTMLButtonElement;
    createButton.click();
    await flushUi();

    expect(createPackage).toHaveBeenCalledWith(5);
    expect(createPackage).not.toHaveBeenCalledWith(1);
  });
});
