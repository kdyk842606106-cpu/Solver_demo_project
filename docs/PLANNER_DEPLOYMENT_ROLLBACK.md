# Planner 适配部署、恢复与回退

## 1. 发布前

1. 记录应用提交号、数据库当前 Alembic 版本和 `PLANNER_PROJECT_PATH`；
2. 对 PostgreSQL 做可恢复备份，并验证备份文件可读取；
3. 执行全量后端测试、Planner 64 项测试、前端生产构建和 Playwright 验收；
4. 先调用旧数据迁移预览，阻塞项为零后才允许执行；
5. 确认前端菜单只有“Planner 数据”和“多引擎求解”。

## 2. 升级

```powershell
python -m alembic upgrade 015_planner_scenario
```

升级只新增 `planner_scenario` 和 `planner_run`，不修改旧业务表。随后设置：

```env
PLANNER_PROJECT_PATH=D:\planner
```

启动后检查 `/health`、`/api/v1/planner-runs/capabilities`，再用黄金场景执行一次 `ALL`。

## 3. 旧数据迁移

1. `GET /api/v1/planner-migrations/legacy/preview` 获取创建、跳过、警告和阻塞明细；
2. 处理全部 blocker；
3. 确认已有可恢复备份；
4. `POST /api/v1/planner-migrations/legacy`，同时提交 `confirm: true` 与 `backup_acknowledged: true`；
5. 对账预览和执行数量，并复跑统一校验及黄金路径。

迁移只创建新 Planner 场景，旧表保持可读且不被修改。不支持的数据留在旧表并进入报告。

## 4. 应用回退

若新页面或求解桥故障，先回退应用代码到发布前提交。因为旧表未改，旧系统可继续读取原数据；已创建的 Planner 场景保留在新表中，待修复后继续使用。

若必须回退数据库结构，在确认不再需要新场景和运行记录、并完成导出/备份后执行：

```powershell
python -m alembic downgrade 014_body_reference_unification
```

该操作删除 `planner_run` 和 `planner_scenario`，其中数据只能从发布前备份或导出的 JSON/Excel 恢复。禁止在未备份时执行数据库回退。

## 5. 故障定位

- `planner_available: false`：检查 `PLANNER_PROJECT_PATH` 下是否存在 `planner_experiment/scenario.py`；
- 场景提交 409：页面基线已过期，取消草稿并重新载入；
- 场景提交 422：按稳定 `error_code` 和 `issues.object_id` 定位业务对象；
- 单引擎失败：查看该引擎诊断，其他已验证结果仍会保留；
- 镜像不一致：以活动包侧为权威重新导出，不允许手工修改状态包。

