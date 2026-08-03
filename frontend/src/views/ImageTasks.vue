<template>
  <section>
    <div class="page-heading">
      <div>
        <div class="eyebrow">人工确认 / Image task</div>
        <h1>图片任务</h1>
        <p>先上传参考图，再创建任务；生成结果必须人工确认、审批后才可导出。</p>
      </div>
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
      v-else-if="!productLoading && productOptions.length === 0"
      type="warning"
      title="暂无可用于图片任务的已批准商品。"
      :closable="false"
      show-icon
      class="notice"
    />
    <div class="new-task panel">
      <div>
        <b>创建图片任务</b>
        <p>商品必须为已批准状态。参考图是创建任务的前置条件。</p>
      </div>
      <el-select
        v-model="selectedProductId"
        placeholder="选择已批准商品"
        filterable
        :loading="productLoading"
        :disabled="productLoading || productOptions.length === 0"
      >
        <el-option
          v-for="product in productOptions"
          :key="product.id"
          :label="product.name"
          :value="product.id"
        />
      </el-select>
      <el-select v-model="style" aria-label="场景">
        <el-option label="极简" value="minimal" />
        <el-option label="居家" value="home" />
      </el-select>
      <el-upload
        :auto-upload="false"
        :show-file-list="false"
        accept="image/png,image/jpeg,image/webp"
        :disabled="!selectedProductId"
        @change="onFile"
      >
        <el-button :disabled="!selectedProductId">上传参考图</el-button>
      </el-upload>
      <span class="file-name">{{ referenceFileName || "未选择参考图" }}</span>
      <el-button
        type="primary"
        :disabled="!selectedProductId || !referenceFile"
        :loading="working"
        @click="create"
      >
        创建任务
      </el-button>
    </div>
    <div class="task-grid" v-loading="loading">
      <article v-for="task in tasks" :key="task.id" class="task-card panel">
        <div class="task-top">
          <div>
            <span class="eyebrow">TASK {{ task.id }}</span>
            <h3>{{ productName(task.product_id) }}</h3>
          </div>
          <el-tag :type="statusType(task.status)">{{ task.status }}</el-tag>
        </div>
        <div v-if="taskResultAssets(task).length" class="preview-grid">
          <div
            v-for="asset in taskResultAssets(task)"
            :key="asset.id"
            class="result-asset"
          >
            <el-image :src="asset.url" fit="cover" />
            <span>Asset #{{ asset.id }}</span>
          </div>
        </div>
        <div v-else class="preview waiting">
          {{
            task.status === "pending" || task.status === "processing"
              ? "等待生成"
              : "暂无结果图"
          }}
        </div>
        <dl>
          <dt>场景</dt>
          <dd>{{ task.style }}</dd>
          <dt>参考图</dt>
          <dd>
            {{
              task.source_asset_id
                ? `Asset #${task.source_asset_id}`
                : "未记录"
            }}
          </dd>
          <dt>审批</dt>
          <dd>
            {{ approvalText(task.approval_status)
            }}{{ task.confirmed_at ? " · 已人工确认" : "" }}
          </dd>
          <dt v-if="task.error_message">失败原因</dt>
          <dd v-if="task.error_message" class="danger">
            {{ task.error_message }}
          </dd>
        </dl>
        <div class="task-actions">
          <el-button
            v-if="
              ['no_key', 'timeout', 'failed', 'field_missing'].includes(
                task.status,
              )
            "
            @click="action(task, 'retry')"
          >
            重试
          </el-button>
          <el-button
            v-if="task.status === 'completed' && !task.confirmed_at"
            @click="action(task, 'confirm')"
          >
            人工确认
          </el-button>
          <el-button
            v-if="
              task.status === 'completed' &&
              task.confirmed_at &&
              task.approval_status === 'draft'
            "
            type="primary"
            @click="action(task, 'submit')"
          >
            提交审批
          </el-button>
          <el-button
            v-if="
              task.status === 'completed' &&
              task.confirmed_at &&
              task.approval_status === 'approved'
            "
            type="success"
            @click="action(task, 'export')"
          >
            导出素材
          </el-button>
          <span v-if="task.approval_status !== 'approved'" class="blocked">
            未批准，不能导出
          </span>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import type { UploadFile } from "element-plus";
import { errorMessage } from "../api/client";
import {
  m2Api,
  parseResultAssetIds,
  type ApprovalStatus,
  type AssetRead,
  type ImageTask,
  type ImageTaskStatus,
  type ProductOption,
} from "../api/milestone2";

const tasks = ref<ImageTask[]>([]);
const productOptions = ref<ProductOption[]>([]);
const assets = ref<Record<number, AssetRead>>({});
const selectedProductId = ref<number>();
const style = ref("minimal");
const loading = ref(false);
const productLoading = ref(false);
const working = ref(false);
const error = ref("");
const referenceFileName = ref("");
const referenceFile = ref<File>();

const productNames = computed(
  () =>
    new Map(
      productOptions.value.map((product) => [product.id, product.name]),
    ),
);

function productName(productId: number) {
  return productNames.value.get(productId) || `商品 #${productId}`;
}

async function loadProducts() {
  productLoading.value = true;
  error.value = "";
  try {
    productOptions.value = await m2Api.listApprovedProducts();
  } catch (exception) {
    error.value = errorMessage(exception);
  } finally {
    productLoading.value = false;
  }
}

async function refresh() {
  loading.value = true;
  try {
    tasks.value = await m2Api.listTasks();
    const productIds = Array.from(
      new Set(tasks.value.map((task) => task.product_id)),
    );
    const lists = await Promise.all(
      productIds.map((productId) => m2Api.listAssets(productId)),
    );
    assets.value = Object.fromEntries(
      lists.flat().map((asset) => [asset.id, asset]),
    );
  } catch (exception) {
    error.value = errorMessage(exception);
  } finally {
    loading.value = false;
  }
}

function taskResultAssets(task: ImageTask) {
  return parseResultAssetIds(task.result_asset_ids)
    .map((id) => assets.value[id])
    .filter((asset): asset is AssetRead => Boolean(asset));
}

function onFile(file: UploadFile) {
  if (file.raw) {
    referenceFile.value = file.raw;
    referenceFileName.value = file.name;
  }
}

async function create() {
  if (!selectedProductId.value || !referenceFile.value) return;
  working.value = true;
  error.value = "";
  try {
    const reference = await m2Api.uploadReference(
      selectedProductId.value,
      referenceFile.value,
    );
    await m2Api.createTask(
      selectedProductId.value,
      reference.id,
      style.value,
    );
    referenceFileName.value = "";
    referenceFile.value = undefined;
    await refresh();
    ElMessage.success("图片任务已创建");
  } catch (exception) {
    error.value = errorMessage(exception);
  } finally {
    working.value = false;
  }
}

async function action(
  task: ImageTask,
  actionName: "retry" | "confirm" | "submit" | "export",
) {
  try {
    const updated = await m2Api.taskAction(task.id, actionName);
    tasks.value = tasks.value.map((item) =>
      item.id === updated.id ? updated : item,
    );
    ElMessage.success(
      actionName === "export"
        ? "已导出素材并记录审计"
        : "状态已更新",
    );
  } catch (exception) {
    error.value = errorMessage(exception);
  }
}

function statusType(status: ImageTaskStatus) {
  return (
    status === "completed"
      ? "success"
      : ["failed", "no_key", "timeout", "field_missing"].includes(status)
        ? "danger"
        : "warning"
  ) as "success" | "danger" | "warning";
}

function approvalText(status: ApprovalStatus) {
  return {
    draft: "草稿",
    submitted: "待审批",
    approved: "已批准",
    rejected: "已拒绝",
  }[status];
}

onMounted(() => Promise.all([loadProducts(), refresh()]));
</script>

<style scoped>
.notice {
  margin-bottom: 14px;
}
.new-task {
  display: grid;
  grid-template-columns:
    minmax(220px, 1.4fr) minmax(180px, 1fr) 110px auto
    minmax(120px, 0.8fr) auto;
  gap: 12px;
  align-items: center;
  margin-bottom: 18px;
}
.new-task p {
  color: var(--muted);
  font-size: 12px;
  margin: 5px 0 0;
}
.file-name {
  font-size: 12px;
  color: var(--muted);
}
.task-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(330px, 1fr));
  gap: 16px;
}
.task-card {
  padding: 14px;
}
.task-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
.task-top h3 {
  margin: 4px 0 12px;
  font-size: 16px;
}
.preview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(92px, 1fr));
  gap: 8px;
}
.result-asset {
  min-width: 0;
  overflow: hidden;
  border-radius: 4px;
  background: #eef3ef;
}
.result-asset :deep(.el-image) {
  display: block;
  width: 100%;
  height: 130px;
}
.result-asset span {
  display: block;
  padding: 6px 8px;
  color: var(--muted);
  font-size: 11px;
}
.preview {
  height: 180px;
  background: #eef3ef;
  border-radius: 4px;
  overflow: hidden;
}
.waiting {
  display: grid;
  place-items: center;
  color: var(--muted);
}
dl {
  display: grid;
  grid-template-columns: 65px 1fr;
  gap: 7px;
  margin: 14px 0;
  font-size: 13px;
}
dt {
  color: var(--muted);
}
dd {
  margin: 0;
}
.danger {
  color: #b42318;
}
.task-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.blocked {
  font-size: 12px;
  color: var(--muted);
}
@media (max-width: 900px) {
  .new-task {
    grid-template-columns: 1fr;
  }
}
</style>
