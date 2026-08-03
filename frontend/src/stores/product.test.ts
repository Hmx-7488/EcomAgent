import { describe, it, expect, beforeEach, vi } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { useProductStore } from "./product";

// Mock axios
vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

import apiClient from "../api/client";

describe("useProductStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("initializes with empty state", () => {
    const store = useProductStore();
    expect(store.products).toEqual([]);
    expect(store.total).toBe(0);
    expect(store.loading).toBe(false);
  });

  it("fetchProducts populates products array", async () => {
    const mockData = {
      data: {
        items: [
          {
            id: 1,
            name: "测试商品",
            category: "服装",
            skus: [],
            status: "active",
            created_at: "2026-01-01",
            updated_at: "2026-01-01",
          },
        ],
        total: 1,
      },
    };
    vi.mocked(apiClient.get).mockResolvedValueOnce(mockData);

    const store = useProductStore();
    await store.fetchProducts();

    expect(store.products.length).toBe(1);
    expect(store.products[0].name).toBe("测试商品");
    expect(store.total).toBe(1);
  });

  it("deleteProduct calls DELETE endpoint", async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({});

    const store = useProductStore();
    await store.deleteProduct(1);

    expect(apiClient.delete).toHaveBeenCalledWith("/products/1");
  });

  it("createProduct calls POST with payload", async () => {
    const payload = {
      name: "新品",
      category: "数码",
      skus: [{ sku_name: "默认", price: 99 }],
    };
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { id: 5, ...payload, skus: [], status: "active" },
    });

    const store = useProductStore();
    const result = await store.createProduct(payload);

    expect(apiClient.post).toHaveBeenCalledWith("/products", payload);
    expect(result.id).toBe(5);
    expect(result.name).toBe("新品");
  });

  it("saves the six formal cost fields through POST", async () => {
    const payload = {
      purchase_cost: 30,
      packaging_cost: 2,
      shipping_subsidy: 5,
      platform_fee: 4,
      marketing_allocation: 3,
      after_sales_loss: 1,
    };
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        sku_id: 31,
        ...payload,
        completeness: [],
        status: "ready",
      },
    });

    const store = useProductStore();
    const result = await store.saveCosts(31, payload);

    expect(apiClient.post).toHaveBeenCalledWith("/skus/31/costs", payload);
    expect(apiClient.put).not.toHaveBeenCalledWith(
      "/skus/31/costs",
      expect.anything(),
    );
    expect(result.marketing_allocation).toBe(3);
    expect(result).not.toHaveProperty("promotion_allocation");
  });

  it("reads persisted costs together with the backend margin facts", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        sku_id: 31,
        sale_price: 100,
        costs: {
          sku_id: 31,
          purchase_cost: 30,
          packaging_cost: 2,
          shipping_subsidy: 5,
          platform_fee: 4,
          marketing_allocation: 3,
          after_sales_loss: 1,
          completeness: [],
          status: "ready",
        },
        total_cost: 45,
        estimated_gross_profit: 55,
        estimated_gross_margin_rate: 0.55,
        status: "ready",
      },
    });

    const result = await useProductStore().getMargin(31);

    expect(apiClient.get).toHaveBeenCalledWith("/skus/31/margin");
    expect(result.costs.marketing_allocation).toBe(3);
    expect(result.status).toBe("ready");
  });
});
