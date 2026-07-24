# P0 验收测试（里程碑 1–2）

本目录只维护独立验收用例，不修改历史测试或业务实现。默认测试配置必须收集本目录：

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest -q
```

当前冻结的 M1 契约：

- `POST /auth/login` `{username,password}`、`GET /auth/me`、Bearer token；成功响应含 `access_token`、`token_type: bearer` 与 `user`。
- `GET/POST/PATCH /api/products`；`GET/POST/PATCH /api/products/{id}/skus[/{skuId}]`。
- `POST /api/skus/{skuId}/costs`，`GET /api/skus/{skuId}/margin`。
- 统一错误：`{"detail":{"code":"validation_error|authentication_required|permission_denied|not_found|conflict|internal_error","message":"...","fields":{...}?}}`。

覆盖映射：C-F01（固定角色和越权）、C-F02（商品/SKU/成本/毛利）和 C-Q04（无 Key）、C-Q07（公式、缺失成本、零售价、负数成本、错误响应）。测试账号使用固定、仅限 SQLite seed 的凭据，并集中在 `helpers.py`，不读取 `.env`。

网络隔离通过 socket 拦截实现；无 Key 用在临时目录启动的子进程验证，因而不读取 `backend/.env`。

## M2 冻结契约与验收映射

- 内容包：`/api/content/packages` 仅能使用 `status=approved` 商品事实。创建、编辑、生成均形成新版本；历史已审批版本不可覆盖。版本记录事实版本、来源摘要、Provider/模型、任务状态与错误摘要，不能记录 Key。
- 内容审批：`draft -> submitted -> approved|rejected`；拒绝原因必填。仅管理员可批准、拒绝和导出；仅批准内容可以 Markdown 导出。
- 图片：先以 `/api/images/reference` 上传参考图，才能创建 `/api/images/tasks`。任务状态覆盖 `pending/processing/completed/no_key/timeout/failed/field_missing`；失败类可重试。
- 图片审批：完成任务必须由运营确认、提交，再由管理员审批；仅 `completed + confirmed + approved` 可导出。拒绝原因必填。
- 审计：内容和图片的创建、生成、编辑、提交、批准、拒绝、重试、确认、导出均进入 `/api/audit-events`；该端点限管理员。
- 边界：客服与匿名顾客无内容、图片、审批、导出或审计访问权。Provider 场景以可注入 stub 复现，套件不读取真实 Key 且不访问外网。

对应验收文档：`C-F03`（内容与推广素材包）、`C-F04`（图片任务）、`C-F06`（审批与审计）、`C-Q04`（密钥与隐私）及 P0 系统边界。
