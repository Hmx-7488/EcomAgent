import { defineStore } from "pinia";
import { ref } from "vue";
import apiClient from "../api/client";

export interface SKUItem {
  id?: number;
  product_id?: number;
  sku_name: string;
  color?: string;
  size?: string;
  spec?: string;
  price: number;
  image_url?: string;
  status?: string;
  inventory?: {
    stock_quantity: number;
    locked_quantity: number;
    safety_stock: number;
  };
}

export interface SKUMaintenanceFields {
  sku_name: string;
  spec?: string;
  price: number;
}

export interface CostFields {
  purchase_cost?: number | null;
  packaging_cost?: number | null;
  shipping_subsidy?: number | null;
  platform_fee?: number | null;
  marketing_allocation?: number | null;
  after_sales_loss?: number | null;
}
export interface CostRead extends CostFields {
  sku_id: number;
  completeness: string[];
  status: "ready" | "pending_confirmation";
}
export interface MarginResult {
  sku_id: number;
  sale_price: number;
  costs: CostRead;
  status: "ready" | "pending_confirmation";
  estimated_gross_profit: number | null;
  estimated_gross_margin_rate: number | null;
  total_cost: number | null;
}

export interface ProductItem {
  id: number;
  name: string;
  category: string;
  brand?: string;
  description?: string;
  selling_points?: string;
  parameters_json?: string;
  status: string;
  created_at: string;
  updated_at: string;
  skus: SKUItem[];
}

export interface ProductCategoryItem {
  id: number;
  name: string;
  is_active: boolean;
}

export const useProductStore = defineStore("product", () => {
  const products = ref<ProductItem[]>([]);
  const total = ref(0);
  const loading = ref(false);
  const categories = ref<ProductCategoryItem[]>([]);
  const categoryTotal = ref(0);
  const categoryLoading = ref(false);

  async function fetchProducts(page = 1, pageSize = 20) {
    loading.value = true;
    try {
      const res = await apiClient.get("/products", {
        params: { page, page_size: pageSize },
      });
      products.value = res.data.items;
      total.value = res.data.total;
    } finally {
      loading.value = false;
    }
  }

  async function getProduct(id: number): Promise<ProductItem> {
    const res = await apiClient.get(`/products/${id}`);
    return res.data;
  }

  async function listCategories(): Promise<ProductCategoryItem[]> {
    categoryLoading.value = true;
    try {
      const res = await apiClient.get("/product-categories");
      categories.value = res.data.items;
      categoryTotal.value = res.data.total;
      return categories.value;
    } finally {
      categoryLoading.value = false;
    }
  }

  async function createCategory(name: string): Promise<ProductCategoryItem> {
    const res = await apiClient.post("/product-categories", { name });
    const created = res.data as ProductCategoryItem;
    categories.value = [...categories.value, created].sort(
      (left, right) =>
        left.name.localeCompare(right.name) || left.id - right.id,
    );
    categoryTotal.value = categories.value.length;
    return created;
  }

  async function createProduct(data: {
    name: string;
    category: string;
    brand?: string;
    description?: string;
    selling_points?: string;
    parameters_json?: string;
    skus: SKUItem[];
  }): Promise<ProductItem> {
    const res = await apiClient.post("/products", data);
    return res.data;
  }

  async function updateProduct(
    id: number,
    data: Partial<ProductItem>
  ): Promise<ProductItem> {
    const res = await apiClient.put(`/products/${id}`, data);
    return res.data;
  }

  async function createSku(
    productId: number,
    data: SKUMaintenanceFields,
  ): Promise<SKUItem> {
    const res = await apiClient.post(`/products/${productId}/skus`, data);
    return res.data;
  }

  async function updateSku(
    skuId: number,
    data: SKUMaintenanceFields,
  ): Promise<SKUItem> {
    const res = await apiClient.put(`/products/skus/${skuId}`, data);
    return res.data;
  }

  async function deleteProduct(id: number): Promise<void> {
    await apiClient.delete(`/products/${id}`);
  }
  async function saveCosts(skuId: number, costs: CostFields): Promise<CostRead> {
    const res = await apiClient.post(`/skus/${skuId}/costs`, costs);
    return res.data;
  }
  async function getMargin(skuId: number): Promise<MarginResult> {
    const res = await apiClient.get(`/skus/${skuId}/margin`); return res.data;
  }

  return {
    products,
    total,
    loading,
    categories,
    categoryTotal,
    categoryLoading,
    fetchProducts,
    listCategories,
    createCategory,
    getProduct,
    createProduct,
    updateProduct,
    createSku,
    updateSku,
    deleteProduct,
    saveCosts, getMargin,
  };
});
