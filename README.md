# EcomAgent P0

EcomAgent P0 是面向单商家私有化部署的电商经营辅助系统，覆盖本地账号与固定角色权限、商品/SKU/六项成本与预估毛利、内容和图片素材审批、受控售前客服及完整审计。P0 不接入任何电商平台，不执行发布、投放、调价、订单、物流或售后动作。

正式需求、架构和验收依据见 [docs/README.md](docs/README.md)。

## Docker Compose 启动

前置条件：Docker Desktop 或兼容的 Docker Engine、Docker Compose v2。

1. 将 `.env.example` 复制为仓库根目录 `.env`，至少替换 `POSTGRES_PASSWORD` 和 `JWT_SECRET` 为本地强随机值。Provider Key 可保持为空。
2. 构建并启动：

   ```powershell
   docker compose up --build -d
   ```

3. 查看健康状态：

   ```powershell
   docker compose ps
   ```

4. 浏览器访问 `http://localhost:8080`。后端容器会在应用启动前执行 `alembic upgrade head`；前端生产构建固定使用 `VITE_USE_MOCK=false`，并通过同源 `/api` 代理访问后端。

PostgreSQL 与上传文件分别保存在命名卷 `postgres_data` 和 `uploads_data` 中。停止服务使用 `docker compose down`；除非明确要销毁本地数据，不要附加 `-v`。

PostgreSQL 的可选宿主调试端口仅绑定 `127.0.0.1`。图片上传和生成结果会统一经过 Pillow decode、`verify()`、重新 `load()`、格式/扩展名/尺寸/像素数/大小校验，再以不透明文件名原子保存；HTTP `Content-Type` 不能替代图片有效性校验。

Qwen 图片编辑默认使用 `IMAGE_GEN_MODEL=qwen-image-2.0` 和固定 `IMAGE_GEN_OUTPUT_COUNT=3`，调用官方同步多模态接口。参考图只在请求内存中转换为 Base64 data URL，Provider 临时 URL 下载验证后立即本地化；Key、参考图和 Base64 不进入日志或审计。
中国大陆 P0 的 `IMAGE_GEN_API_BASE` 必须使用 `https://<Workspace ID>.cn-beijing.maas.aliyuncs.com/api/v1` 格式的华北 2 Workspace 专属地址；旧公共 DashScope 图片基址、HTTP、其他地域和其他图片模型会在应用启动时明确报错。`IMAGE_GEN_API_KEY` 必须属于该 Workspace，Workspace ID、API Key 与地域必须匹配；示例中的 `YOUR_WORKSPACE_ID` 必须替换为实际值。

## Demo 初始化

Demo 初始化命令是幂等的，账号密码必须由环境变量显式传入；仓库和生产代码不内置弱密码。容器启动后执行：

```powershell
docker compose exec `
  -e DEMO_ADMIN_PASSWORD="<strong-admin-password>" `
  -e DEMO_OPERATOR_PASSWORD="<strong-operator-password>" `
  -e DEMO_SERVICE_PASSWORD="<strong-service-password>" `
  backend python scripts/init_demo.py
```

初始化完成后可分别使用 `admin`、`operator_content` 和 `customer_service` 角色验证工作台权限。固定 Demo 数据只用于封闭回归和演示，不代表真实线上效果或泛化准确率。

## 本地验证

```powershell
backend\.venv\Scripts\python.exe -m pytest -q
Set-Location frontend
npm test -- --run
$env:VITE_USE_MOCK="false"; npm run build
Set-Location ..
docker compose config
```

自动测试会清空 Provider Key、阻断外网，并仅使用 mock/stub。图片质量 `C-Q05` 需要人工验收；任何真实模型 Smoke Test 都必须单独授权。

Docker 完整闭环使用 `backend/scripts/run_isolated_p0_acceptance.py` 创建随机 PostgreSQL 验证库，执行完成后自动删除验证库与本次上传文件，避免污染正式 Demo 数据。M4.1 证据见 [Gate 报告](docs/业务核心系统/M4.1_Gate报告.md)。