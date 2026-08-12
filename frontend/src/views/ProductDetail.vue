<template>
  <section>
    <div class="page-heading">
      <div>
        <el-button link @click="router.push('/products')">← 返回商品列表</el-button>
        <h1>{{ product?.name || "商品详情" }}</h1>
        <p>
          {{ product?.category }}
          <span v-if="product?.brand">· {{ product.brand }}</span>
        </p>
      </div>
      <el-button
        v-if="canEdit"
        type="primary"
        :loading="savingProduct"
        :disabled="savingProduct"
        @click="saveProduct"
      >
        保存商品信息
      </el-button>
    </div>

    <el-alert
      v-if="error"
      type="error"
      :title="error"
      :closable="false"
      show-icon
      class="notice"
    />
    <el-alert
      v-if="success"
      type="success"
      :title="success"
      :closable="false"
      show-icon
      class="notice"
    />
    <el-alert
      v-if="!canEdit"
      title="客服为只读访问：可使用已授权事实，但不能编辑商品、SKU、成本或毛利。"
      type="info"
      :closable="false"
      class="notice"
    />

    <el-skeleton v-if="loading" :rows="8" animated />
    <template v-else-if="product">
      <div class="layout">
        <div class="panel">
          <h2>商品事实</h2>
          <el-form label-position="top">
            <el-form-item label="商品名称">
              <el-input
                v-model.trim="product.name"
                aria-label="商品名称"
                :disabled="!canEdit || savingProduct"
              />
            </el-form-item>
            <el-form-item label="商品类目">
              <template v-if="canEdit">
                <div class="category-picker">
                  <el-select
                    v-model="product.category"
                    aria-label="商品类目"
                    filterable
                    :loading="categoryLoading"
                    :disabled="savingProduct || categoryLoading || categories.length === 0"
                  >
                    <el-option
                      v-for="category in categories"
                      :key="category.id"
                      :label="category.name"
                      :value="category.name"
                    />
                  </el-select>
                  <el-button v-if="isAdmin" plain @click="addCategory">
                    新增一级类目
                  </el-button>
                </div>
                <p v-if="categoryError" class="field-error">{{ categoryError }}</p>
                <p v-else-if="!categoryLoading && categories.length === 0" class="field-hint">
                  暂无可用一级类目<span v-if="isAdmin">，请先新增</span>
                </p>
              </template>
              <el-input v-else :model-value="product.category" disabled />
            </el-form-item>
            <el-form-item label="品牌">
              <el-input
                v-model.trim="product.brand"
                aria-label="品牌"
                :disabled="!canEdit || savingProduct"
              />
            </el-form-item>
            <el-form-item label="商品描述">
              <el-input
                v-model="product.description"
                aria-label="商品描述"
                type="textarea"
                :disabled="!canEdit || savingProduct"
              />
            </el-form-item>
          </el-form>
        </div>

        <div class="panel">
          <div class="sku-heading">
            <h2>SKU、成本与预估毛利</h2>
            <el-button v-if="canEdit" plain @click="showNewSku = !showNewSku">
              新增 SKU/规格
            </el-button>
          </div>
          <p class="hint">
            预估毛利额 = 实收售价 − 六项成本；任何成本缺失或零售价时，显示“毛利待确认”。
          </p>

          <div v-if="canEdit && showNewSku" class="new-sku-form">
            <h3>新增 SKU/规格</h3>
            <el-form label-position="top">
              <div class="new-sku-grid">
                <el-form-item label="SKU 名称">
                  <el-input
                    v-model="newSku.sku_name"
                    aria-label="新 SKU 名称"
                    :disabled="creatingSku"
                  />
                </el-form-item>
                <el-form-item label="规格（可选）">
                  <el-input
                    v-model="newSku.spec"
                    aria-label="新 SKU 规格"
                    :disabled="creatingSku"
                  />
                </el-form-item>
                <el-form-item label="零售价（元）">
                  <el-input-number
                    v-model="newSku.price"
                    aria-label="新 SKU 零售价"
                    :min="0"
                    :precision="2"
                    controls-position="right"
                    :disabled="creatingSku"
                  />
                </el-form-item>
              </div>
              <div class="sku-actions">
                <el-button
                  type="primary"
                  :loading="creatingSku"
                  :disabled="creatingSku"
                  @click="createNewSku"
                >
                  创建 SKU
                </el-button>
              </div>
            </el-form>
          </div>

          <el-collapse v-model="openSku">
            <el-collapse-item
              v-for="sku in product.skus"
              :key="sku.id"
              :name="String(sku.id)"
              :title="`${sku.sku_name} · 零售价 ¥${format(sku.price)}`"
            >
              <div class="sku-grid">
                <div>
                  <el-form label-position="top">
                    <el-form-item label="SKU 名称">
                      <el-input
                        v-model="sku.sku_name"
                        :aria-label="`SKU 名称 ${sku.id}`"
                        :disabled="!canEdit || savingSkuInfo === sku.id"
                      />
                    </el-form-item>
                    <el-form-item label="规格">
                      <el-input
                        v-model="sku.spec"
                        :aria-label="`SKU 规格 ${sku.id}`"
                        :disabled="!canEdit || savingSkuInfo === sku.id"
                      />
                    </el-form-item>
                    <el-form-item label="零售价（元）">
                      <el-input-number
                        v-model="sku.price"
                        :aria-label="`SKU 零售价 ${sku.id}`"
                        :min="0"
                        :precision="2"
                        controls-position="right"
                        :disabled="!canEdit || savingSkuInfo === sku.id"
                      />
                    </el-form-item>
                  </el-form>
                  <p v-if="isSkuDirty(sku)" class="unsaved-hint">SKU 信息尚未保存</p>
                  <div v-if="canEdit" class="sku-actions">
                    <el-button
                      type="primary"
                      plain
                      :loading="savingSkuInfo === sku.id"
                      :disabled="savingSkuInfo !== undefined"
                      @click="saveSkuInfo(sku)"
                    >
                      保存 SKU 信息
                    </el-button>
                  </div>
                </div>

                <div>
                  <h3>成本录入</h3>
                  <div class="cost-grid">
                    <el-form-item
                      v-for="field in fields"
                      :key="field.key"
                      :label="field.label"
                      :error="fieldError(sku, field.key)"
                    >
                      <el-input-number
                        v-model="costsFor(sku)[field.key]"
                        :min="0"
                        :precision="2"
                        placeholder="未录入"
                        controls-position="right"
                        :disabled="!canEdit || savingCostSku === sku.id"
                        @change="refreshMargin(sku)"
                      />
                    </el-form-item>
                  </div>
                  <div v-if="canEdit" class="cost-actions">
                    <el-button
                      type="primary"
                      plain
                      :loading="savingCostSku === sku.id"
                      :disabled="savingCostSku !== undefined"
                      @click="saveCosts(sku)"
                    >
                      保存成本
                    </el-button>
                  </div>
                </div>
              </div>

              <div class="margin" :class="marginFor(sku).status">
                <div>
                  <span>预估毛利状态</span>
                  <strong>{{ marginFor(sku).status === "ready" ? "已计算" : "毛利待确认" }}</strong>
                </div>
                <template v-if="marginFor(sku).status === 'ready'">
                  <div>
                    <span>预估毛利额</span>
                    <strong>¥{{ format(marginFor(sku).estimated_gross_profit) }}</strong>
                  </div>
                  <div>
                    <span>预估毛利率</span>
                    <strong>{{ percent(marginFor(sku).estimated_gross_margin_rate) }}</strong>
                  </div>
                </template>
                <p v-else>
                  请补全采购、包装、运费补贴、平台费、推广分摊和售后损失，并确认零售价大于
                  0；当前不产生任何调价结论。
                </p>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessageBox } from "element-plus";
import { useRoute, useRouter } from "vue-router";
import {
  useProductStore,
  type CostFields,
  type MarginResult,
  type ProductItem,
  type SKUMaintenanceFields,
  type SKUItem,
} from "../stores/product";
import { useAuthStore } from "../stores/auth";
import { errorMessage } from "../api/client";

type SkuSnapshot = {
  sku_name: string;
  spec: string;
  price: number;
};

const route = useRoute();
const router = useRouter();
const store = useProductStore();
const auth = useAuthStore();

const product = ref<ProductItem | null>(null);
const loading = ref(true);
const error = ref("");
const success = ref("");
const categoryError = ref("");
const savingProduct = ref(false);
const savingSkuInfo = ref<number | undefined>();
const savingCostSku = ref<number | undefined>();
const creatingSku = ref(false);
const showNewSku = ref(false);
const openSku = ref<string[]>([]);
const newSku = reactive<SKUMaintenanceFields>({
  sku_name: "",
  spec: "",
  price: 0,
});

const canEdit = computed(
  () => auth.user?.role === "admin" || auth.user?.role === "operator_content",
);
const isAdmin = computed(() => auth.user?.role === "admin");
const categories = computed(() => store.categories);
const categoryLoading = computed(() => store.categoryLoading);
const costs = reactive<Record<number, CostFields>>({});
const margins = reactive<Record<number, MarginResult>>({});
const skuSnapshots = reactive<Record<number, SkuSnapshot>>({});
const fields = [
  { key: "purchase_cost", label: "采购成本" },
  { key: "packaging_cost", label: "包装成本" },
  { key: "shipping_subsidy", label: "运费补贴" },
  { key: "platform_fee", label: "平台费" },
  { key: "marketing_allocation", label: "推广分摊" },
  { key: "after_sales_loss", label: "售后损失" },
] as const;

onMounted(async () => {
  if (canEdit.value) await loadCategories();
  try {
    product.value = await store.getProduct(Number(route.params.id));
    openSku.value = product.value.skus.map((sku) => String(sku.id));
    product.value.skus.forEach(setSkuSnapshot);
    await Promise.all(product.value.skus.map(loadCostsAndMargin));
  } catch (caught) {
    error.value = errorMessage(caught);
  } finally {
    loading.value = false;
  }
});

function clearNotices() {
  error.value = "";
  success.value = "";
}

async function loadCategories() {
  categoryError.value = "";
  try {
    await store.listCategories();
  } catch (caught) {
    categoryError.value = `类目加载失败：${errorMessage(caught)}`;
  }
}

async function addCategory() {
  if (!isAdmin.value || !product.value) return;
  categoryError.value = "";
  try {
    const { value } = await ElMessageBox.prompt("请输入新的一级类目名称", "新增一级类目", {
      confirmButtonText: "新增",
      cancelButtonText: "取消",
      inputValidator: (input) => {
        const name = input.trim();
        return name.length >= 1 && name.length <= 128
          ? true
          : "一级类目名称长度必须为 1 至 128 个字符";
      },
    });
    const created = await store.createCategory(value.trim());
    product.value.category = created.name;
  } catch (caught) {
    if (caught === "cancel" || caught === "close") return;
    categoryError.value = errorMessage(caught);
  }
}

function skuSnapshot(sku: SKUItem): SkuSnapshot {
  return {
    sku_name: typeof sku.sku_name === "string" ? sku.sku_name : "",
    spec: typeof sku.spec === "string" ? sku.spec : "",
    price: Number(sku.price),
  };
}

function setSkuSnapshot(sku: SKUItem) {
  if (sku.id === undefined) return;
  skuSnapshots[sku.id] = skuSnapshot(sku);
}

function isSkuDirty(sku: SKUItem) {
  if (sku.id === undefined || !skuSnapshots[sku.id]) return false;
  const current = skuSnapshot(sku);
  const persisted = skuSnapshots[sku.id];
  return (
    current.sku_name !== persisted.sku_name ||
    current.spec !== persisted.spec ||
    current.price !== persisted.price
  );
}

function isSkuPriceDirty(sku: SKUItem) {
  if (sku.id === undefined || !skuSnapshots[sku.id]) return false;
  return skuSnapshot(sku).price !== skuSnapshots[sku.id].price;
}

function skuValidationMessage(values: SkuSnapshot) {
  if (!values.sku_name.trim()) return "SKU 名称不能为空";
  if (!Number.isFinite(values.price) || values.price < 0) {
    return "零售价必须是大于等于 0 的有限数字";
  }
  return "";
}

function replaceSku(saved: SKUItem) {
  if (!product.value || saved.id === undefined) return;
  const index = product.value.skus.findIndex((sku) => sku.id === saved.id);
  if (index >= 0) product.value.skus.splice(index, 1, saved);
  setSkuSnapshot(saved);
}

async function saveSkuInfo(sku: SKUItem) {
  if (!canEdit.value || sku.id === undefined || savingSkuInfo.value !== undefined) return;
  if (!isSkuDirty(sku)) return;
  clearNotices();
  const request = skuSnapshot(sku);
  const validationMessage = skuValidationMessage(request);
  if (validationMessage) {
    error.value = validationMessage;
    return;
  }
  savingSkuInfo.value = sku.id;
  try {
    const saved = await store.updateSku(sku.id, request);
    replaceSku(saved);
    success.value = "SKU 信息已保存";
  } catch (caught) {
    error.value = errorMessage(caught);
  } finally {
    savingSkuInfo.value = undefined;
  }
}

function resetNewSku() {
  newSku.sku_name = "";
  newSku.spec = "";
  newSku.price = 0;
}

async function createNewSku() {
  if (!canEdit.value || !product.value || creatingSku.value) return;
  clearNotices();
  const request: SkuSnapshot = {
    sku_name: typeof newSku.sku_name === "string" ? newSku.sku_name : "",
    spec: typeof newSku.spec === "string" ? newSku.spec : "",
    price: Number(newSku.price),
  };
  const validationMessage = skuValidationMessage(request);
  if (validationMessage) {
    error.value = validationMessage;
    return;
  }
  creatingSku.value = true;
  try {
    const saved = await store.createSku(product.value.id, request);
    product.value.skus.push(saved);
    setSkuSnapshot(saved);
    if (saved.id !== undefined) {
      openSku.value = [...new Set([...openSku.value, String(saved.id)])];
    }
    resetNewSku();
    showNewSku.value = false;
    success.value = "SKU 已新增";
  } catch (caught) {
    error.value = errorMessage(caught);
  } finally {
    creatingSku.value = false;
  }
}

function costsFor(sku: SKUItem) {
  return costs[sku.id || 0] || (costs[sku.id || 0] = {});
}

function setCostFacts(skuId: number, facts: CostFields) {
  costs[skuId] = Object.fromEntries(
    fields.map((field) => [field.key, facts[field.key]]),
  ) as CostFields;
}

async function loadCostsAndMargin(sku: SKUItem) {
  if (!sku.id) return;
  const result = await store.getMargin(sku.id);
  setCostFacts(sku.id, result.costs);
  margins[sku.id] = result;
}

function localMargin(sku: SKUItem): MarginResult {
  const skuId = sku.id || 0;
  const values = fields.map((field) => costsFor(sku)[field.key]);
  const missing = fields
    .filter((_, index) => values[index] === undefined || values[index] === null)
    .map((field) => field.key);
  const costView = {
    sku_id: skuId,
    ...costsFor(sku),
    completeness: missing,
    status: missing.length ? ("pending_confirmation" as const) : ("ready" as const),
  };
  if (missing.length) {
    return {
      sku_id: skuId,
      sale_price: Number(sku.price),
      costs: costView,
      status: "pending_confirmation",
      estimated_gross_profit: null,
      estimated_gross_margin_rate: null,
      total_cost: null,
    };
  }
  const total = values.reduce<number>((sum, value) => sum + Number(value), 0);
  if (Number(sku.price) <= 0) {
    return {
      sku_id: skuId,
      sale_price: Number(sku.price),
      costs: costView,
      status: "pending_confirmation",
      estimated_gross_profit: null,
      estimated_gross_margin_rate: null,
      total_cost: total,
    };
  }
  const profit = Number(sku.price) - total;
  return {
    sku_id: skuId,
    sale_price: Number(sku.price),
    costs: costView,
    status: "ready",
    estimated_gross_profit: +profit.toFixed(2),
    estimated_gross_margin_rate: +(profit / Number(sku.price)).toFixed(4),
    total_cost: total,
  };
}

function marginFor(sku: SKUItem) {
  return margins[sku.id || 0] || localMargin(sku);
}

function refreshMargin(sku: SKUItem) {
  if (sku.id) margins[sku.id] = localMargin(sku);
}

function fieldError(sku: SKUItem, key: keyof CostFields) {
  const value = costsFor(sku)[key];
  return value !== undefined && value !== null && Number(value) < 0 ? "成本不能为负数" : "";
}

async function saveCosts(sku: SKUItem) {
  if (!sku.id || !canEdit.value || savingCostSku.value !== undefined) return;
  clearNotices();
  if (isSkuPriceDirty(sku)) {
    error.value = "请先保存 SKU 信息";
    return;
  }
  const request = Object.fromEntries(
    fields.map((field) => [field.key, costsFor(sku)[field.key]]),
  ) as CostFields;
  if (
    fields.some((field) => {
      const value = request[field.key];
      return value !== undefined && value !== null && Number(value) < 0;
    })
  ) {
    error.value = "成本不能为负数";
    return;
  }
  savingCostSku.value = sku.id;
  try {
    const saved = await store.saveCosts(sku.id, request);
    setCostFacts(sku.id, saved);
    const margin = await store.getMargin(sku.id);
    margins[sku.id] = margin;
    success.value =
      Number(sku.price) === 0
        ? "成本已保存；零售价为 0，毛利继续待确认"
        : "成本已保存";
  } catch (caught) {
    error.value = errorMessage(caught);
  } finally {
    savingCostSku.value = undefined;
  }
}

async function saveProduct() {
  if (!product.value || !canEdit.value || savingProduct.value) return;
  clearNotices();
  if (!product.value.name || !product.value.category) {
    error.value = "商品名称和类目不能为空";
    return;
  }
  const request = {
    name: product.value.name,
    category: product.value.category,
    brand: product.value.brand,
    description: product.value.description,
  };
  savingProduct.value = true;
  try {
    const saved = await store.updateProduct(product.value.id, request);
    product.value.name = saved.name;
    product.value.category = saved.category;
    product.value.brand = saved.brand;
    product.value.description = saved.description;
    product.value.updated_at = saved.updated_at;
    success.value = "商品信息已保存";
  } catch (caught) {
    error.value = errorMessage(caught);
  } finally {
    savingProduct.value = false;
  }
}

function format(value: number | null | undefined) {
  return value === null || value === undefined ? "--" : Number(value).toFixed(2);
}

function percent(value: number | null) {
  return value === null ? "--" : `${(value * 100).toFixed(2)}%`;
}
</script>

<style scoped>
.notice {
  margin-bottom: 14px;
}
.layout {
  display: grid;
  grid-template-columns: minmax(260px, 0.75fr) minmax(0, 1.5fr);
  gap: 16px;
}
.panel h2 {
  margin-top: 0;
  font-size: 16px;
}
.hint {
  font-size: 13px;
  color: #66766f;
}
.category-picker,
.sku-heading {
  display: flex;
  width: 100%;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}
.category-picker :deep(.el-select) {
  flex: 1;
}
.field-error,
.field-hint,
.unsaved-hint {
  width: 100%;
  margin: 6px 0 0;
  font-size: 12px;
}
.field-error {
  color: #c2362b;
}
.field-hint {
  color: #66766f;
}
.unsaved-hint {
  color: #9a6800;
}
.new-sku-form {
  padding: 14px;
  margin: 14px 0;
  border: 1px solid #d8e0dc;
  border-radius: 8px;
  background: #f8faf9;
}
.new-sku-form h3 {
  margin: 0 0 10px;
  font-size: 15px;
}
.new-sku-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.sku-grid {
  display: grid;
  grid-template-columns: minmax(190px, 0.7fr) minmax(300px, 1.3fr);
  gap: 24px;
}
.sku-actions,
.cost-actions {
  margin-top: 8px;
}
.cost-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 12px;
}
.margin {
  display: flex;
  gap: 28px;
  align-items: center;
  background: #e5f3ed;
  border-left: 3px solid #007d61;
  padding: 12px;
  margin-top: 16px;
}
.margin span {
  display: block;
  color: #66766f;
  font-size: 12px;
}
.margin strong {
  display: block;
  margin-top: 3px;
}
.margin.pending_confirmation {
  display: block;
  background: #fff8e8;
  border-color: #9a6800;
  color: #735000;
}
.margin p {
  margin: 8px 0 0;
}
@media (max-width: 900px) {
  .layout,
  .sku-grid,
  .new-sku-grid {
    grid-template-columns: 1fr;
  }
  .cost-grid {
    grid-template-columns: 1fr;
  }
  .margin {
    display: block;
  }
  .margin > div {
    margin: 8px 0;
  }
}
</style>
