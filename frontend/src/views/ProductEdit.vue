<template>
  <section>
    <div class="page-heading">
      <div>
        <h1>新增商品</h1>
        <p>先建立商品与 SKU 事实；成本和毛利在商品详情页维护。</p>
      </div>
    </div>
    <div class="panel">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="92px">
        <el-form-item label="商品名称" prop="name">
          <el-input v-model.trim="form.name" />
        </el-form-item>
        <el-form-item label="商品类目" prop="category">
          <div class="category-picker">
            <el-select
              v-model="form.category"
              aria-label="商品类目"
              filterable
              placeholder="请选择一级类目"
              :loading="categoryLoading"
              :disabled="categoryLoading || categories.length === 0"
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
          <p
            v-else-if="!categoryLoading && categories.length === 0"
            class="field-hint"
          >
            暂无可用一级类目<span v-if="isAdmin">，请先新增</span>
          </p>
        </el-form-item>
        <el-form-item label="品牌">
          <el-input v-model.trim="form.brand" />
        </el-form-item>
        <el-form-item label="商品描述">
          <el-input v-model="form.description" type="textarea" />
        </el-form-item>
        <el-divider>SKU</el-divider>
        <div v-for="(sku, index) in form.skus" :key="index" class="sku">
          <el-row :gutter="12">
            <el-col :xs="24" :sm="8">
              <el-input v-model.trim="sku.sku_name" placeholder="SKU 名称" />
            </el-col>
            <el-col :xs="24" :sm="8">
              <el-input v-model.trim="sku.spec" placeholder="规格" />
            </el-col>
            <el-col :xs="24" :sm="6">
              <el-input-number
                v-model="sku.price"
                :min="0"
                :precision="2"
                controls-position="right"
                aria-label="零售价"
              />
              <span class="unit">元（零售价可为 0，毛利待确认）</span>
            </el-col>
            <el-col :xs="24" :sm="2">
              <el-button
                link
                type="danger"
                :disabled="form.skus.length === 1"
                @click="removeSku(index)"
              >
                移除
              </el-button>
            </el-col>
          </el-row>
        </div>
        <el-button plain @click="addSku">添加 SKU</el-button>
        <div class="actions">
          <el-button @click="router.push('/products')">取消</el-button>
          <el-button type="primary" :loading="saving" @click="save">
            创建商品
          </el-button>
        </div>
      </el-form>
      <el-alert
        v-if="error"
        class="alert"
        type="error"
        :title="error"
        :closable="false"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessageBox, type FormInstance } from "element-plus";
import { useRouter } from "vue-router";
import { useProductStore } from "../stores/product";
import { useAuthStore } from "../stores/auth";
import { errorMessage } from "../api/client";

const router = useRouter();
const store = useProductStore();
const auth = useAuthStore();
const formRef = ref<FormInstance>();
const saving = ref(false);
const error = ref("");
const categoryError = ref("");
const categories = computed(() => store.categories);
const categoryLoading = computed(() => store.categoryLoading);
const isAdmin = computed(() => auth.user?.role === "admin");
const form = reactive({
  name: "",
  category: "",
  brand: "",
  description: "",
  skus: [{ sku_name: "", spec: "", price: 0 }],
});
const rules = {
  name: [{ required: true, message: "请填写商品名称", trigger: "blur" }],
  category: [{ required: true, message: "请选择商品类目", trigger: "change" }],
};

onMounted(loadCategories);

async function loadCategories() {
  categoryError.value = "";
  try {
    await store.listCategories();
  } catch (exception) {
    categoryError.value = `类目加载失败：${errorMessage(exception)}`;
  }
}

async function addCategory() {
  if (!isAdmin.value) return;
  categoryError.value = "";
  try {
    const { value } = await ElMessageBox.prompt(
      "请输入新的一级类目名称",
      "新增一级类目",
      {
        confirmButtonText: "新增",
        cancelButtonText: "取消",
        inputValidator: (input) => {
          const name = input.trim();
          return name.length >= 1 && name.length <= 128
            ? true
            : "一级类目名称长度必须为 1 至 128 个字符";
        },
      },
    );
    const created = await store.createCategory(value.trim());
    form.category = created.name;
  } catch (exception) {
    if (exception === "cancel" || exception === "close") return;
    categoryError.value = errorMessage(exception);
  }
}

function addSku() {
  form.skus.push({ sku_name: "", spec: "", price: 0 });
}

function removeSku(index: number) {
  form.skus.splice(index, 1);
}

function invalidPrice(price: number) {
  return !Number.isFinite(Number(price)) || Number(price) < 0;
}

async function save() {
  error.value = "";
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;
  if (form.skus.some((sku) => !sku.sku_name)) {
    error.value = "每个 SKU 都需要名称";
    return;
  }
  if (form.skus.some((sku) => invalidPrice(sku.price))) {
    error.value = "SKU 零售价必须是大于或等于 0 的有限数字";
    return;
  }
  saving.value = true;
  try {
    const product = await store.createProduct({
      ...form,
      brand: form.brand || undefined,
      description: form.description || undefined,
    });
    router.push(`/products/${product.id}`);
  } catch (exception) {
    error.value = errorMessage(exception);
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.category-picker {
  display: flex;
  width: 100%;
  gap: 10px;
}
.category-picker :deep(.el-select) {
  flex: 1;
}
.field-error,
.field-hint {
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
.sku {
  padding: 12px;
  background: #f8faf8;
  border-radius: 6px;
  margin: 8px 0;
}
.unit {
  display: block;
  font-size: 12px;
  color: #66766f;
  margin-top: 4px;
}
.actions {
  margin-top: 24px;
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
.alert {
  margin-top: 16px;
}
</style>
