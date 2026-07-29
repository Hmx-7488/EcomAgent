import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import axios from "axios";
import apiClient, { API_BASE_URL, AUTH_LOGIN_PATH, AUTH_LOGIN_URL, createApiClient, resolveMockMode } from "../api/client";
import { resolveProtectedNavigation, routes } from "../router";
import { useAuthStore } from "./auth";

describe("production authentication contract", () => {
  beforeEach(() => { sessionStorage.clear(); setActivePinia(createPinia()); vi.restoreAllMocks(); });
  it("cannot enable Mock in a production build", () => {
    expect(resolveMockMode(false, undefined)).toBe(false);
    expect(resolveMockMode(false, "true")).toBe(false);
    expect(resolveMockMode(false, "false")).toBe(false);
    expect(resolveMockMode(true, "true")).toBe(true);
    expect(resolveMockMode(true, "false")).toBe(false);
  });
  it("builds the frozen real backend login URL without an nginx rewrite", async () => {
    const client = createApiClient(false);
    client.defaults.adapter = async (config) => {
      expect(config.baseURL).toBe(API_BASE_URL);
      expect(config.url).toBe(AUTH_LOGIN_PATH);
      expect(axios.getUri(config)).toBe(AUTH_LOGIN_URL);
      return { data: { access_token: "opaque-staff-token", user: { id: 1, username: "admin", role: "admin" } }, status: 200, statusText: "OK", headers: {}, config };
    };
    expect((await client.post(AUTH_LOGIN_PATH,{username:"admin",password:"secret"})).data.user.role).toBe("admin");
  });
  it("stores a successful backend login and preserves the fixed role", async () => {
    vi.spyOn(apiClient,"post").mockResolvedValueOnce({data:{access_token:"opaque-staff-token",user:{id:2,username:"customer_service",role:"customer_service"}}});
    const auth=useAuthStore(); await auth.login("customer_service","secret");
    expect(apiClient.post).toHaveBeenCalledWith(AUTH_LOGIN_PATH,{username:"customer_service",password:"secret"});
    expect(auth.user?.role).toBe("customer_service");
    expect(sessionStorage.getItem("ecomagent_token")).toBe("opaque-staff-token");
  });
  it("redirects anonymous access to login and denies a role outside the route boundary", () => {
    const route=routes.find(item=>item.path==="/service");
    expect(resolveProtectedNavigation({fullPath:"/service",roles:route?.meta?.roles},null)).toEqual({path:"/login",query:{redirect:"/service"}});
    expect(resolveProtectedNavigation({fullPath:"/service",roles:route?.meta?.roles},{role:"operator_content"})).toBe("/forbidden");
    expect(resolveProtectedNavigation({fullPath:"/service",roles:route?.meta?.roles},{role:"customer_service"})).toBe(true);
  });
});
