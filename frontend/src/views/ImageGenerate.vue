<template>
  <div class="image-generate">
    <div class="page-header">
      <h2>商品图片生成</h2>
      <span class="page-desc">上传商品图，AI 生成不同场景的背景图</span>
    </div>

    <el-card class="upload-card">
      <el-form label-width="100px">
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

        <el-form-item label="场景风格">
          <el-select v-model="form.style">
            <el-option label="居家" value="home" />
            <el-option label="户外" value="outdoor" />
            <el-option label="夏日" value="summer" />
            <el-option label="极简" value="minimal" />
            <el-option label="直播间" value="live" />
            <el-option label="节日促销" value="promotion" />
          </el-select>
        </el-form-item>

        <el-form-item label="上传图片">
          <el-upload
            :auto-upload="false"
            :limit="1"
            :on-change="handleFileChange"
            :file-list="fileList"
            list-type="picture"
            accept="image/png,image/jpeg,image/webp"
          >
            <el-button type="primary" plain>选择商品图片</el-button>
            <template #tip>
              <div class="upload-tip">支持 PNG / JPEG / WebP，不超过 10MB</div>
            </template>
          </el-upload>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="generating" @click="handleGenerate">
            生成图片
          </el-button>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="taskStatus"
        :title="statusLabel"
        :type="statusType"
        :closable="false"
        show-icon
      />
    </el-card>

    <el-card v-if="generatedAssets.length > 0" class="result-card">
      <template #header>生成结果</template>
      <el-row :gutter="16">
        <el-col v-for="asset in generatedAssets" :key="asset.id" :span="8">
          <el-card shadow="hover" class="asset-card">
            <el-image :src="asset.url" fit="cover" class="asset-image" />
            <p class="asset-style">{{ formatStyle(asset.metadata_json) }}</p>
          </el-card>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { ElMessage } from "element-plus";
import type { UploadFile, UploadRawFile } from "element-plus";
import apiClient from "../api/client";

interface ProductOption {
  id: number;
  name: string;
}

const productOptions = ref<ProductOption[]>([]);
const productLoading = ref(false);
const generating = ref(false);
const fileList = ref<UploadFile[]>([]);
const selectedFile = ref<UploadRawFile | null>(null);

const form = reactive({
  product_id: null as number | null,
  style: "minimal",
});

const taskStatus = ref<{ status: string; task_id: number } | null>(null);
const generatedAssets = ref<{ id: number; url: string; metadata_json: string }[]>([]);

const statusLabel = ref("");
const statusType = ref<"info" | "success" | "warning" | "error">("info");

let pollTimer: ReturnType<typeof setInterval> | null = null;

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

function handleFileChange(file: UploadFile) {
  selectedFile.value = file.raw ?? null;
}

async function handleGenerate() {
  if (!form.product_id) {
    ElMessage.warning("请选择商品");
    return;
  }
  if (!selectedFile.value) {
    ElMessage.warning("请上传商品图片");
    return;
  }

  generating.value = true;
  try {
    // Step 1: Upload image
    const uploadForm = new FormData();
    uploadForm.append("product_id", String(form.product_id));
    uploadForm.append("file", selectedFile.value);

    await apiClient.post("/images/upload", uploadForm, {
      headers: { "Content-Type": "multipart/form-data" },
    });

    // Step 2: Create generation task
    const res = await apiClient.post("/images/generate", {
      product_id: form.product_id,
      style: form.style,
    });

    taskStatus.value = { status: "pending", task_id: res.data.task_id };
    statusLabel.value = "任务已创建，正在生成中...";
    statusType.value = "info";

    // Step 3: Poll for results
    startPolling(res.data.task_id);
  } catch (err: unknown) {
    const msg =
      (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
      "生成失败";
    ElMessage.error(msg);
    generating.value = false;
  }
}

function startPolling(taskId: number) {
  pollTimer = setInterval(async () => {
    try {
      const res = await apiClient.get(`/images/tasks/${taskId}`);
      const task = res.data;

      if (task.status === "completed") {
        clearInterval(pollTimer!);
        generating.value = false;
        statusLabel.value = "生成完成！";
        statusType.value = "success";
        ElMessage.success("图片生成完成");

        // Load generated assets
        const assetsRes = await apiClient.get(
          `/images/assets/${form.product_id}?asset_type=generated`
        );
        generatedAssets.value = assetsRes.data.items;
      } else if (task.status === "failed") {
        clearInterval(pollTimer!);
        generating.value = false;
        statusLabel.value = `生成失败: ${task.error_message || "未知错误"}`;
        statusType.value = "error";
        ElMessage.error("图片生成失败");
      }
    } catch {
      clearInterval(pollTimer!);
      generating.value = false;
      statusType.value = "error";
    }
  }, 3000);
}

function formatStyle(metaJson: string): string {
  try {
    const meta = JSON.parse(metaJson);
    const styleMap: Record<string, string> = {
      home: "居家", outdoor: "户外", summer: "夏日",
      minimal: "极简", live: "直播间", promotion: "节日促销",
    };
    return `风格: ${styleMap[meta.style] || meta.style}`;
  } catch {
    return "";
  }
}
</script>

<style scoped>
.image-generate {
  max-width: 900px;
  margin: 0 auto;
}
.page-header {
  margin-bottom: 20px;
  display: flex;
  align-items: baseline;
  gap: 16px;
}
.page-header h2 { margin: 0; }
.page-desc { color: var(--color-text-secondary); font-size: 13px; }
.upload-card { margin-bottom: 20px; }
.upload-tip { color: var(--color-text-secondary); font-size: 12px; margin-top: 4px; }
.result-card { margin-bottom: 20px; }
.asset-card { text-align: center; }
.asset-image { width: 100%; height: 200px; }
.asset-style { color: var(--color-text-body); font-size: 13px; margin: 8px 0 0; }
</style>
