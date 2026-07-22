<template>
  <router-view v-if="isPublic" />
  <el-container v-else class="shell">
    <aside class="sidebar"><div class="brand">EcomAgent<small>栖纳家居 · 本地工作台</small></div>
      <nav><router-link v-for="item in menu" :key="item.to" :to="item.to" class="nav-item">{{ item.label }}</router-link></nav>
      <div class="side-note">当前为单商家 Demo 数据环境。任何平台发布、调价或投放操作均不在 P0 范围内。</div>
    </aside>
    <el-container><el-header class="topbar"><b>{{ title }}</b><div><el-tag effect="plain" type="success">{{ roleName }}</el-tag><el-button text @click="logout">退出登录</el-button></div></el-header>
      <el-main class="workspace"><router-view /></el-main></el-container>
  </el-container>
</template>
<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "./stores/auth";
const route = useRoute(); const router = useRouter(); const auth = useAuthStore();
const isPublic = computed(() => ["/login", "/forbidden"].includes(route.path));
const menu = computed(() => auth.user ? [{ to: "/products", label: auth.user.role === "customer_service" ? "商品事实查询" : "商品工作台" }] : []);
const title = computed(() => route.path.startsWith("/products") ? "商品工作台" : "EcomAgent");
const roleName = computed(() => ({ admin: "管理员", operator_content: "运营/内容", customer_service: "客服" }[auth.user?.role || "customer_service"]));
function logout() { auth.logout(); router.push("/login"); }
</script>
<style>
:root { font-family: "Microsoft YaHei", "Noto Sans SC", sans-serif; color:#17312b; background:#f5f7f5; --ink:#17312b; --line:#dbe5df; --green:#007d61; --muted:#66766f; }
* { box-sizing:border-box; } body { margin:0; min-width:320px; } .shell { min-height:100vh; } .sidebar { width:220px; background:#17312b; color:#f2faf6; padding:22px 14px; display:flex; flex-direction:column; } .brand { padding:0 10px 20px; font-size:20px; font-weight:700; } .brand small { display:block; margin-top:4px; color:#b7ccc2; font-size:12px; font-weight:400; } nav { display:grid; gap:4px; } .nav-item { border-radius:6px; color:#cbdcd4; padding:10px 12px; text-decoration:none; } .nav-item.router-link-active { color:#fff; background:#245044; } .side-note { margin-top:auto; color:#b7ccc2; border-top:1px solid #3a6055; padding:14px 10px 0; font-size:12px; line-height:1.6; } .topbar { display:flex; align-items:center; justify-content:space-between; background:#fff; border-bottom:1px solid var(--line); padding:0 30px; } .workspace { padding:28px 30px; max-width:1440px; width:100%; margin:auto; } .page-heading { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin-bottom:20px; } .page-heading h1 { margin:0 0 4px; font-size:22px; } .page-heading p { margin:0; color:var(--muted); } .panel { background:#fff; border:1px solid var(--line); border-radius:7px; padding:18px; } @media(max-width:760px) { .sidebar{display:none}.workspace{padding:18px 16px}.topbar{padding:0 16px} }
</style>
