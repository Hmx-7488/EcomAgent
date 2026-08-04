import { createApp, defineComponent, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const {
  listApprovedProducts,
  listPackages,
  createPackage,
  updatePackage,
  generatePackage,
  contentGenerationError,
  messageSuccess,
} = vi.hoisted(() => ({
  listApprovedProducts: vi.fn(),
  listPackages: vi.fn(),
  createPackage: vi.fn(),
  updatePackage: vi.fn(),
  generatePackage: vi.fn(),
  contentGenerationError: vi.fn((item: Record<string, unknown>) => {
    const labels: Record<string, string> = {
      no_key: "文本生成服务未配置",
      timeout: "内容生成超时",
      failed: "内容生成失败",
      field_missing: "内容生成结果字段不完整",
    };
    const status = String(item.task_status || "");
    if (status !== "completed") return labels[status] || "内容生成失败";
    const fields = [
      "title",
      "selling_points",
      "detail",
      "parameters",
      "faq",
      "presale_script",
      "promotion_material",
    ];
    return fields.every(
      (field) =>
        typeof item[field] === "string" &&
        Boolean((item[field] as string).trim()),
    )
      ? undefined
      : "内容生成结果字段不完整";
  }),
  messageSuccess: vi.fn(),
}));

vi.mock("../api/milestone2", () => ({
  m2Api: {
    listApprovedProducts,
    listPackages,
    createPackage,
    updatePackage,
    generatePackage,
    packageAction: vi.fn(),
  },
  contentGenerationError,
}));
vi.mock("../api/client", () => ({
  errorMessage: (error: unknown) => String(error),
}));
vi.mock("element-plus", () => ({
  ElMessage: { success: messageSuccess },
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
  app.component(
    "el-alert",
    defineComponent({
      props: ["title"],
      template: '<div class="alert">{{ title }}</div>',
    }),
  );
  app.component(
    "el-tab-pane",
    defineComponent({
      props: ["label", "name"],
      inject: ["activateTab"],
      template:
        '<section><button type="button" class="tab-trigger" @click="activateTab(name)">{{ label }}</button><slot /></section>',
    }),
  );
  app.component("el-tabs", defineComponent({
    props: ["modelValue"],
    emits: ["update:modelValue"],
    provide() {
      return {
        activateTab: (name: string) => this.$emit("update:modelValue", name),
      };
    },
    template: "<div><slot /></div>",
  }));
  app.component("el-tag", defineComponent({ template: "<div><slot /></div>" }));
  app.component(
    "el-input",
    defineComponent({
      props: ["modelValue", "disabled"],
      emits: ["update:modelValue", "blur"],
      methods: {
        input(event: Event) {
          this.$emit(
            "update:modelValue",
            (event.target as HTMLTextAreaElement).value,
          );
        },
      },
      template:
        '<textarea :value="modelValue" :disabled="disabled" @input="input" @blur="$emit(\'blur\')" />',
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

const completePackage = {
  id: 40,
  product_id: 3,
  fact_version: "product-3:v1",
  input_summary: "approved facts",
  title: "完整标题",
  selling_points: "完整卖点",
  detail: "完整详情",
  parameters: "完整参数",
  faq: "Q：问题\nA：回答",
  presale_script: "完整售前话术",
  promotion_material: "完整推广素材",
  version: 7,
  status: "draft",
  provider: "qwen",
  model_name: "qwen-plus",
  task_status: "completed",
  updated_at: "2026-08-03T10:00:00Z",
};

function textareaValues(host: HTMLElement) {
  return Array.from(host.querySelectorAll("textarea"), (item) => item.value);
}

function generationButton(host: HTMLElement) {
  return Array.from(host.querySelectorAll("button")).find(
    (button) => button.textContent?.trim() === "生成",
  ) as HTMLButtonElement;
}

function textareaAt(host: HTMLElement, index = 0) {
  return host.querySelectorAll("textarea")[index] as HTMLTextAreaElement;
}

async function editTextarea(
  host: HTMLElement,
  value: string,
  index = 0,
) {
  const textarea = textareaAt(host, index);
  textarea.value = value;
  textarea.dispatchEvent(new Event("input", { bubbles: true }));
  await nextTick();
  return textarea;
}

async function blurTextarea(textarea: HTMLTextAreaElement) {
  textarea.dispatchEvent(new Event("blur"));
  await flushUi();
}

async function switchEveryTab(host: HTMLElement) {
  const labels = [
    "标题",
    "卖点",
    "详情",
    "参数说明",
    "FAQ",
    "售前话术",
    "图文推广素材",
  ];
  for (const [index, label] of labels.entries()) {
    const textarea = textareaAt(host, index);
    const trigger = Array.from(
      host.querySelectorAll<HTMLButtonElement>(".tab-trigger"),
    ).find((button) => button.textContent?.trim() === label)!;
    textarea.focus();
    trigger.focus();
    trigger.click();
    await flushUi();
  }
}

describe("ContentWorkspace real product selection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updatePackage.mockReset();
    generatePackage.mockReset();
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
    updatePackage.mockImplementation(
      async (_id: number, payload: Record<string, string>) => ({
        ...completePackage,
        ...payload,
        version: 8,
        provider: "manual",
        model_name: undefined,
      }),
    );
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

  it("keeps an incomplete historical version loadable", async () => {
    const host = await mountView();

    expect(textareaValues(host)).toEqual(["", "", "", "", "", "", ""]);
    expect(generatePackage).not.toHaveBeenCalled();
  });

  it("fills all seven tabs and shows success only for a complete response", async () => {
    generatePackage.mockResolvedValue({ ...completePackage });
    const host = await mountView();

    generationButton(host).click();
    await flushUi();

    expect(generatePackage).toHaveBeenCalledTimes(1);
    expect(generatePackage).toHaveBeenCalledWith(40);
    expect(messageSuccess).toHaveBeenCalledOnce();
    expect(messageSuccess).toHaveBeenCalledWith("内容生成任务已完成");
    expect(host.textContent).toContain("标题");
    expect(host.textContent).toContain("卖点");
    expect(host.textContent).toContain("详情");
    expect(host.textContent).toContain("参数说明");
    expect(host.textContent).toContain("FAQ");
    expect(host.textContent).toContain("售前话术");
    expect(host.textContent).toContain("图文推广素材");
    expect(textareaValues(host)).toEqual([
      completePackage.title,
      completePackage.selling_points,
      completePackage.detail,
      completePackage.parameters,
      completePackage.faq,
      completePackage.presale_script,
      completePackage.promotion_material,
    ]);
  });

  it.each([
    ["no_key", "文本生成服务未配置"],
    ["timeout", "内容生成超时"],
    ["failed", "内容生成失败"],
    ["field_missing", "内容生成结果字段不完整"],
  ])("shows %s as failure without success or retry", async (taskStatus, expected) => {
    generatePackage.mockResolvedValue({
      ...completePackage,
      task_status: taskStatus,
      error_summary: "安全失败摘要",
    });
    const host = await mountView();

    generationButton(host).click();
    await flushUi();
    await flushUi();

    expect(generatePackage).toHaveBeenCalledTimes(1);
    expect(messageSuccess).not.toHaveBeenCalled();
    expect(host.textContent).toContain(expected);
  });

  it("rejects completed generation when any displayed field is incomplete", async () => {
    generatePackage.mockResolvedValue({
      ...completePackage,
      promotion_material: " ",
    });
    const host = await mountView();

    generationButton(host).click();
    await flushUi();

    expect(generatePackage).toHaveBeenCalledTimes(1);
    expect(messageSuccess).not.toHaveBeenCalled();
    expect(host.textContent).toContain("内容生成结果字段不完整");
  });

  it("restores all seven fields from the latest version after remount", async () => {
    listPackages.mockResolvedValue([{ ...completePackage }]);

    const first = await mountView();
    expect(textareaValues(first)).toEqual([
      completePackage.title,
      completePackage.selling_points,
      completePackage.detail,
      completePackage.parameters,
      completePackage.faq,
      completePackage.presale_script,
      completePackage.promotion_material,
    ]);
    mountedApps.pop()?.unmount();
    first.remove();

    const refreshed = await mountView();
    expect(listPackages).toHaveBeenCalledTimes(2);
    expect(textareaValues(refreshed)).toEqual([
      completePackage.title,
      completePackage.selling_points,
      completePackage.detail,
      completePackage.parameters,
      completePackage.faq,
      completePackage.presale_script,
      completePackage.promotion_material,
    ]);
    expect(generatePackage).not.toHaveBeenCalled();
  });

  it("does not save a complete v7 while switching all seven tabs", async () => {
    listPackages.mockResolvedValue([{ ...completePackage }]);
    const host = await mountView();

    await switchEveryTab(host);

    expect(updatePackage).not.toHaveBeenCalled();
  });

  it("does not save an unchanged textarea on blur", async () => {
    listPackages.mockResolvedValue([{ ...completePackage }]);
    const host = await mountView();

    await blurTextarea(textareaAt(host));

    expect(updatePackage).not.toHaveBeenCalled();
  });

  it("saves one changed field exactly once", async () => {
    listPackages.mockResolvedValue([{ ...completePackage }]);
    const host = await mountView();

    const textarea = await editTextarea(host, "修改后的标题");
    await blurTextarea(textarea);

    expect(updatePackage).toHaveBeenCalledTimes(1);
    expect(updatePackage).toHaveBeenCalledWith(40, {
      title: "修改后的标题",
      selling_points: completePackage.selling_points,
      detail: completePackage.detail,
      parameters: completePackage.parameters,
      faq: completePackage.faq,
      presale_script: completePackage.presale_script,
      promotion_material: completePackage.promotion_material,
    });
  });

  it("does not save again after a successful save establishes a new baseline", async () => {
    listPackages.mockResolvedValue([{ ...completePackage }]);
    const host = await mountView();

    const textarea = await editTextarea(host, "修改后的标题");
    await blurTextarea(textarea);
    await blurTextarea(textareaAt(host));

    expect(updatePackage).toHaveBeenCalledTimes(1);
  });

  it("does not save generated content while switching tabs", async () => {
    listPackages.mockResolvedValue([{ ...completePackage, version: 6 }]);
    generatePackage.mockResolvedValue({ ...completePackage });
    const host = await mountView();

    generationButton(host).click();
    await flushUi();
    await switchEveryTab(host);

    expect(updatePackage).not.toHaveBeenCalled();
  });

  it("locks concurrent blur saves to one in-flight patch", async () => {
    listPackages.mockResolvedValue([{ ...completePackage }]);
    let finishSave!: (value: typeof completePackage) => void;
    updatePackage.mockReturnValueOnce(
      new Promise((resolve) => {
        finishSave = resolve;
      }),
    );
    const host = await mountView();
    const textarea = await editTextarea(host, "并发修改标题");

    textarea.dispatchEvent(new Event("blur"));
    textarea.dispatchEvent(new Event("blur"));
    textarea.dispatchEvent(new Event("blur"));
    await nextTick();

    expect(updatePackage).toHaveBeenCalledTimes(1);
    finishSave({ ...completePackage, title: "并发修改标题", version: 8 });
    await flushUi();
  });

  it("keeps an unsaved edit and reports an error without retrying", async () => {
    listPackages.mockResolvedValue([{ ...completePackage }]);
    updatePackage.mockRejectedValueOnce(new Error("安全保存失败"));
    const host = await mountView();

    const textarea = await editTextarea(host, "尚未保存的标题");
    await blurTextarea(textarea);
    await flushUi();

    expect(updatePackage).toHaveBeenCalledTimes(1);
    expect(textareaAt(host).value).toBe("尚未保存的标题");
    expect(host.textContent).toContain("安全保存失败");
  });

  it("does not save approved content on blur", async () => {
    listPackages.mockResolvedValue([
      { ...completePackage, status: "approved" },
    ]);
    const host = await mountView();

    await blurTextarea(textareaAt(host));

    expect(updatePackage).not.toHaveBeenCalled();
  });

  it("does not save an incomplete historical version while switching tabs", async () => {
    listPackages.mockResolvedValue([
      {
        ...completePackage,
        selling_points: undefined,
        faq: 42,
        promotion_material: null,
      },
    ]);
    const host = await mountView();

    expect(textareaValues(host)).toEqual([
      completePackage.title,
      "",
      completePackage.detail,
      completePackage.parameters,
      "",
      completePackage.presale_script,
      "",
    ]);
    await switchEveryTab(host);

    expect(updatePackage).not.toHaveBeenCalled();
  });

  it("never generates content merely by switching tabs", async () => {
    listPackages.mockResolvedValue([{ ...completePackage }]);
    const host = await mountView();

    await switchEveryTab(host);

    expect(generatePackage).not.toHaveBeenCalled();
  });
});
