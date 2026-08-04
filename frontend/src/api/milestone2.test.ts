import { beforeEach, describe, expect, it, vi } from "vitest";

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }));

vi.mock("./client", () => ({
  default: { request: requestMock },
  usingMock: false,
}));

import { m2Api, parseResultAssetIds } from "./milestone2";

const completePayload = {
  title: "完整标题",
  selling_points: "完整卖点",
  detail: "完整详情",
  parameters: "完整参数",
  faq: "Q：问题\nA：回答",
  sales_script: "完整售前话术",
  promo_material: "完整推广素材",
};

function contentPackageResponse(
  taskStatus = "completed",
  payload: Record<string, unknown> = completePayload,
) {
  return {
    id: 51,
    product_id: 5,
    source_fact_version: "product-5:v1",
    source_summary: "approved facts",
    status: "draft",
    current_version_no: 7,
    updated_at: "2026-08-03T10:00:00Z",
    versions: [
      {
        version_no: 7,
        payload,
        provider: "qwen",
        model_name: "qwen-plus",
        task_status: taskStatus,
        error_summary:
          taskStatus === "completed" ? undefined : "安全失败摘要",
        created_at: "2026-08-03T10:00:00Z",
      },
    ],
  };
}

async function generationError(item: unknown) {
  const contract = (await import("./milestone2")) as unknown as {
    contentGenerationError: (value: unknown) => string | undefined;
  };
  return contract.contentGenerationError(item);
}

function apiResponse(data: unknown) {
  return Promise.resolve({ data });
}

describe("M2 real backend contract", () => {
  beforeEach(() => {
    requestMock.mockReset();
  });

  it("loads approved products and creates a package with the selected non-1 product id", async () => {
    requestMock
      .mockImplementationOnce(() =>
        apiResponse({
          items: [
            { id: 3, name: "栖纳收纳箱", status: "approved" },
            { id: 5, name: "栖纳真空袋", status: "approved" },
          ],
          total: 2,
        }),
      )
      .mockImplementationOnce(() =>
        apiResponse({
          id: 41,
          product_id: 5,
          source_fact_version: "product-5:v1",
          source_summary: "approved facts",
          status: "draft",
          current_version_no: 1,
          updated_at: "2026-07-31T10:00:00Z",
          versions: [],
        }),
      );

    const products = await m2Api.listApprovedProducts();
    const created = await m2Api.createPackage(products[1].id);

    expect(products.map((item) => item.id)).toEqual([3, 5]);
    expect(created.product_id).toBe(5);
    expect(created).not.toHaveProperty("product_name");
    expect(requestMock).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        method: "get",
        url: "/products",
        params: { page: 1, page_size: 100, status: "approved" },
      }),
    );
    expect(requestMock).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        method: "post",
        url: "/content/packages",
        data: { product_id: 5, payload: {} },
      }),
    );
  });

  it("uses AssetRead and ImageGenerateRequest without mock-only fields", async () => {
    const reference = {
      id: 13,
      product_id: 4,
      asset_type: "reference",
      source_type: "upload",
      url: "/uploads/reference.png",
      width: 1254,
      height: 1254,
      metadata_json: null,
      confirmed_by_id: null,
      confirmed_at: null,
      created_at: "2026-07-31T10:00:00Z",
    };
    requestMock
      .mockImplementationOnce(() => apiResponse(reference))
      .mockImplementationOnce(() =>
        apiResponse({ task_id: 22, status: "pending" }),
      );

    const uploaded = await m2Api.uploadReference(
      4,
      new File(["reference"], "reference.png", { type: "image/png" }),
    );
    const task = await m2Api.createTask(4, uploaded.id, "home");

    expect(uploaded.id).toBe(13);
    expect(uploaded).not.toHaveProperty("reference_name");
    expect(task).toEqual({ task_id: 22, status: "pending" });
    expect(requestMock).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        method: "post",
        url: "/images/tasks",
        data: {
          product_id: 4,
          reference_asset_id: 13,
          style: "home",
        },
      }),
    );
    const serialized = JSON.stringify(requestMock.mock.calls[1][0]);
    expect(serialized).not.toContain("reference_name");
    expect(serialized).not.toContain("product_name");
    expect(serialized).not.toContain("result_url");
  });

  it("maps every valid result asset id and rejects malformed task data safely", () => {
    expect(parseResultAssetIds("[10,11,12]")).toEqual([10, 11, 12]);
    expect(parseResultAssetIds("[12, 12, 13]")).toEqual([12, 13]);
    expect(parseResultAssetIds(null)).toEqual([]);
    expect(parseResultAssetIds("not-json")).toEqual([]);
    expect(parseResultAssetIds('{"id":10}')).toEqual([]);
    expect(parseResultAssetIds('[10,"11",-2,null]')).toEqual([10]);
  });

  it("loads formal AssetRead records for task result mapping", async () => {
    requestMock.mockImplementationOnce(() =>
      apiResponse({
        items: [
          { id: 10, product_id: 3, asset_type: "generated", url: "/uploads/10.png" },
          { id: 11, product_id: 3, asset_type: "generated", url: "/uploads/11.png" },
          { id: 12, product_id: 3, asset_type: "generated", url: "/uploads/12.png" },
        ],
        total: 3,
      }),
    );

    const assets = await m2Api.listAssets(3);

    expect(assets.map((item) => item.id)).toEqual([10, 11, 12]);
    expect(requestMock).toHaveBeenCalledWith(
      expect.objectContaining({
        method: "get",
        url: "/images/assets/3",
      }),
    );
  });

  it("sends one explicit complete-package generation request and maps all seven fields", async () => {
    requestMock.mockImplementationOnce(() =>
      apiResponse(
        contentPackageResponse("completed", {
          ...completePayload,
          short_title: "must be ignored",
          product_name: "must be ignored",
        }),
      ),
    );

    const generated = await m2Api.generatePackage(51);

    expect(requestMock).toHaveBeenCalledTimes(1);
    expect(requestMock).toHaveBeenCalledWith(
      expect.objectContaining({
        method: "post",
        url: "/content/packages/51/generate",
        data: {
          package_id: 51,
          content_type: "package",
          platform: "general",
        },
      }),
    );
    expect(generated).toMatchObject({
      title: completePayload.title,
      selling_points: completePayload.selling_points,
      detail: completePayload.detail,
      parameters: completePayload.parameters,
      faq: completePayload.faq,
      presale_script: completePayload.sales_script,
      promotion_material: completePayload.promo_material,
      task_status: "completed",
    });
    expect(generated).not.toHaveProperty("short_title");
    expect(generated).not.toHaveProperty("product_name");
  });

  it("keeps historical incomplete versions loadable with empty display fields", async () => {
    requestMock.mockImplementationOnce(() =>
      apiResponse({
        items: [contentPackageResponse("completed", { title: "历史标题" })],
      }),
    );

    const [historical] = await m2Api.listPackages();

    expect(historical.title).toBe("历史标题");
    expect(historical.selling_points).toBe("");
    expect(historical.detail).toBe("");
    expect(historical.parameters).toBe("");
    expect(historical.faq).toBe("");
    expect(historical.presale_script).toBe("");
    expect(historical.promotion_material).toBe("");
  });

  it.each(["no_key", "timeout", "failed", "field_missing"])(
    "does not classify %s as a successful generation",
    async (taskStatus) => {
      requestMock.mockImplementationOnce(() =>
        apiResponse(contentPackageResponse(taskStatus)),
      );

      const generated = await m2Api.generatePackage(51);

      expect(await generationError(generated)).toBeTruthy();
      expect(requestMock).toHaveBeenCalledTimes(1);
    },
  );

  it("does not classify completed content with a missing field as successful", async () => {
    const incomplete = { ...completePayload };
    delete (incomplete as Partial<typeof completePayload>).promo_material;
    requestMock.mockImplementationOnce(() =>
      apiResponse(contentPackageResponse("completed", incomplete)),
    );

    const generated = await m2Api.generatePackage(51);

    expect(await generationError(generated)).toContain("不完整");
    expect(requestMock).toHaveBeenCalledTimes(1);
  });
});
