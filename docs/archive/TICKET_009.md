# TICKET-009: 临时支持非 Docker 本地运行（Local PostgreSQL）

> 对应 STATE_V0.2.md → 运行与交付补充项（非架构变更）
> 前置依赖：TICKET-008 已完成
> 预估工作量：1 次对话

---

## 本次任务范围（只做这些）

为“另一个终端无法使用 Docker”的场景，补齐一套可运行流程，使系统在本机 PostgreSQL 下可完整启动与初始化。

目标：不依赖 Docker，也能完成 DB 连接、迁移、种子、后端、前端启动。

**不做**：不改求解算法、不改数据模型、不改 API 契约、不删除 Docker 方案。

---

## 子任务清单

```
[✅] A  新增本地启动脚本（无 Docker）
[✅] B  README 增加“Docker / 非 Docker”双路径说明
[✅] C  环境变量示例补充本地数据库使用说明
[⏳] D  最小回归验证并记录命令（受本机未启动 PostgreSQL 阻塞）
```

---

## 一、各子任务详细要求

### A：新增本地启动脚本（`start.local.bat`）

流程：

1. 检查 `.venv` / Python / npm 是否可用
2. 本地 PostgreSQL 连通性检查（`scripts/test_db_connection.py`）
3. `alembic upgrade head`
4. 依次加载 seeds `001` / `002` / `003`（失败仅警告，不中断）
5. 启动后端（`uvicorn`）
6. 启动前端（`npm run dev`）
7. 自动打开浏览器

约束：

- 不调用 Docker / Docker Compose
- 复用 `.env`（DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME）
- 输出信息明确标识“本地数据库模式”

### B：README 双路径说明

新增“非 Docker 启动（本地 PostgreSQL）”章节，明确：

- 本地 PostgreSQL 前置要求
- `.env` 配置方式
- 启动命令序列
- `start.local.bat` 快捷入口

### C：`.env.example` 注释增强

保持字段不变，补充说明：

- 默认值可用于本地 PostgreSQL
- `DATABASE_URL` / `DATABASE_URL_SYNC` 为可选覆盖

### D：最小回归验证

执行并记录以下命令（本次对话内）：

1. `python scripts/test_db_connection.py`
2. `alembic upgrade head`
3. `python scripts/load_seed_data.py --file seeds/003_v0.2_seed_data.sql`

本次执行结果：

- `python scripts/test_db_connection.py`：失败（`localhost:5432` 连接超时/拒绝）
- `alembic upgrade head`：失败（数据库未就绪，连接拒绝）
- `python scripts/load_seed_data.py --file seeds/003_v0.2_seed_data.sql`：失败（数据库未就绪，连接拒绝）

---

## 验收标准

```
✅ 不启动 Docker 的情况下可完成系统启动
✅ 新增 start.local.bat 且不包含 Docker 依赖
✅ README 明确给出非 Docker 运行路径
✅ .env.example 注释明确本地数据库使用方式
✅ 不影响原有 Docker 启动路径
```

---

## 本次不做（明确排除）

| 排除项 | 原因 |
|--------|------|
| 求解链路和算法 | 与本票目标无关 |
| 数据模型 / Alembic 结构调整 | 本票不涉及 schema 变更 |
| API 入参出参变更 | 本票只补运行方式 |
| 移除 Docker 脚本与编排 | 需保留原有交付路径 |
