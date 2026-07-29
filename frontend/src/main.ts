import { createApp } from "vue";
import {
  ElAlert, ElButton, ElCard, ElCol, ElCollapse, ElCollapseItem, ElContainer,
  ElDialog, ElDivider, ElForm, ElFormItem, ElHeader, ElImage, ElInput,
  ElInputNumber, ElMain, ElOption, ElPagination, ElResult, ElRow, ElSelect,
  ElSkeleton, ElTabPane, ElTable, ElTableColumn, ElTabs, ElTag, ElTooltip,
  ElUpload,
} from "element-plus";
import "element-plus/dist/index.css";
import { createPinia } from "pinia";

import App from "./App.vue";
import router from "./router";

const app = createApp(App);

[
  ElAlert, ElButton, ElCard, ElCol, ElCollapse, ElCollapseItem, ElContainer,
  ElDialog, ElDivider, ElForm, ElFormItem, ElHeader, ElImage, ElInput,
  ElInputNumber, ElMain, ElOption, ElPagination, ElResult, ElRow, ElSelect,
  ElSkeleton, ElTabPane, ElTable, ElTableColumn, ElTabs, ElTag, ElTooltip,
  ElUpload,
].forEach((component) => app.component(component.name!, component));
app.use(createPinia());
app.use(router);

app.mount("#app");
