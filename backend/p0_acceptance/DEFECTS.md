# P0 里程碑 1 缺陷清单

| ID | 状态 | 严重度 | 发现依据 | 描述 | 验收映射 |
| --- | --- | --- | --- | --- | --- |
| M1-QA-001 | Fixed | P0 blocker | Gate 0 基线 | 测试配置会加载本地 `.env`，Provider fallback 可能意外读取真实 Key；已改为不加载 `.env`，测试 fixture 清空 Provider 配置并拦截外网。 | C-Q04 |
| M1-QA-002 | Fixed | P0 blocker | Gate 0 基线 | 9 项既有失败尚未全部修复，禁止删除或弱化历史用例；组合回归 87 项均已通过。 | 回归门禁 |
| M1-QA-003 | Fixed | P0 blocker | M1 契约 | 当前产品 API 尚无本地认证、固定角色授权、成本与毛利端点；已实现并由验收覆盖。 | C-F01, C-F02, C-Q07 |
| M1-QA-004 | Fixed | High | M1 契约 | 既有 HTTP 错误为字符串 `detail`，未符合统一错误 envelope；现已统一。 | C-F01, C-Q07 |
| M1-QA-005 | Fixed | Medium | 测试发现 | `pytest.ini` 的 `testpaths` 未包含本目录；现已默认收集 `p0_acceptance`，`python -m pytest -q` 覆盖全部验收。 | 回归门禁 |
| M1-QA-006 | Fixed | High | M1 组合回归 | `RateLimitMiddleware._clients` 在 TestClient/测试间共享；合并运行时累计请求超过 100 后返回 429，导致无关用例失败。测试 fixture 已每例重置内存状态，生产限流不变。 | 回归门禁 |
| M2-QA-001 | Fixed | P0 blocker | M2 验收契约 | 内容、图片、审批、导出与审计已与冻结 API 集成；验收覆盖事实来源、版本不可覆盖、Provider 异常、审批门禁、RBAC 和审计，默认回归已通过。 | C-F03, C-F04, C-F06, C-Q04 |
| M2-QA-002 | Fixed | Low | M4 默认回归 | 已迁移 `SettingsConfigDict`、为两个 `model_name` Schema 配置 `protected_namespaces`，并以 timezone-aware UTC 替代三处 `datetime.utcnow()`；M4 默认回归 166 项通过且 0 warning。 | 质量维护 |
| M3-QA-001 | Fixed | High | M3 金标回归 | 多 SKU 简称、包装数量、承重说明、适用场景和重复使用问法曾错误转人工或选错事实；已修复事实字段选择，金标恢复为 50/50。 | C-F05, C-Q01 |
| M3-QA-002 | Fixed | P0 blocker | M3 冲突事实契约 | 描述与结构化参数冲突时曾选择单一字段自动回复；现以 `fact_conflict` 安全转人工，不编造或擅自裁决。 | C-F05, C-Q02, C-Q03 |
| M3-QA-003 | Fixed | High | M3 红队回归 | RT-24 必须用缺材质夹具验证，避免“已有材质商品返回已批准事实”的假阴性；修正后全 30 条均未自动回复。 | C-Q03 |
| M3-QA-004 | Fixed | High | M3 dataset regression | Gold/red tests reused conversations by product, so `waiting_review` or `transferred` contaminated later cases. Every example now creates an isolated anonymous conversation; only the TestClient limiter bucket is cleared between examples. Closed-Demo results are gold 50/50, no-data 10/10, sources 19/19, red-team 30/30; production rate limiting is unchanged. | C-Q01, C-Q02, C-Q03 |
| M3-QA-005 | Fixed | High | M3 Provider contract regression | Old tests incorrectly expected low-risk answers to call a Provider. Tests now prove deterministic low-risk Provider calls are 0; each medium-risk failure stub is called once and fails closed. The Qwen `no_key` adapter makes 0 DashScope calls. | C-Q03, C-Q04 |
| M3-QA-006 | Fixed | P0 blocker | Gate 3 state-machine regression | Customer supplements in `waiting_review` regenerated drafts, while supplements in `transferred` could reopen the conversation. Both states now append only the customer business message, preserve state/draft/notice, and make 0 Provider calls; `resolved` remains 409. | C-F05 |
| M3-QA-007 | Fixed | High | Gate 3 privacy/input regression | Audit rows duplicated draft, staff reply, and manual-transfer note text; whitespace-only inputs could pass validation. Audit now stores fixed codes, message IDs, lengths and SHA-256 evidence only, while all three request schemas trim before validation and return the unified 422 envelope for blank input. | C-F06, C-Q04 |

| M4-QA-001 | External | Low | 前端 production build | `@vueuse/core` 依赖中两处 PURE 注释位置提示由 Rollup 安全移除；项目代码无法修复且未修改 `node_modules`，构建成功、最大 JS chunk 351.10 KB。 | 外部非阻塞 warning |