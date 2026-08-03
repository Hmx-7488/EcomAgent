import apiClient, { usingMock } from "./client";

export type ApprovalStatus = "draft" | "submitted" | "approved" | "rejected";
export type ImageTaskStatus =
  | "pending"
  | "processing"
  | "completed"
  | "no_key"
  | "timeout"
  | "failed"
  | "field_missing";
export type ProductOption = {
  id: number;
  name: string;
  status: string;
};
export type ContentPackage = {
  id: number;
  product_id: number;
  fact_version: string;
  input_summary: string;
  title: string;
  selling_points: string;
  detail: string;
  parameters: string;
  faq: string;
  presale_script: string;
  promotion_material: string;
  version: number;
  status: ApprovalStatus;
  rejection_reason?: string;
  provider?: string;
  model_name?: string;
  task_status?: string;
  error_summary?: string;
  updated_at: string;
};
export type AssetRead = {
  id: number;
  product_id: number;
  asset_type: string;
  source_type?: string | null;
  url: string;
  width?: number | null;
  height?: number | null;
  metadata_json?: string | null;
  confirmed_by_id?: number | null;
  confirmed_at?: string | null;
  created_at?: string;
};
export type ImageTask = {
  id: number;
  product_id: number;
  source_asset_id?: number | null;
  status: ImageTaskStatus;
  style: string;
  model_name?: string | null;
  prompt?: string | null;
  result_asset_ids?: string | null;
  error_message?: string | null;
  provider?: string | null;
  retry_count: number;
  approval_status: ApprovalStatus;
  rejection_reason?: string | null;
  confirmed_by_id?: number | null;
  confirmed_at?: string | null;
  created_at: string;
  updated_at: string;
};
export type ImageTaskCreateResponse = {
  task_id: number;
  status: ImageTaskStatus;
};
export type AuditEvent = {
  id: number;
  action: string;
  target: string;
  actor: string;
  at: string;
  summary: string;
};

let nextId = 20;
const now = () =>
  new Date().toLocaleString("zh-CN", {
    hour12: false,
  });
const mockProducts: ProductOption[] = [
  { id: 1, name: "可视折叠衣物收纳箱", status: "approved" },
];
const packages: ContentPackage[] = [
  {
    id: 1,
    product_id: 1,
    fact_version: "product-1:v3",
    input_summary: "已批准商品、SKU规格、规则与素材事实",
    title: "可视折叠收纳箱",
    selling_points: "可视窗口；双向拉链；可折叠",
    detail: "用于衣物分类收纳的商品详情文案。",
    parameters: "100L · 60×45×37cm",
    faq: "Q：可以折叠吗？A：可以。",
    presale_script: "您好，可根据收纳空间选择规格。",
    promotion_material: "主图文案：收纳一目了然",
    version: 1,
    status: "draft",
    provider: "mock",
    model_name: "mock-content",
    task_status: "completed",
    updated_at: now(),
  },
];
const assets: AssetRead[] = [
  {
    id: 1,
    product_id: 1,
    asset_type: "reference",
    source_type: "upload",
    url: "/mock/reference.png",
    created_at: now(),
  },
  {
    id: 2,
    product_id: 1,
    asset_type: "generated",
    source_type: "generated",
    url: "https://placehold.co/720x720/e6efe9/17312b?text=Preview",
    created_at: now(),
  },
];
const tasks: ImageTask[] = [
  {
    id: 1,
    product_id: 1,
    source_asset_id: 1,
    style: "minimal",
    prompt: "商品展示图",
    status: "completed",
    approval_status: "draft",
    result_asset_ids: "[2]",
    retry_count: 0,
    created_at: now(),
    updated_at: now(),
  },
];
const audits: AuditEvent[] = [];
const audit = (action: string, target: string, summary: string) =>
  audits.unshift({
    id: ++nextId,
    action,
    target,
    actor: "当前登录用户",
    at: now(),
    summary,
  });
const clone = <T>(value: T): T =>
  JSON.parse(JSON.stringify(value)) as T;

async function request<T>(
  method: "get" | "post" | "patch",
  path: string,
  body?: unknown,
  params?: Record<string, unknown>,
): Promise<T> {
  const result = await apiClient.request<T>({
    method,
    url: path,
    data: body,
    params,
  });
  return result.data;
}

type ApiContentVersion = {
  version_no: number;
  payload: Record<string, string>;
  provider: string;
  model_name?: string;
  task_status: string;
  error_summary?: string;
  created_at: string;
};
type ApiContentPackage = {
  id: number;
  product_id: number;
  source_fact_version: string;
  source_summary: string;
  status: ApprovalStatus;
  current_version_no: number;
  updated_at: string;
  versions: ApiContentVersion[];
};
function contentFromApi(item: ApiContentPackage): ContentPackage {
  const version = item.versions[item.versions.length - 1];
  const payload = version?.payload || {};
  return {
    id: item.id,
    product_id: item.product_id,
    fact_version: item.source_fact_version,
    input_summary: item.source_summary,
    title: payload.title || "",
    selling_points: payload.selling_points || "",
    detail: payload.detail || "",
    parameters: payload.parameters || "",
    faq: payload.faq || "",
    presale_script: payload.sales_script || "",
    promotion_material: payload.promo_material || "",
    version: item.current_version_no,
    status: item.status,
    provider: version?.provider,
    model_name: version?.model_name,
    task_status: version?.task_status,
    error_summary: version?.error_summary,
    updated_at: item.updated_at,
  };
}
function apiPayload(payload: Partial<ContentPackage>) {
  return {
    title: payload.title,
    selling_points: payload.selling_points,
    detail: payload.detail,
    parameters: payload.parameters,
    faq: payload.faq,
    sales_script: payload.presale_script,
    promo_material: payload.promotion_material,
  };
}

export function parseResultAssetIds(
  value: string | null | undefined,
): number[] {
  if (!value) return [];
  try {
    const parsed: unknown = JSON.parse(value);
    if (!Array.isArray(parsed)) return [];
    return Array.from(
      new Set(
        parsed.filter(
          (item): item is number =>
            typeof item === "number" &&
            Number.isInteger(item) &&
            item > 0,
        ),
      ),
    );
  } catch {
    return [];
  }
}

export const m2Api = {
  async listApprovedProducts(): Promise<ProductOption[]> {
    if (usingMock) return clone(mockProducts);
    const data = await request<{ items: ProductOption[]; total: number }>(
      "get",
      "/products",
      undefined,
      { page: 1, page_size: 100, status: "approved" },
    );
    return data.items;
  },
  async listPackages(): Promise<ContentPackage[]> {
    if (usingMock) return clone(packages);
    const data = await request<{ items: ApiContentPackage[] }>(
      "get",
      "/content/packages",
    );
    return data.items.map(contentFromApi);
  },
  async createPackage(productId: number): Promise<ContentPackage> {
    if (!usingMock) {
      return contentFromApi(
        await request<ApiContentPackage>("post", "/content/packages", {
          product_id: productId,
          payload: {},
        }),
      );
    }
    const item: ContentPackage = {
      ...clone(packages[0]),
      id: ++nextId,
      product_id: productId,
      version: 1,
      status: "draft",
      updated_at: now(),
    };
    packages.unshift(item);
    audit(
      "content.created",
      `content-package:${item.id}`,
      "创建内容包草稿",
    );
    return clone(item);
  },
  async generatePackage(id: number): Promise<ContentPackage> {
    if (!usingMock) {
      return contentFromApi(
        await request<ApiContentPackage>(
          "post",
          `/content/packages/${id}/generate`,
          { package_id: id },
        ),
      );
    }
    const item = packages.find((entry) => entry.id === id)!;
    item.task_status = "completed";
    item.updated_at = now();
    audit(
      "content.generated",
      `content-package:${id}`,
      "生成内容草稿并记录事实版本",
    );
    return clone(item);
  },
  async updatePackage(
    id: number,
    payload: Partial<ContentPackage>,
  ): Promise<ContentPackage> {
    if (!usingMock) {
      return contentFromApi(
        await request<ApiContentPackage>(
          "patch",
          `/content/packages/${id}`,
          { payload: apiPayload(payload) },
        ),
      );
    }
    const item = packages.find((entry) => entry.id === id)!;
    Object.assign(item, payload, { updated_at: now() });
    audit(
      "content.edited",
      `content-package:${id}`,
      "编辑内容草稿",
    );
    return clone(item);
  },
  async packageAction(
    id: number,
    action: "submit" | "approve" | "reject" | "export",
    reason?: string,
  ): Promise<ContentPackage> {
    if (!usingMock) {
      if (action === "export") {
        await request("post", `/content/packages/${id}/export`, {});
        return contentFromApi(
          await request<ApiContentPackage>(
            "get",
            `/content/packages/${id}`,
          ),
        );
      }
      return contentFromApi(
        await request<ApiContentPackage>(
          "post",
          `/content/packages/${id}/${action}`,
          reason ? { reason } : {},
        ),
      );
    }
    const item = packages.find((entry) => entry.id === id)!;
    if (action === "submit") item.status = "submitted";
    if (action === "approve") item.status = "approved";
    if (action === "reject") {
      item.status = "rejected";
      item.rejection_reason = reason;
    }
    item.updated_at = now();
    audit(
      `content.${action}`,
      `content-package:${id}`,
      reason || `${action} 内容包`,
    );
    return clone(item);
  },
  async listTasks(): Promise<ImageTask[]> {
    return usingMock
      ? clone(tasks)
      : request<ImageTask[]>("get", "/images/tasks");
  },
  async listAssets(productId: number): Promise<AssetRead[]> {
    if (usingMock) {
      return clone(
        assets.filter((asset) => asset.product_id === productId),
      );
    }
    const data = await request<{ items: AssetRead[]; total: number }>(
      "get",
      `/images/assets/${productId}`,
    );
    return data.items;
  },
  async uploadReference(
    productId: number,
    file: File,
  ): Promise<AssetRead> {
    if (!usingMock) {
      const data = new FormData();
      data.append("product_id", String(productId));
      data.append("file", file);
      return request<AssetRead>("post", "/images/reference", data);
    }
    const item: AssetRead = {
      id: ++nextId,
      product_id: productId,
      asset_type: "reference",
      source_type: "upload",
      url: URL.createObjectURL(file),
      created_at: now(),
    };
    assets.push(item);
    audit(
      "image.reference_uploaded",
      `product:${productId}`,
      "上传参考图",
    );
    return clone(item);
  },
  async createTask(
    productId: number,
    referenceAssetId: number,
    style: string,
  ): Promise<ImageTaskCreateResponse> {
    if (!usingMock) {
      return request<ImageTaskCreateResponse>("post", "/images/tasks", {
        product_id: productId,
        reference_asset_id: referenceAssetId,
        style,
      });
    }
    const item: ImageTask = {
      id: ++nextId,
      product_id: productId,
      source_asset_id: referenceAssetId,
      style,
      prompt: style,
      status: "pending",
      approval_status: "draft",
      result_asset_ids: null,
      retry_count: 0,
      created_at: now(),
      updated_at: now(),
    };
    tasks.unshift(item);
    audit(
      "image.created",
      `image-task:${item.id}`,
      "基于参考图创建图片任务",
    );
    return { task_id: item.id, status: item.status };
  },
  async taskAction(
    id: number,
    action:
      | "retry"
      | "confirm"
      | "submit"
      | "approve"
      | "reject"
      | "export",
    reason?: string,
  ): Promise<ImageTask> {
    if (!usingMock) {
      return request<ImageTask>(
        "post",
        `/images/tasks/${id}/${action}`,
        reason ? { reason } : undefined,
      );
    }
    const item = tasks.find((entry) => entry.id === id)!;
    if (action === "retry") {
      item.status = "pending";
      item.retry_count += 1;
    }
    if (action === "confirm") item.confirmed_at = now();
    if (action === "submit") item.approval_status = "submitted";
    if (action === "approve") item.approval_status = "approved";
    if (action === "reject") item.approval_status = "rejected";
    item.updated_at = now();
    audit(
      `image.${action}`,
      `image-task:${id}`,
      reason || `${action} 图片任务`,
    );
    return clone(item);
  },
  async listAudits(): Promise<AuditEvent[]> {
    return usingMock
      ? clone(audits)
      : request<AuditEvent[]>("get", "/audit-events");
  },
};
