<template>
  <div class="content-generate">
    <div class="page-header">
      <h2>内容生成</h2>
    </div>

    <el-card class="generate-card">
      <el-form :model="form" label-width="100px">
        <el-form-item label="选择商品">
          <el-select
            v-model="form.product_id"
            filterable
            placeholder="请选择商品"
            :loading="productLoading"
            @focus="loadProducts"
          >
            <el-option
              v-for="p in productOptions"
              :key="p.id"
              :label="p.name"
              :value="p.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="内容类型">
          <el-select v-model="form.content_type">
            <el-option label="商品标题" value="title" />
            <el-option label="核心卖点" value="selling_points" />
            <el-option label="详情页文案" value="description" />
            <el-option label="商品 FAQ" value="faq" />
            <el-option label="客服话术" value="script" />
            <el-option label="平台关键词" value="keywords" />
          </el-select>
        </el-form-item>

        <el-form-item label="目标平台">
          <el-select v-model="form.platform">
            <el-option label="通用" value="general" />
            <el-option label="淘宝" value="taobao" />
            <el-option label="拼多多" value="pinduoduo" />
            <el-option label="抖音" value="douyin" />
            <el-option label="小红书" value="xiaohongshu" />
          </el-select>
        </el-form-item>

        <el-form-item label="风格提示">
          <el-input
            v-model="form.style_hint"
            placeholder="可选，如：年轻化、简约、促销感"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="generating" @click="handleGenerate">
            生成内容
          </el-button>
        </el-form-item>
      </el-form>

      <el-divider v-if="result" />

      <div v-if="result" class="result-area">
        <h4>生成结果</h4>
        <el-alert
          v-if="result.content_json"
          type="success"
          :closable="false"
          show-icon
        >
          <pre class="result-json">{{ formatResult(result.content_json) }}</pre>
        </el-alert>
        <p class="result-hint">
          提示：已配置 LLM 时将调用 Qwen 生成内容；未配置时使用模板兜底。
        </p>
      </div>
    </el-card>

    <el-card v-if="history.total > 0" class="history-card">
      <template #header>生成历史</template>
      <el-table :data="history.items" stripe size="small">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="content_type" label="类型" width="100" />
        <el-table-column prop="platform" label="平台" width="100" />
        <el-table-column label="内容预览" min-width="200">
          <template #default="{ row }">
            <span class="content-preview">{{
              truncate(row.content_json, 80)
            }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="生成时间" width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { ElMessage } from "element-plus";
import apiClient from "../api/client";

interface ProductOption {
  id: number;
  name: string;
}

const productOptions = ref<ProductOption[]>([]);
const productLoading = ref(false);
const generating = ref(false);
const result = ref<{ content_json: string } | null>(null);

const form = reactive({
  product_id: null as number | null,
  content_type: "title",
  platform: "general",
  style_hint: "",
});

const history = reactive<{
  items: { id: number; content_type: string; platform: string; content_json: string; created_at: string }[];
  total: number;
}>({ items: [], total: 0 });

async function loadProducts() {
  if (productOptions.value.length > 0) return;
  productLoading.value = true;
  try {
    const res = await apiClient.get("/products", { params: { page_size: 100 } });
    productOptions.value = res.data.items;
  } finally {
    productLoading.value = false;
  }
}

async function handleGenerate() {
  if (!form.product_id) {
    ElMessage.warning("请选择商品");
    return;
  }
  generating.value = true;
  try {
    const res = await apiClient.post("/content/generate", {
      product_id: form.product_id,
      content_type: form.content_type,
      platform: form.platform,
      style_hint: form.style_hint || undefined,
    });
    result.value = { content_json: res.data.content_json };
    ElMessage.success("生成完成");
    // Refresh history
    await loadHistory();
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data
      ?.detail || "生成失败";
    ElMessage.error(msg);
  } finally {
    generating.value = false;
  }
}

async function loadHistory() {
  if (!form.product_id) return;
  try {
    const res = await apiClient.get(`/content/history/${form.product_id}`);
    history.items = res.data.items;
    history.total = res.data.total;
  } catch {
    // silent
  }
}

function formatResult(json: string): string {
  try {
    return JSON.stringify(JSON.parse(json), null, 2);
  } catch {
    return json;
  }
}

function truncate(text: string, max: number): string {
  if (!text) return "";
  return text.length > max ? text.slice(0, max) + "..." : text;
}
</script>

<style scoped>
.content-generate {
  max-width: 800px;
  margin: 0 auto;
}
.page-header {
  margin-bottom: 20px;
}
.page-header h2 {
  margin: 0;
}
.generate-card {
  margin-bottom: 20px;
}
.result-area {
  margin-top: 4px;
}
.result-area h4 {
  margin: 0 0 8px;
}
.result-json {
  white-space: pre-wrap;
  font-size: 13px;
  margin: 0;
}
.result-hint {
  color: var(--color-text-secondary);
  font-size: 12px;
  margin-top: 8px;
}
.history-card {
  margin-bottom: 20px;
}
.content-preview {
  color: var(--color-text-body);
}
</style>
