import { describe, expect, it } from "vitest";
import { canCustomerSend, conversationTokenHeaders, customerStatusText, isUncertainTransferReason, m3Api, toCustomerConversation } from "./milestone3";
import { isRoleAllowed, routes } from "../router";
import { shouldAttachStaffAuthorization } from "./client";

describe("M3 frozen customer service contract", () => {
  it("sends the opaque conversation credential only in the dedicated header", () => {
    expect(conversationTokenHeaders("opaque-token")).toEqual({ headers: { "X-Conversation-Token": "opaque-token" } });
    expect(JSON.stringify(conversationTokenHeaders("opaque-token"))).not.toContain("Authorization");
    expect(shouldAttachStaffAuthorization("/customer/conversations/1")).toBe(false);
    expect(shouldAttachStaffAuthorization("/service/conversations/1")).toBe(true);
  });

  it("allow-lists public conversation fields and hides internal drafts", () => {
    const customer = toCustomerConversation({
      id: 9, status: "waiting_review", cost: 100, margin: 0.3, pending_draft: { content: "internal draft" },
      decisions: [{ reason_code: "internal" }],
      messages: [
        { id: 1, sender_type: "customer", content: "公开问题", created_at: "2026-07-26T00:00:00Z", visibility: "customer" },
        { id: 2, sender_type: "assistant", content: "internal draft", created_at: "2026-07-26T00:00:01Z", visibility: "internal", message_type: "draft" },
      ],
    });
    expect(customer.messages.map((item) => item.content)).toEqual(["公开问题"]);
    expect(customer).not.toHaveProperty("pending_draft");
    expect(customer).not.toHaveProperty("decisions");
    expect(customer).not.toHaveProperty("cost");
    expect(customer).not.toHaveProperty("margin");
  });

  it("restores the safe uncertainty reason without exposing internal decisions", () => {
    const customer = toCustomerConversation({ id: 11, status: "transferred", reason_code: "fact_conflict", decisions: [{ prompt: "internal" }], messages: [] });
    expect(customer.reason_code).toBe("fact_conflict");
    expect(isUncertainTransferReason(customer.reason_code)).toBe(true);
    expect(isUncertainTransferReason("complaint_or_dispute")).toBe(false);
    expect(customer).not.toHaveProperty("decisions");
  });

  it("keeps a review draft invisible until customer service sends it", async () => {
    const products = await m3Api.listCustomerProducts();
    expect(products[0].name).toBe("可视折叠衣物收纳箱");
    expect(products[0].name).not.toMatch(/\?{3}/);
    const created = await m3Api.createConversation(products[0].id);
    const publicState = await m3Api.sendCustomerMessage(created.id, created.access_token, "请核对这个问题");
    expect(publicState.status).toBe("waiting_review");
    expect(publicState.messages.some((item) => item.content.includes("客服依据"))).toBe(false);
    const serviceState = await m3Api.getServiceConversation(created.id);
    expect(typeof serviceState.pending_draft === "string" ? serviceState.pending_draft : serviceState.pending_draft?.content).toContain("客服依据");
    expect(serviceState.decisions[serviceState.decisions.length - 1]?.decision).toBe("review_draft");
  });

  it("appends supplemental customer messages without rerouting queued conversations", async () => {
    const product = (await m3Api.listCustomerProducts())[0];
    const created = await m3Api.createConversation(product.id);
    await m3Api.sendCustomerMessage(created.id, created.access_token, "第一条待审核问题");
    const reviewBefore = await m3Api.getServiceConversation(created.id);
    const waiting = await m3Api.sendCustomerMessage(created.id, created.access_token, "补充说明一");
    const reviewAfter = await m3Api.getServiceConversation(created.id);
    expect(waiting.status).toBe("waiting_review");
    expect(waiting.messages[waiting.messages.length - 1]?.content).toBe("补充说明一");
    expect(reviewAfter.decisions).toHaveLength(reviewBefore.decisions.length);
    await m3Api.transferServiceConversation(created.id, "人工处理");
    const transferBefore = await m3Api.getServiceConversation(created.id);
    const transferred = await m3Api.sendCustomerMessage(created.id, created.access_token, "补充说明二");
    const transferAfter = await m3Api.getServiceConversation(created.id);
    expect(transferred.status).toBe("transferred");
    expect(transferred.messages[transferred.messages.length - 1]?.content).toBe("补充说明二");
    expect(transferAfter.decisions).toHaveLength(transferBefore.decisions.length);
  });

  it("keeps resolved conversations closed and labels an uncreated conversation", async () => {
    expect(customerStatusText(undefined)).toBe("准备开始");
    expect(canCustomerSend("open")).toBe(true);
    expect(canCustomerSend("waiting_review")).toBe(true);
    expect(canCustomerSend("transferred")).toBe(true);
    expect(canCustomerSend("resolved")).toBe(false);
    const product = (await m3Api.listCustomerProducts())[0];
    const created = await m3Api.createConversation(product.id);
    await m3Api.resolveServiceConversation(created.id);
    await expect(m3Api.sendCustomerMessage(created.id, created.access_token, "不应发送")).rejects.toThrow();
  });

  it("freezes public and role-restricted routes", () => {
    const consult = routes.find((route) => route.path === "/consult");
    const service = routes.find((route) => route.path === "/service");
    expect(consult?.meta?.public).toBe(true);
    expect(service?.meta?.roles).toEqual(["admin", "customer_service"]);
    expect(service?.meta?.roles).not.toContain("operator_content");
    expect(isRoleAllowed("admin", service?.meta?.roles)).toBe(true);
    expect(isRoleAllowed("customer_service", service?.meta?.roles)).toBe(true);
    expect(isRoleAllowed("operator_content", service?.meta?.roles)).toBe(false);
  });
});
