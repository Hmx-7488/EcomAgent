import { defineStore } from "pinia";
import { computed, ref } from "vue";
import apiClient, { AUTH_LOGIN_PATH } from "../api/client";

/** Fixed backend roles. Customer is anonymous and deliberately has no backend account. */
export type Role = "admin" | "operator_content" | "customer_service";
export const useAuthStore = defineStore("auth", () => {
  const user = ref<{ id: string; username: string; role: Role } | null>(JSON.parse(sessionStorage.getItem("ecomagent_user") || "null"));
  const isAuthenticated = computed(() => !!user.value);
  async function login(username: string, password: string) {
    const res = await apiClient.post(AUTH_LOGIN_PATH, { username, password });
    user.value = res.data.user;
    sessionStorage.setItem("ecomagent_user", JSON.stringify(res.data.user));
    sessionStorage.setItem("ecomagent_token", res.data.access_token);
  }
  function logout() { user.value = null; sessionStorage.removeItem("ecomagent_user"); sessionStorage.removeItem("ecomagent_token"); }
  return { user, isAuthenticated, login, logout };
});
