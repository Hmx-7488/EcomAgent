import apiClient, { usingMock } from "./client";

export type ConversationStatus = "open" | "waiting_review" | "transferred" | "resolved";
export type RiskLevel = "low" | "medium" | "high";
export type CustomerProduct = { id: number; name: string; category?: string; brand?: string; summary?: string; status: string };
export type ConversationMessage = { id: number | string; sender_type: "customer" | "assistant" | "customer_service" | "system"; content: string; created_at: string };
export type CustomerConversation = { id: number | string; status: ConversationStatus; product?: { id: number; name: string }; messages: ConversationMessage[]; notice?: string; reason_code?: string; created_at?: string; updated_at?: string };
export type CreatedConversation = CustomerConversation & { access_token: string };
export type FactSource = { source_object_id?: number | string; source_type?: string; version?: string; field_summary?: string; data_time?: string };
export type ServiceQueueItem = { id: number | string; product?: { id: number; name: string }; status: ConversationStatus; last_risk_level?: RiskLevel; transfer_reason?: string; last_customer_message?: string; created_at?: string; updated_at?: string };
export type ServiceMessage = ConversationMessage & { visibility?: string; message_type?: string };
export type ServiceDecision = { risk_level?: RiskLevel; decision?: string; reason_code?: string; created_at?: string };
export type ServiceConversation = ServiceQueueItem & { messages: ServiceMessage[]; decisions: ServiceDecision[]; fact_sources: FactSource[]; pending_draft?: { content?: string; created_at?: string } | string | null };

type UnknownRecord = Record<string, unknown>;
const asRecord = (value: unknown): UnknownRecord => value && typeof value === "object" ? value as UnknownRecord : {};
const asText = (value: unknown) => typeof value === "string" ? value : undefined;
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const now = () => new Date().toISOString();

export function canCustomerSend(status?: ConversationStatus) { return Boolean(status && status !== "resolved"); }
export function customerStatusText(status?: ConversationStatus) {
  return status ? ({ open: "咨询中", waiting_review: "等待客服审核", transferred: "已转人工", resolved: "已解决" })[status] : "准备开始";
}

const uncertainTransferReasons = new Set(["fact_missing_or_ambiguous", "fact_conflict", "approved_product_required"]);
export function isUncertainTransferReason(reasonCode?: string) {
  return Boolean(reasonCode && (uncertainTransferReasons.has(reasonCode) || reasonCode.startsWith("provider_")));
}

export function conversationTokenHeaders(accessToken: string) {
  return { headers: { "X-Conversation-Token": accessToken } };
}

function unwrapItems(value: unknown): unknown[] {
  const payload = asRecord(value);
  return Array.isArray(value) ? value : Array.isArray(payload.items) ? payload.items : [];
}

/** Public data is allow-listed: no draft, decision, audit, cost, margin or inventory. */
export function toCustomerConversation(value: unknown): CustomerConversation {
  const payload = asRecord(value);
  const product = asRecord(payload.product);
  const rawMessages = Array.isArray(payload.messages) ? payload.messages.map(asRecord) : [];
  return {
    id: (payload.id ?? payload.conversation_id ?? "") as number | string,
    status: (payload.status ?? "open") as ConversationStatus,
    product: payload.product ? { id: Number(product.id), name: asText(product.name) ?? "" } : undefined,
    notice: asText(payload.notice),
    reason_code: asText(payload.reason_code),
    messages: rawMessages
      .filter((message) => message.visibility !== "internal" && message.message_type !== "draft")
      .map((message, index) => ({ id: (message.id ?? index) as number | string, sender_type: (message.sender_type ?? "system") as ConversationMessage["sender_type"], content: asText(message.content) ?? "", created_at: asText(message.created_at) ?? "" })),
    created_at: asText(payload.created_at), updated_at: asText(payload.updated_at),
  };
}

function toQueueItem(value: unknown): ServiceQueueItem {
  const item = asRecord(value); const product = asRecord(item.product);
  return {
    id: (item.id ?? "") as number | string,
    product: item.product ? { id: Number(product.id), name: asText(product.name) ?? "" } : undefined,
    status: (item.status ?? "open") as ConversationStatus,
    last_risk_level: asText(item.last_risk_level) as RiskLevel | undefined,
    transfer_reason: asText(item.transfer_reason), last_customer_message: asText(item.last_customer_message),
    created_at: asText(item.created_at), updated_at: asText(item.updated_at),
  };
}

function toServiceConversation(value: unknown): ServiceConversation {
  const item = asRecord(value);
  const rawMessages = Array.isArray(item.messages) ? item.messages.map(asRecord) : [];
  const rawDecisions = Array.isArray(item.decisions) ? item.decisions.map(asRecord) : [];
  const rawSources = Array.isArray(item.fact_sources) ? item.fact_sources.map(asRecord) : [];
  const draft = asRecord(item.pending_draft);
  return {
    ...toQueueItem(item),
    messages: rawMessages.map((message, index) => ({ id: (message.id ?? index) as number | string, sender_type: (message.sender_type ?? "system") as ConversationMessage["sender_type"], content: asText(message.content) ?? "", created_at: asText(message.created_at) ?? "", visibility: asText(message.visibility), message_type: asText(message.message_type) })),
    decisions: rawDecisions.map((decision) => ({ risk_level: asText(decision.risk_level) as RiskLevel | undefined, decision: asText(decision.decision), reason_code: asText(decision.reason_code), created_at: asText(decision.created_at) })),
    fact_sources: rawSources.map((source) => ({ source_object_id: (source.source_object_id ?? source.object_id) as number | string | undefined, source_type: asText(source.source_type ?? source.object_type), version: asText(source.version ?? source.source_version), field_summary: asText(source.field_summary), data_time: asText(source.data_time) })),
    pending_draft: typeof item.pending_draft === "string" ? item.pending_draft : item.pending_draft ? { content: asText(draft.content), created_at: asText(draft.created_at) } : null,
  };
}

let sequence = 30;
const mockProducts: CustomerProduct[] = [{ id: 1, name: "可视折叠衣物收纳箱", category: "居家收纳", brand: "栖纳家居", summary: "100L · 60×45×37cm", status: "approved" }];
const mockTokens = new Map<string, string>();
const mockConversations = new Map<string, ServiceConversation>();
function getMock(id: number | string) { const item = mockConversations.get(String(id)); if (!item) throw new Error("会话不存在"); return item; }
function checkMockToken(id: number | string, token: string) { if (mockTokens.get(String(id)) !== token) throw new Error("会话凭据无效"); }

export const m3Api = {
  async listCustomerProducts(): Promise<CustomerProduct[]> {
    if (usingMock) return clone(mockProducts);
    const { data } = await apiClient.get("/customer/products");
    return unwrapItems(data).map(asRecord).map((item) => ({ id: Number(item.id), name: asText(item.name) ?? "", category: asText(item.category), brand: asText(item.brand), summary: asText(item.summary), status: asText(item.status) ?? "approved" }));
  },
  async createConversation(productId: number): Promise<CreatedConversation> {
    if (usingMock) {
      const id = ++sequence; const accessToken = `${crypto.randomUUID()}${crypto.randomUUID()}`;
      const product = mockProducts.find((item) => item.id === productId)!;
      const conversation: ServiceConversation = { id, product: { id: product.id, name: product.name }, status: "open", messages: [], decisions: [], fact_sources: [], pending_draft: null, created_at: now(), updated_at: now() };
      mockTokens.set(String(id), accessToken); mockConversations.set(String(id), conversation);
      return { ...toCustomerConversation(conversation), access_token: accessToken };
    }
    const { data } = await apiClient.post("/customer/conversations", { product_id: productId });
    const item = asRecord(data); return { ...toCustomerConversation(item), access_token: asText(item.access_token) ?? "" };
  },
  async getCustomerConversation(id: number | string, accessToken: string): Promise<CustomerConversation> {
    if (usingMock) { checkMockToken(id, accessToken); return clone(toCustomerConversation(getMock(id))); }
    const { data } = await apiClient.get(`/customer/conversations/${id}`, conversationTokenHeaders(accessToken)); return toCustomerConversation(data);
  },
  async sendCustomerMessage(id: number | string, accessToken: string, content: string): Promise<CustomerConversation> {
    if (usingMock) {
      checkMockToken(id, accessToken); const item = getMock(id);
      if (!canCustomerSend(item.status)) throw new Error("会话已解决");
      item.messages.push({ id: ++sequence, sender_type: "customer", content, created_at: now(), visibility: "customer", message_type: "customer_message" });
      if (item.status !== "open") { item.updated_at = now(); return clone(toCustomerConversation(item)); }
      item.status = "waiting_review"; item.last_risk_level = "medium";
      item.decisions.push({ risk_level: "medium", decision: "review_draft", reason_code: "mock_review_draft", created_at: now() });
      item.fact_sources = [{ source_object_id: 1, source_type: "product", version: "product-1:v3", field_summary: "已批准商品事实", data_time: now() }];
      item.pending_draft = { content: "请客服依据已审核事实核对后回复。", created_at: now() }; item.updated_at = now();
      return clone(toCustomerConversation(item));
    }
    const { data } = await apiClient.post(`/customer/conversations/${id}/messages`, { content }, conversationTokenHeaders(accessToken));
    const conversation = await this.getCustomerConversation(id, accessToken);
    conversation.notice = asText(asRecord(data).notice);
    return conversation;
  },
  async listServiceConversations(queueStatus: "waiting_review" | "transferred"): Promise<ServiceQueueItem[]> {
    if (usingMock) return clone([...mockConversations.values()].filter((item) => item.status === queueStatus).map(toQueueItem));
    const { data } = await apiClient.get("/service/conversations", { params: { status: queueStatus } }); return unwrapItems(data).map(toQueueItem);
  },
  async getServiceConversation(id: number | string): Promise<ServiceConversation> {
    if (usingMock) return clone(getMock(id));
    const { data } = await apiClient.get(`/service/conversations/${id}`); return toServiceConversation(data);
  },
  async sendServiceReply(id: number | string, content: string): Promise<ServiceConversation> {
    if (usingMock) { const item = getMock(id); item.messages.push({ id: ++sequence, sender_type: "customer_service", content, created_at: now(), visibility: "customer", message_type: "service_reply" }); item.status = "open"; item.updated_at = now(); return clone(item); }
    const { data } = await apiClient.post(`/service/conversations/${id}/send`, { content }); return toServiceConversation(data);
  },
  async transferServiceConversation(id: number | string, reason: string): Promise<ServiceConversation> {
    if (usingMock) { const item = getMock(id); item.status = "transferred"; item.transfer_reason = reason; item.updated_at = now(); return clone(item); }
    const { data } = await apiClient.post(`/service/conversations/${id}/transfer`, { reason }); return toServiceConversation(data);
  },
  async resolveServiceConversation(id: number | string): Promise<ServiceConversation> {
    if (usingMock) { const item = getMock(id); item.status = "resolved"; item.updated_at = now(); return clone(item); }
    const { data } = await apiClient.post(`/service/conversations/${id}/resolve`, {}); return toServiceConversation(data);
  },
};
