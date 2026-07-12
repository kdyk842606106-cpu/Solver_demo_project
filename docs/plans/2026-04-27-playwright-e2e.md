# Playwright E2E 阻塞场景测试 — Implementation Plan
> **For agent:** REQUIRED SUB-SKILL: Use Section 4 or Section 5 to implement this plan.
> **Goal:** 在前端建立 Playwright 浏览器自动化测试，覆盖阻塞策略 A/B 的完整 UI 流程。
> **Architecture:** Playwright + Vue3/Vite 前端 + FastAPI 后端（SQLite 测试模式）。globalSetup 统一启动后端（seed 后）和前端 devServer，测试用例通过 UI 交互验证端到端行为。
> **Tech Stack:** @playwright/test, TypeScript, FastAPI, SQLite, Element Plus, ECharts

---

## 前置状态
- 当前在分支 `feat/playwright-e2e`（已从 main 的 `88ed799` 切出）
- 前端：Vue 3 + Element Plus + Vite (port 5173, proxy `/api` → localhost:8000)
- 后端：FastAPI + async SQLAlchemy，默认 PostgreSQL，支持 `DATABASE_URL` 覆盖
- 现有 API E2E 在 `tests/e2e/`（pytest + httpx + SQLite in-memory）
- 阻塞 UI 组件：`frontend/src/components/BlockageDialog.vue`

---

## Task 1: Playwright 基建安装
**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/playwright.config.ts`
- Create: `frontend/.gitignore`（追加）
**Step 1:** 在前端目录安装 Playwright
```bash
cd /mnt/e/Solver_demo_project/frontend
npm install -D @playwright/test
npx playwright install chromium
```
**Step 2:** 向 `package.json` 的 `scripts` 追加：
```json
"test:e2e": "playwright test",
"test:e2e:ui": "playwright test --ui"
```
**Step 3:** 创建 `frontend/playwright.config.ts`
```typescript
import { defineConfig, devices } from '@playwright/test'
import path from 'path'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: [
    {
      command: 'cd /mnt/e/Solver_demo_project && DATABASE_URL=sqlite+aiosqlite:///./frontend/e2e/test.db uvicorn app.main:app --port 8000',
      url: 'http://localhost:8000/health',
      timeout: 120 * 1000,
      reuseExistingServer: !process.env.CI,
      env: {
        DATABASE_URL: 'sqlite+aiosqlite:///./frontend/e2e/test.db',
      },
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      timeout: 120 * 1000,
      reuseExistingServer: !process.env.CI,
    },
  ],
})
```
**Step 4:** 追加 `frontend/.gitignore`：
```
/test-results/
/playwright-report/
/playwright/.cache/
```
**Step 5:** 运行安装验证
```bash
cd /mnt/e/Solver_demo_project/frontend
npm install
npx playwright install chromium
```
**预期输出：** 无报错，chromium 安装完成。

---

## Task 2: 后端测试数据 Seed 脚本
**Files:**
- Create: `frontend/e2e/seed.py`
**Step 1:** 创建 Python seed 脚本，复用现有 `tests/e2e/conftest.py` 的 seed 函数直接写入 SQLite 文件：
```python
"""Seed SQLite DB for Playwright E2E tests."""
import asyncio
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models import Base
from tests.e2e.conftest import seed_base_data, seed_op_rules, seed_serial_states, seed_parallel_states

DB_PATH = Path(__file__).with_suffix('.db')
ASYNC_URL = f"sqlite+aiosqlite:///{DB_PATH}"


async def main():
    engine = create_async_engine(ASYNC_URL, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        await seed_base_data(session)
        await seed_op_rules(session)
        await seed_serial_states(session)
        # Also seed parallel states for potential future tests
        # await seed_parallel_states(session)  # uncomment if needed
        await session.commit()

    print(f"Seeded: {DB_PATH}")


if __name__ == '__main__':
    asyncio.run(main())
```
**Step 2:** 手动验证 seed
```bash
cd /mnt/e/Solver_demo_project
python frontend/e2e/seed.py
```
**预期输出：** `Seeded: /mnt/e/Solver_demo_project/frontend/e2e/test.db`

---

## Task 3: 基础求解 UI 测试
**Files:**
- Create: `frontend/e2e/tests/solve.spec.ts`
**Step 1:** 创建第一个 Playwright 测试，验证页面加载 + 求解流程：
```typescript
import { test, expect } from '@playwright/test'

test.describe('Solve Page — Happy Path', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    // Wait for page to load machine list
    await page.waitForSelector('.el-select', { timeout: 10000 })
  })

  test('page loads and shows solve form', async ({ page }) => {
    await expect(page.locator('h2')).toContainText('求解')
    await expect(page.locator('.el-form')).toBeVisible()
  })

  test('can select machine and states', async ({ page }) => {
    // Select machine
    await page.click('.el-form-item:nth-child(1) .el-select')
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe")')

    // States should auto-populate after machine selection
    await page.waitForTimeout(500)
    const currentState = await page.inputValue('.el-form-item:nth-child(2) .el-select .el-input__inner')
    const targetState = await page.inputValue('.el-form-item:nth-child(3) .el-select .el-input__inner')
    expect(currentState).not.toBe('')
    expect(targetState).not.toBe('')
  })

  test('full solve flow produces schedule', async ({ page }) => {
    // Select machine
    await page.click('.el-form-item:nth-child(1) .el-select')
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe")')
    await page.waitForTimeout(500)

    // Click solve
    await page.click('button:has-text("开始求解")')

    // Wait for result
    await page.waitForSelector('.el-table__body tr', { timeout: 30000 })

    // Verify tasks appear
    const rows = page.locator('.el-table__body tr')
    await expect(rows).toHaveCount(2) // serial: WARMUP + CALIBRATE

    // Verify Gantt chart renders
    await expect(page.locator('text=排程 Gantt 图')).toBeVisible()
  })
})
```
**Step 2:** 运行测试验证 RED（预期失败，因为 seed 可能在 webServer 启动后才需要调整）
```bash
cd /mnt/e/Solver_demo_project/frontend
npx playwright test e2e/tests/solve.spec.ts --headed
```
**预期输出：** 测试可能因 Element Plus 选择器问题失败，需要调整定位器（这是 RED 阶段，记录失败原因）。

---

## Task 4: 阻塞策略 A E2E 测试
**Files:**
- Create: `frontend/e2e/tests/blockage-strategy-a.spec.ts`
**Step 1:** 创建 Strategy A 测试：
```typescript
import { test, expect } from '@playwright/test'

test.describe('Blockage — Strategy A (not_before)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('.el-select', { timeout: 10000 })

    // Run initial solve
    await page.click('.el-form-item:nth-child(1) .el-select')
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe")')
    await page.waitForTimeout(500)
    await page.click('button:has-text("开始求解")')
    await page.waitForSelector('.el-table__body tr', { timeout: 30000 })
  })

  test('can apply not_before and verify delayed task', async ({ page }) => {
    // Click "标记阻塞" on first task row
    const firstRow = page.locator('.el-table__body tr').first()
    await firstRow.locator('button:has-text("标记阻塞")').click()

    // BlockageDialog should open
    await page.waitForSelector('.el-dialog', { timeout: 5000 })
    await expect(page.locator('.el-dialog__title')).toContainText('标记阻塞并重排')

    // Select Strategy A
    await page.click('.el-radio:has-text("策略 A")')

    // Set not_before_offset to 25
    await page.fill('.el-input-number input', '25')

    // Submit
    await page.click('.el-dialog__footer button:has-text("提交重排")')

    // Wait for replan result
    await page.waitForSelector('.el-message--success', { timeout: 30000 })

    // Verify new schedule has delayed task
    await page.waitForTimeout(500)
    const rows = page.locator('.el-table__body tr')
    const delayedTag = rows.locator('.el-tag:has-text("延后")')
    await expect(delayedTag.first()).toBeVisible()

    // Verify not_before column shows 25m
    const notBeforeCell = rows.filter({ hasText: '延后' }).locator('td').nth(7) // not_before column
    await expect(notBeforeCell).toContainText('25m')
  })
})
```
**Step 2:** 运行测试
```bash
cd /mnt/e/Solver_demo_project/frontend
npx playwright test e2e/tests/blockage-strategy-a.spec.ts --headed
```

---

## Task 5: 阻塞策略 B E2E 测试
**Files:**
- Create: `frontend/e2e/tests/blockage-strategy-b.spec.ts`
**Step 1:** 需要先在 seed 中添加 `blockage_reason` feature 和 repair rule。因此先修改 `frontend/e2e/seed.py`：
```python
# 在 seed.py 中追加以下内容到 main() 之后 seed 逻辑：
from tests.integration.test_blockage_strategies import _seed_repair_strategy_data

# 在 seed_serial_states 之后：
await _seed_repair_strategy_data(session)
```
但 `_seed_repair_strategy_data` 使用 id=3,4 的 MachineState，可能与 serial_states 的 id=1,2 冲突？不冲突，id 不同。但 machine_id=1 复用，feature_key 可能重复定义。

更安全的方式：直接内联 repair seed 到 seed.py，避免 import integration 的函数（因为那些可能依赖特定 state id）。

**Step 2:** 修改 seed.py 追加 repair 数据：
```python
from app.db.models import StateFeatureDef

async def seed_repair_data(session):
    session.add(StateFeatureDef(
        id=50, machine_type_id=1, feature_key="blockage_reason",
        feature_name="Blockage Reason", value_type="string"
    ))
    # ... (repair rule + states with blockage_reason)
```

**Step 3:** 创建 Strategy B 测试：
```typescript
import { test, expect } from '@playwright/test'

test.describe('Blockage — Strategy B (repair insertion)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('.el-select', { timeout: 10000 })

    // For Strategy B we need a state that includes blockage_reason.
    // The seed data provides state_id=3 (current with mechanical_wear) and state_id=4 (target).
    // We must manually select these states since auto-select picks id=1,2.
    await page.click('.el-form-item:nth-child(1) .el-select')
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe")')
    await page.waitForTimeout(500)

    // Manually select current state with blockage
    await page.click('.el-form-item:nth-child(2) .el-select')
    await page.click('.el-select-dropdown__item:has-text("Cold Standby with Blockage")')

    // Manually select target state
    await page.click('.el-form-item:nth-child(3) .el-select')
    await page.click('.el-select-dropdown__item:has-text("Ready for Production with Blockage")')

    await page.click('button:has-text("开始求解")')
    await page.waitForSelector('.el-table__body tr', { timeout: 30000 })
  })

  test('repair task is inserted and marked red', async ({ page }) => {
    // Click blockage on any normal task
    const normalRow = page.locator('.el-table__body tr').first()
    await normalRow.locator('button:has-text("标记阻塞")').click()

    await page.waitForSelector('.el-dialog', { timeout: 5000 })

    // Select Strategy B
    await page.click('.el-radio:has-text("策略 B")')

    // Select blockage reason from dropdown
    await page.click('.el-form-item:has-text("阻塞原因") .el-select')
    await page.click('.el-select-dropdown__item:has-text("mechanical_wear")')

    await page.click('.el-dialog__footer button:has-text("提交重排")')
    await page.waitForSelector('.el-message--success', { timeout: 30000 })

    // Verify repair task appears with red "维修" tag
    await page.waitForTimeout(500)
    const repairTag = page.locator('.el-table__body tr .el-tag--danger:has-text("维修")')
    await expect(repairTag.first()).toBeVisible()

    // Verify OP_REPAIR_WORN row exists
    const repairRow = page.locator('.el-table__body tr:has-text("OP_REPAIR_WORN")')
    await expect(repairRow).toBeVisible()
  })
})
```

---

## Task 6: 运行全部 E2E 并修复选择器问题
**Files:**
- Modify: 上述 `.spec.ts` 文件（按需调整定位器）
**Step 1:** 运行全部测试
```bash
cd /mnt/e/Solver_demo_project/frontend
npx playwright test e2e/tests/ --reporter=list
```
**Step 2:** 根据失败日志调整 Element Plus 组件的 Playwright 定位器（常见修复）：
- `el-select` 点击后等待 dropdown 动画：`.el-select-dropdown` + `waitForVisible`
- `el-dialog` 用 `page.locator('.el-dialog').first()` 而非全局
- `el-input-number` 用 `fill` 前先 `click` 清空
- 表格行用 `page.locator('table tbody tr')` 更稳定

---

## Task 7: 提交并收尾
**Step 1:** 提交所有新文件
```bash
cd /mnt/e/Solver_demo_project
git add frontend/e2e/ frontend/playwright.config.ts frontend/package.json frontend/.gitignore
git commit -m "feat(e2e): Playwright browser automation for blockage scenarios

- Install @playwright/test + Chromium
- Configure dual webServer (backend SQLite + frontend Vite)
- Add seed.py for SQLite test DB with repair data
- Add solve.spec.ts: basic solve flow validation
- Add blockage-strategy-a.spec.ts: not_before UI test
- Add blockage-strategy-b.spec.ts: repair insertion UI test
- Add npm scripts: test:e2e, test:e2e:ui"
```

---

## 风险与应对
| 风险 | 应对 |
|------|------|
| Element Plus 选择器不稳定 | 优先用 `getByRole`, `getByText`, `getByLabel`（Playwright 内置定位器），少用 CSS class |
| webServer 启动顺序/超时 | playwright.config.ts 里后端先启动（health check），前端后启动；timeout 120s |
| SQLite 并发问题 | 单 worker (`workers: 1`) 避免并发写同一个 db 文件 |
| ECharts canvas 难以断言 | 不测 canvas 像素，测 DOM 中的任务表格数据 |
| seed 数据状态冲突 | seed.py 每次 drop_all + create_all，确保干净基线 |

---

## 执行方式建议
推荐 **Subagent-Driven Development**（Section 5）：
- Task 1-2（基建）可在一个 subagent 完成
- Task 3-5（测试用例）每个一个 subagent，串行执行（因为共享前端状态）
- Task 6-7（调试验证 + 提交）由本 session 完成

**立即开始？** 还是你需要先调整计划中的某些细节？
