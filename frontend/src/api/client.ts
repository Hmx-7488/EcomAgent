import axios, { type AxiosRequestConfig } from "axios";

/**
 * Mock data is a development-only aid. Production bundles always use the
 * same-origin /api contract, even if VITE_USE_MOCK is accidentally set.
 */
export function resolveMockMode(isDevelopment: boolean, configuredValue?: string) {
  return isDevelopment && configuredValue !== "false";
}
export const usingMock = resolveMockMode(import.meta.env.DEV, import.meta.env.VITE_USE_MOCK);
export const API_BASE_URL = "/api";
export const AUTH_LOGIN_PATH = "/auth/login";
export const AUTH_LOGIN_URL = API_BASE_URL + AUTH_LOGIN_PATH;

type MockProduct = Record<string, unknown> & { id: number; skus: Array<Record<string, unknown>> };
const products: MockProduct[] = [
  {
    id: 1, name: "可视折叠衣物收纳箱", category: "居家收纳", brand: "栖纳家居", status: "approved",
    description: "用于衣物分类收纳的 Demo 商品。", selling_points: "透明可视窗；双向拉链", created_at: "2026-07-21", updated_at: "2026-07-21",
    skus: [{ id: 11, sku_name: "大号 100L", spec: "60×45×37cm", price: 79.9, costs: { purchase_cost: 30, packaging_cost: 2, shipping_subsidy: 5, platform_fee: 4, marketing_allocation: 3, after_sales_loss: 1 } }],
  },
];

function response(config: AxiosRequestConfig, data: unknown, status = 200) {
  return Promise.resolve({ data, status, statusText: "OK", headers: {}, config });
}
function mockError(config: AxiosRequestConfig, status: number, code: string, message: string) {
  return Promise.reject({ config, response: { status, data: { detail: { code, message } } }, message });
}
function margin(sku: Record<string, unknown>) {
  const price = Number(sku.price);
  const costs = (sku.costs || {}) as Record<string, unknown>;
  const fields = ["purchase_cost", "packaging_cost", "shipping_subsidy", "platform_fee", "marketing_allocation", "after_sales_loss"];
  if (!Number.isFinite(price) || price <= 0 || fields.some((key) => costs[key] === null || costs[key] === undefined || costs[key] === "")) {
    return { status: "pending_confirmation", estimated_gross_profit: null, estimated_gross_margin_rate: null };
  }
  const total = fields.reduce((sum, key) => sum + Number(costs[key]), 0);
  return { status: "ready", estimated_gross_profit: +(price - total).toFixed(2), estimated_gross_margin_rate: +((price - total) / price).toFixed(4), total_cost: +total.toFixed(2) };
}
async function mockAdapter(config: AxiosRequestConfig) {
  const url = config.url || "";
  const method = (config.method || "get").toLowerCase();
  const body = typeof config.data === "string" ? JSON.parse(config.data) : (config.data || {});
  if (url === "/auth/login" && method === "post") {
    const username = String(body.username || "");
    const roles: Record<string, string> = { admin: "admin", operator_content: "operator_content", customer_service: "customer_service" };
    if (!roles[username]) return mockError(config, 401, "AUTH_INVALID", "用户名或密码错误");
    return response(config, { access_token: `mock-${username}`, user: { id: username, username, role: roles[username] } });
  }
  if (url === "/products" && method === "get") return response(config, { items: products, total: products.length });
  if (url === "/products" && method === "post") {
    const product = { ...body, id: Date.now(), status: "active", created_at: new Date().toISOString(), updated_at: new Date().toISOString(), skus: body.skus || [] } as MockProduct;
    products.push(product); return response(config, product, 201);
  }
  const productMatch = url.match(/^\/products\/(\d+)$/);
  if (productMatch) {
    const product = products.find((item) => item.id === Number(productMatch[1]));
    if (!product) return mockError(config, 404, "PRODUCT_NOT_FOUND", "商品不存在");
    if (method === "get") return response(config, product);
    if (method === "put") { Object.assign(product, body, { updated_at: new Date().toISOString() }); return response(config, product); }
    if (method === "delete") { products.splice(products.indexOf(product), 1); return response(config, null, 204); }
  }
  const skuMatch = url.match(/^\/skus\/(\d+)\/(costs|margin)$/);
  if (skuMatch) {
    const sku = products.flatMap((item) => item.skus).find((item) => Number(item.id) === Number(skuMatch[1]));
    if (!sku) return mockError(config, 404, "SKU_NOT_FOUND", "SKU 不存在");
    if (skuMatch[2] === "costs" && method === "post") {
      sku.costs = body;
      return response(config, {
        sku_id: Number(skuMatch[1]),
        ...sku.costs as Record<string, unknown>,
        completeness: [],
        status: "ready",
      });
    }
    if (skuMatch[2] === "margin" && method === "get") {
      const result = margin(sku);
      return response(config, {
        sku_id: Number(skuMatch[1]),
        sale_price: Number(sku.price),
        costs: {
          sku_id: Number(skuMatch[1]),
          ...sku.costs as Record<string, unknown>,
          completeness: [],
          status: result.status,
        },
        ...result,
      });
    }
  }
  return mockError(config, 404, "API_NOT_AVAILABLE", "Mock 中未实现此接口");
}

export function createApiClient(useMock = usingMock) {
  return axios.create({
    baseURL: API_BASE_URL,
    timeout: 30000,
    headers: { "Content-Type": "application/json" },
    adapter: useMock ? (mockAdapter as never) : undefined,
  });
}

const apiClient = createApiClient();

export function shouldAttachStaffAuthorization(url?: string) { return !url?.startsWith("/customer/"); }

apiClient.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("ecomagent_token");
  if (token && shouldAttachStaffAuthorization(config.url)) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
apiClient.interceptors.response.use((res) => res, (error) => Promise.reject(error));

export function errorMessage(error: unknown) {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === "object" && detail && "message" in detail) return String((detail as { message: unknown }).message);
  return typeof detail === "string" ? detail : "请求失败，请稍后重试";
}
export default apiClient;
