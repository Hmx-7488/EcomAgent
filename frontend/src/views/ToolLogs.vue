<template>
  <div class="tool-logs">
    <div class="page-header">
      <h2>工具调用日志</h2>
      <span class="page-desc">
        Agent 每次工具调用的完整记录——展示系统不是简单聊天机器人
      </span>
    </div>

    <el-table :data="logs.items" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="tool_name" label="工具名称" width="180" />
      <el-table-column label="参数" min-width="180">
        <template #default="{ row }">
          <el-tooltip :content="row.arguments_json || '无'" placement="top">
            <span class="cell-preview">{{ truncate(row.arguments_json, 60) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="结果摘要" min-width="200">
        <template #default="{ row }">
          <span class="cell-preview">{{ truncate(row.result_summary, 80) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="80">
        <template #default="{ row }">
          <el-tag
            :type="row.status === 'success' ? 'success' : 'danger'"
            size="small"
          >
            {{ row.status === 'success' ? '成功' : '失败' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="latency_ms" label="耗时" width="80">
        <template #default="{ row }">
          {{ row.latency_ms ? row.latency_ms + 'ms' : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="错误信息" min-width="150">
        <template #default="{ row }">
          <span class="error-text">{{ row.error_message || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="调用时间" width="180" />
    </el-table>

    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        :page-size="20"
        :total="logs.total"
        layout="total, prev, pager, next"
        @current-change="fetchLogs"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import apiClient from "../api/client";

const loading = ref(false);
const page = ref(1);

const logs = reactive<{
  items: {
    id: number;
    tool_name: string;
    arguments_json: string | null;
    result_summary: string | null;
    status: string;
    latency_ms: number | null;
    error_message: string | null;
    created_at: string;
  }[];
  total: number;
}>({ items: [], total: 0 });

onMounted(() => fetchLogs());

async function fetchLogs(p = 1) {
  loading.value = true;
  try {
    const res = await apiClient.get("/logs", { params: { page: p, page_size: 20 } });
    logs.items = res.data.items;
    logs.total = res.data.total;
  } finally {
    loading.value = false;
  }
}

function truncate(text: string | null, max: number): string {
  if (!text) return "-";
  return text.length > max ? text.slice(0, max) + "..." : text;
}
</script>

<style scoped>
.tool-logs {
  max-width: 1200px;
  margin: 0 auto;
}
.page-header {
  margin-bottom: 20px;
  display: flex;
  align-items: baseline;
  gap: 16px;
}
.page-header h2 {
  margin: 0;
}
.page-desc {
  color: var(--color-text-secondary);
  font-size: 13px;
}
.cell-preview {
  color: var(--color-text-body);
  font-size: 13px;
}
.error-text {
  color: var(--color-danger);
  font-size: 13px;
}
.pagination-wrap {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
