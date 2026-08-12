import { beforeEach, describe, expect, it } from "vitest";
import { createApiClient, errorMessage } from "./client";

describe("product category mock and safe error contracts", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("implements the active category list and admin-only create contract", async () => {
    sessionStorage.setItem(
      "ecomagent_user",
      JSON.stringify({ id: "1", username: "admin", role: "admin" }),
    );
    const client = createApiClient(true);

    const before = await client.get("/product-categories");
    const name = `测试一级类目-${Date.now()}`;
    const created = await client.post("/product-categories", { name: ` ${name} ` });
    const after = await client.get("/product-categories");

    expect(before.data).toEqual({
      items: expect.any(Array),
      total: expect.any(Number),
    });
    expect(created.status).toBe(201);
    expect(created.data.name).toBe(name);
    expect(created.data.is_active).toBe(true);
    expect(after.data.total).toBe(before.data.total + 1);
  });

  it("rejects exact duplicate categories while keeping comparison case-sensitive", async () => {
    sessionStorage.setItem(
      "ecomagent_user",
      JSON.stringify({ id: "1", username: "admin", role: "admin" }),
    );
    const client = createApiClient(true);
    const name = `CaseSensitive-${Date.now()}`;

    await client.post("/product-categories", { name });
    await expect(client.post("/product-categories", { name })).rejects.toMatchObject({
      response: { status: 409, data: { detail: { code: "category_exists" } } },
    });
    await expect(
      client.post("/product-categories", { name: name.toLowerCase() }),
    ).resolves.toMatchObject({ status: 201 });
  });

  it("enforces mock RBAC and rejects products outside the dictionary", async () => {
    const client = createApiClient(true);
    sessionStorage.setItem(
      "ecomagent_user",
      JSON.stringify({
        id: "3",
        username: "customer_service",
        role: "customer_service",
      }),
    );
    await expect(client.get("/product-categories")).rejects.toMatchObject({
      response: { status: 403 },
    });

    sessionStorage.setItem(
      "ecomagent_user",
      JSON.stringify({ id: "2", username: "operator_content", role: "operator_content" }),
    );
    await expect(
      client.post("/product-categories", { name: "运营不可新增" }),
    ).rejects.toMatchObject({ response: { status: 403 } });
    await expect(
      client.post("/products", {
        name: "未知类目商品",
        category: "字典外类目",
        skus: [{ sku_name: "标准款", price: 0 }],
      }),
    ).rejects.toMatchObject({
      response: { status: 422, data: { detail: { code: "category_not_found" } } },
    });
  });

  it("maps category and validation failures to safe Chinese field messages", () => {
    expect(
      errorMessage({
        response: { data: { detail: { code: "category_exists", message: "internal" } } },
      }),
    ).toBe("该一级类目已存在");
    expect(
      errorMessage({
        response: {
          data: {
            detail: {
              code: "validation_error",
              message: "请求参数校验失败",
              fields: [
                {
                  field: "第1个SKU零售价",
                  message: "第1个SKU零售价必须是有限数字",
                },
              ],
            },
          },
        },
      }),
    ).toBe("第1个SKU零售价必须是有限数字");
    expect(
      errorMessage({
        response: {
          data: {
            detail: {
              code: "validation_error",
              message: "请求参数校验失败",
              fields: [{ field: "商品类目", message: "长度超出限制" }],
            },
          },
        },
      }),
    ).toBe("商品类目：长度超出限制");
  });

  it("does not require raw validation locations or display internal objects", () => {
    expect(
      errorMessage({
        response: {
          data: {
            detail: {
              code: "validation_error",
              message: "请求参数校验失败",
              fields: [{ field: "请求参数", message: "输入内容不符合要求" }],
            },
          },
        },
      }),
    ).toBe("请求参数：输入内容不符合要求");
    expect(
      errorMessage({
        response: { data: { detail: { message: { internal: "secret" } } } },
      }),
    ).toBe("请求失败，请稍后重试");
  });
});
