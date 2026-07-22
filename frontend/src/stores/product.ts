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
  costs?: CostFields;
  inventory?: {
    stock_quantity: number;
    locked_quantity: number;
    safety_stock: number;
  };
}

export interface CostFields {
  purchase_cost?: number;
  packaging_cost?: number;
  shipping_subsidy?: number;
  platform_fee?: number;
  promotion_allocation?: number;
  after_sales_loss?: number;
}
export interface MarginResult { status: "ready" | "pending_confirmation"; estimated_gross_profit: number | null; estimated_gross_margin_rate: number | null; total_cost?: number; }

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

export const useProductStore = defineStore("product", () => {
  const products = ref<ProductItem[]>([]);
  const total = ref(0);
  const loading = ref(false);

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

  async function deleteProduct(id: number): Promise<void> {
    await apiClient.delete(`/products/${id}`);
  }
  async function saveCosts(skuId: number, costs: CostFields): Promise<CostFields> {
    const res = await apiClient.put(`/skus/${skuId}/costs`, costs); return res.data;
  }
  async function getMargin(skuId: number): Promise<MarginResult> {
    const res = await apiClient.get(`/skus/${skuId}/margin`); return res.data;
  }

  return {
    products,
    total,
    loading,
    fetchProducts,
    getProduct,
    createProduct,
    updateProduct,
    deleteProduct,
    saveCosts, getMargin,
  };
});
