import { createApp, defineComponent, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { listApprovedProducts, listTasks, listAssets } = vi.hoisted(() => ({
  listApprovedProducts: vi.fn(),
  listTasks: vi.fn(),
  listAssets: vi.fn(),
}));

vi.mock("../api/milestone2", () => ({
  m2Api: {
    listApprovedProducts,
    listTasks,
    listAssets,
    uploadReference: vi.fn(),
    createTask: vi.fn(),
    taskAction: vi.fn(),
  },
  parseResultAssetIds: (value: string | null | undefined) => {
    try {
      const parsed = JSON.parse(value || "[]");
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  },
}));
vi.mock("../api/client", () => ({
  errorMessage: (error: unknown) => String(error),
}));
vi.mock("element-plus", () => ({
  ElMessage: { success: vi.fn() },
}));

import ImageTasks from "./ImageTasks.vue";

const mountedApps: Array<ReturnType<typeof createApp>> = [];

function registerStubs(app: ReturnType<typeof createApp>) {
  for (const name of ["el-alert", "el-tag", "el-upload"]) {
    app.component(name, defineComponent({ template: "<div><slot /></div>" }));
  }
  app.component(
    "el-select",
    defineComponent({ template: "<select><slot /></select>" }),
  );
  app.component(
    "el-option",
    defineComponent({
      props: ["label", "value"],
      template: '<option :value="value">{{ label }}</option>',
    }),
  );
  app.component(
    "el-input",
    defineComponent({ props: ["modelValue"], template: "<input />" }),
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
  app.component(
    "el-image",
    defineComponent({
      props: ["src", "fit"],
      template: '<img :src="src" />',
    }),
  );
  app.directive("loading", () => undefined);
}

async function flushUi() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await nextTick();
}

async function mountView() {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const app = createApp(ImageTasks);
  registerStubs(app);
  app.mount(host);
  mountedApps.push(app);
  await flushUi();
  return host;
}

describe("ImageTasks formal multi-result display", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listApprovedProducts.mockResolvedValue([
      { id: 3, name: "栖纳收纳箱", status: "approved" },
    ]);
    listTasks.mockResolvedValue([
      {
        id: 6,
        product_id: 3,
        source_asset_id: 9,
        status: "completed",
        style: "minimal",
        model_name: "qwen-image-2.0",
        prompt: "minimal",
        result_asset_ids: "[10,11,12]",
        error_message: null,
        provider: "qwen",
        retry_count: 0,
        approval_status: "draft",
        rejection_reason: null,
        confirmed_by_id: null,
        confirmed_at: null,
        created_at: "2026-07-31T10:00:00Z",
        updated_at: "2026-07-31T10:01:00Z",
      },
    ]);
    listAssets.mockResolvedValue([
      { id: 9, product_id: 3, asset_type: "reference", url: "/uploads/9.png" },
      { id: 10, product_id: 3, asset_type: "generated", url: "/uploads/10.png" },
      { id: 11, product_id: 3, asset_type: "generated", url: "/uploads/11.png" },
      { id: 12, product_id: 3, asset_type: "generated", url: "/uploads/12.png" },
    ]);
  });

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("maps every result_asset_id to AssetRead and preserves task traceability", async () => {
    const host = await mountView();
    const images = Array.from(host.querySelectorAll("img"));

    expect(listAssets).toHaveBeenCalledWith(3);
    expect(images.map((image) => image.getAttribute("src"))).toEqual([
      "/uploads/10.png",
      "/uploads/11.png",
      "/uploads/12.png",
    ]);
    expect(host.textContent).toContain("TASK 6");
    expect(host.textContent).toContain("Asset #10");
    expect(host.textContent).toContain("Asset #11");
    expect(host.textContent).toContain("Asset #12");
    expect(host.textContent).toContain("栖纳收纳箱");
  });
});
