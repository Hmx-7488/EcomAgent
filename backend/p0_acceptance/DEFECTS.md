# P0 里程碑 1 缺陷清单

| ID | 状态 | 严重度 | 发现依据 | 描述 | 验收映射 |
| --- | --- | --- | --- | --- | --- |
| M1-QA-001 | Fixed | P0 blocker | Gate 0 基线 | 测试配置会加载本地 `.env`，Provider fallback 可能意外读取真实 Key；已改为不加载 `.env`，测试 fixture 清空 Provider 配置并拦截外网。 | C-Q04 |
| M1-QA-002 | Fixed | P0 blocker | Gate 0 基线 | 9 项既有失败尚未全部修复，禁止删除或弱化历史用例；组合回归 87 项均已通过。 | 回归门禁 |
| M1-QA-003 | Fixed | P0 blocker | M1 契约 | 当前产品 API 尚无本地认证、固定角色授权、成本与毛利端点；已实现并由验收覆盖。 | C-F01, C-F02, C-Q07 |
| M1-QA-004 | Fixed | High | M1 契约 | 既有 HTTP 错误为字符串 `detail`，未符合统一错误 envelope；现已统一。 | C-F01, C-Q07 |
| M1-QA-005 | Open | Medium | 测试发现 | `pytest.ini` 的 `testpaths` 未包含本目录；M1 回归需以 `pytest p0_acceptance` 显式执行或由后端调整测试收集配置。 | 回归门禁 |
| M1-QA-006 | Fixed | High | M1 组合回归 | `RateLimitMiddleware._clients` 在 TestClient/测试间共享；合并运行时累计请求超过 100 后返回 429，导致无关用例失败。测试 fixture 已每例重置内存状态，生产限流不变。 | 回归门禁 |
