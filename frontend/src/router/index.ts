import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { useAuthStore, type Role } from "../stores/auth";

declare module "vue-router" { interface RouteMeta { roles?: Role[]; public?: boolean } }
export const routes: RouteRecordRaw[] = [
  { path: "/", redirect: "/products" },
  { path: "/login", component: () => import("../views/Login.vue"), meta: { public: true } },
  { path: "/forbidden", component: () => import("../views/Forbidden.vue"), meta: { public: true } },
  { path: "/consult", component: () => import("../views/CustomerConsult.vue"), meta: { public: true } },
  // The M1 workstation contains price, cost and margin fields. Customer
  // service consumes approved facts through its later service surface, not
  // this financial workspace.
  { path: "/products", component: () => import("../views/ProductList.vue"), meta: { roles: ["admin", "operator_content"] } },
  { path: "/products/new", component: () => import("../views/ProductEdit.vue"), meta: { roles: ["admin", "operator_content"] } },
  { path: "/products/:id", component: () => import("../views/ProductDetail.vue"), props: true, meta: { roles: ["admin", "operator_content"] } },
  { path: "/products/:id/edit", redirect: (to) => `/products/${to.params.id}` },
  { path: "/content", component: () => import("../views/ContentWorkspace.vue"), meta: { roles: ["admin", "operator_content"] } },
  { path: "/image-tasks", component: () => import("../views/ImageTasks.vue"), meta: { roles: ["admin", "operator_content"] } },
  { path: "/approvals", component: () => import("../views/Approvals.vue"), meta: { roles: ["admin"] } },
  { path: "/service", component: () => import("../views/ServiceWorkspace.vue"), meta: { roles: ["admin", "customer_service"] } },
  { path: "/:pathMatch(.*)*", redirect: "/forbidden" },
];
export function isRoleAllowed(role: Role, allowed?: Role[]) { return !allowed || allowed.includes(role); }
const router = createRouter({ history: createWebHistory(), routes });
router.beforeEach((to) => {
  const auth = useAuthStore();
  if (to.meta.public) return true;
  if (!auth.isAuthenticated) return { path: "/login", query: { redirect: to.fullPath } };
  if (!auth.user || !isRoleAllowed(auth.user.role, to.meta.roles)) return "/forbidden";
  return true;
});
export default router;
