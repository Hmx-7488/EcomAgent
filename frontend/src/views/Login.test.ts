import { createApp, defineComponent, nextTick } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({
  default: {},
  usingMock: false,
  errorMessage: (error: unknown) => String(error),
}));
vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({
    user: null,
    login: vi.fn(),
  }),
}));
vi.mock("vue-router", () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}));

import Login from "./Login.vue";

const mountedApps: Array<ReturnType<typeof createApp>> = [];

function registerStubs(app: ReturnType<typeof createApp>) {
  app.component(
    "el-alert",
    defineComponent({
      props: ["title"],
      template: "<div>{{ title }}</div>",
    }),
  );
  app.component(
    "el-form",
    defineComponent({ template: "<form><slot /></form>" }),
  );
  app.component(
    "el-form-item",
    defineComponent({
      props: ["label"],
      template: "<label>{{ label }}<slot /></label>",
    }),
  );
  app.component(
    "el-input",
    defineComponent({ props: ["modelValue"], template: "<input />" }),
  );
  app.component(
    "el-button",
    defineComponent({ template: "<button><slot /></button>" }),
  );
}

describe("Login real authentication messaging", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("does not claim that a password can be arbitrary when mock mode is off", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const app = createApp(Login);
    registerStubs(app);
    app.mount(host);
    mountedApps.push(app);
    await nextTick();

    expect(host.textContent).not.toContain("密码可任意填写");
    expect(host.textContent).not.toContain("P0 本地演示账号");
  });
});
