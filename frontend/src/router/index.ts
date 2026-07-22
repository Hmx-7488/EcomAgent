import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore, type Role } from "../stores/auth";

declare module "vue-router" { interface RouteMeta { roles?: Role[]; public?: boolean } }
const router = createRouter({ history: createWebHistory(), routes: [
  { path: "/", redirect: "/products" },
  { path: "/login", component: () => import("../views/Login.vue"), meta: { public: true } },
  { path: "/forbidden", component: () => import("../views/Forbidden.vue"), meta: { public: true } },
  // The M1 workstation contains price, cost and margin fields. Customer
  // service consumes approved facts through its later service surface, not
  // this financial workspace.
  { path: "/products", component: () => import("../views/ProductList.vue"), meta: { roles: ["admin", "operator_content"] } },
  { path: "/products/new", component: () => import("../views/ProductEdit.vue"), meta: { roles: ["admin", "operator_content"] } },
  { path: "/products/:id", component: () => import("../views/ProductDetail.vue"), props: true, meta: { roles: ["admin", "operator_content"] } },
  { path: "/products/:id/edit", redirect: (to) => `/products/${to.params.id}` },
  { path: "/:pathMatch(.*)*", redirect: "/forbidden" },
] });
router.beforeEach((to) => {
  const auth = useAuthStore();
  if (to.meta.public) return true;
  if (!auth.isAuthenticated) return { path: "/login", query: { redirect: to.fullPath } };
  if (to.meta.roles && (!auth.user || !to.meta.roles.includes(auth.user.role))) return "/forbidden";
  return true;
});
export default router;
