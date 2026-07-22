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
});
