# P0 里程碑 1 验收测试

本目录只维护独立验收用例，不修改历史测试或业务实现。运行时明确指定目录，避免受遗留 `pytest.ini` 的 `testpaths` 限制：

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest p0_acceptance -q
```

当前冻结的 M1 契约：

- `POST /auth/login` `{username,password}`、`GET /auth/me`、Bearer token；成功响应含 `access_token`、`token_type: bearer` 与 `user`。
- `GET/POST/PATCH /api/products`；`GET/POST/PATCH /api/products/{id}/skus[/{skuId}]`。
- `POST /api/skus/{skuId}/costs`，`GET /api/skus/{skuId}/margin`。
- 统一错误：`{"detail":{"code":"validation_error|authentication_required|permission_denied|not_found|conflict|internal_error","message":"...","fields":{...}?}}`。

覆盖映射：C-F01（固定角色和越权）、C-F02（商品/SKU/成本/毛利）和 C-Q04（无 Key）、C-Q07（公式、缺失成本、零售价、负数成本、错误响应）。测试账号使用固定、仅限 SQLite seed 的凭据，并集中在 `helpers.py`，不读取 `.env`。

网络隔离通过 socket 拦截实现；无 Key 用在临时目录启动的子进程验证，因而不读取 `backend/.env`。
