/**
 * Minimal i18n foundation for EcomAgent.
 *
 * P0 targets Chinese-market merchants — all strings are Chinese by default.
 * The i18n structure exists so future localization (en, ja, etc.) can
 * be added by providing additional locale files without refactoring views.
 */
import { reactive } from "vue";

const zh = {
  app: { title: "EcomAgent", subtitle: "AI 电商运营工作台" },
  nav: { products: "商品管理", content: "内容生成", images: "图片生成", logs: "工具调用日志" },
  product: {
    title: "商品管理",
    create: "新增商品",
    edit: "编辑商品",
    name: "商品名称",
    category: "商品类目",
    brand: "品牌",
    description: "商品描述",
    sellingPoints: "核心卖点",
    skuManagement: "SKU 管理",
    addSku: "+ 添加 SKU",
    delete: "删除",
    cancel: "取消",
    save: "保存修改",
    submit: "创建商品",
    deleteConfirm: "确认删除「{name}」？",
    deleteTitle: "删除确认",
    deleted: "已删除",
    updated: "商品已更新",
    created: "商品已创建",
    loadError: "加载商品信息失败",
    saveError: "保存失败",
  },
  content: {
    title: "内容生成",
    selectProduct: "选择商品",
    contentType: "内容类型",
    platform: "目标平台",
    styleHint: "风格提示",
    generate: "生成内容",
    result: "生成结果",
    history: "生成历史",
    hint: "已配置 LLM 时将调用 Qwen 生成内容；未配置时使用模板兜底。",
  },
  logs: {
    title: "工具调用日志",
    desc: "Agent 每次工具调用的完整记录——展示系统不是简单聊天机器人",
  },
  common: {
    save: "保存",
    cancel: "取消",
    delete: "删除",
    edit: "编辑",
    confirm: "确认",
    loading: "加载中...",
    noData: "暂无数据",
    error: "操作失败",
  },
};

type Messages = typeof zh;

const en: Messages = {
  app: { title: "EcomAgent", subtitle: "AI E-Commerce Workbench" },
  nav: { products: "Products", content: "Content", images: "Images", logs: "Tool Logs" },
  product: {
    title: "Products",
    create: "New Product",
    edit: "Edit Product",
    name: "Product Name",
    category: "Category",
    brand: "Brand",
    description: "Description",
    sellingPoints: "Selling Points",
    skuManagement: "SKU Management",
    addSku: "+ Add SKU",
    delete: "Delete",
    cancel: "Cancel",
    save: "Save",
    submit: "Create Product",
    deleteConfirm: 'Delete "{name}"?',
    deleteTitle: "Confirm Delete",
    deleted: "Deleted",
    updated: "Product updated",
    created: "Product created",
    loadError: "Failed to load product",
    saveError: "Failed to save",
  },
  content: {
    title: "Content Generation",
    selectProduct: "Select Product",
    contentType: "Content Type",
    platform: "Platform",
    styleHint: "Style Hint",
    generate: "Generate",
    result: "Result",
    history: "History",
    hint: "Calls Qwen when LLM is configured; falls back to templates otherwise.",
  },
  logs: {
    title: "Tool Call Logs",
    desc: "Complete record of every Agent tool call — proving this is not a simple chatbot",
  },
  common: {
    save: "Save",
    cancel: "Cancel",
    delete: "Delete",
    edit: "Edit",
    confirm: "Confirm",
    loading: "Loading...",
    noData: "No data",
    error: "Operation failed",
  },
};

const locales: Record<string, Messages> = { zh, en };

export const i18n = reactive({
  locale: "zh" as string,
  messages: zh as Messages,
  t(key: string, params?: Record<string, string>): string {
    const keys = key.split(".");
    let value: unknown = this.messages;
    for (const k of keys) {
      value = (value as Record<string, unknown>)?.[k];
      if (value === undefined) return key;
    }
    let result = String(value);
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        result = result.replace(`{${k}}`, v);
      }
    }
    return result;
  },
  setLocale(locale: string) {
    this.locale = locale;
    this.messages = locales[locale] || zh;
  },
});
