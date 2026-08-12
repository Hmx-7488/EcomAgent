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

  it("loads the active category dictionary from the formal endpoint", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        items: [
          { id: 2, name: "居家收纳", is_active: true },
          { id: 5, name: "旅行收纳", is_active: true },
        ],
        total: 2,
      },
    });

    const store = useProductStore();
    const result = await store.listCategories();

    expect(apiClient.get).toHaveBeenCalledWith("/product-categories");
    expect(result).toEqual(store.categories);
    expect(store.categories.map((item) => item.name)).toEqual([
      "居家收纳",
      "旅行收纳",
    ]);
    expect(store.categoryTotal).toBe(2);
  });

  it("creates one category and adds it to the selectable dictionary", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { id: 8, name: "桌面收纳", is_active: true },
    });

    const store = useProductStore();
    const result = await store.createCategory("  桌面收纳  ");

    expect(apiClient.post).toHaveBeenCalledWith("/product-categories", {
      name: "  桌面收纳  ",
    });
    expect(result.name).toBe("桌面收纳");
    expect(store.categories).toEqual([result]);
    expect(store.categoryTotal).toBe(1);
  });

  it("creates a SKU through the selected product's formal endpoint", async () => {
    const payload = {
      sku_name: "加大款",
      spec: "60 × 40 cm",
      price: 0,
    };
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        id: 91,
        product_id: 47,
        ...payload,
        status: "active",
      },
    });

    const result = await useProductStore().createSku(47, payload);

    expect(apiClient.post).toHaveBeenCalledTimes(1);
    expect(apiClient.post).toHaveBeenCalledWith("/products/47/skus", payload);
    expect(result).toMatchObject({ id: 91, product_id: 47, price: 0 });
  });

  it("updates only the editable SKU facts through PUT", async () => {
    const payload = {
      sku_name: "升级款",
      spec: "带盖",
      price: 128,
    };
    vi.mocked(apiClient.put).mockResolvedValueOnce({
      data: {
        id: 31,
        product_id: 3,
        ...payload,
        color: "米白",
        status: "active",
      },
    });

    const result = await useProductStore().updateSku(31, payload);

    expect(apiClient.put).toHaveBeenCalledTimes(1);
    expect(apiClient.put).toHaveBeenCalledWith("/products/skus/31", payload);
    expect(result).toMatchObject({ id: 31, sku_name: "升级款", price: 128 });
  });
});
