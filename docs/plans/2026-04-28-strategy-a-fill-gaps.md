# Strategy A Fill-Gaps E2E 测试 — Implementation Plan
> **For agent:** REQUIRED SUB-SKILL: Use Section 5 to implement this plan.
> **Goal:** 验证当策略A（not_before）延后某个任务时，CP-SAT 调度器自动安排无影响的并行活动填充空窗期。
> **Architecture:** Playwright + 真实 FastAPI 后端（SQLite）+ Vue3 前端。后端真实求解 CP-SAT，前端验证 UI 展示。
> **Tech Stack:** @playwright/test, TypeScript, FastAPI, SQLite, CP-SAT (ortools)

---

## 场景设计

### 初始排程（无阻塞）
- 状态：temp=cold, clean=dirty, calib=off → temp=hot, clean=clean, calib=on
- Delta：temp(cold→hot), clean(dirty→clean), calib(off→on)
- 需要的操作：WARMUP(30min, TECHNICIAN) + CLEANING(20min, CLEANER) 可并行，然后 CALIBRATE(15min, TECHNICIAN)
- 理想排程：WARMUP(0-30) + CLEANING(0-20) 并行 → CALIBRATE(30-45)
- Makespan: 45

### 阻塞后排程（Strategy A, not_before=25）
- WARMUP 被延后到 not_before=25，即 25-55
- CLEANING 不受影响（不依赖 WARMUP），自动填充 0-20
- CALIBRATE 等待 WARMUP 完成，55-70
- 最终排程：CLEANING(0-20) → WARMUP(25-55) → CALIBRATE(55-70)
- Makespan: 70

### UI 验证点
1. 初始求解后表格显示 3 行（WARMUP + CLEANING + CALIBRATE）
2. WARMUP 和 CLEANING 的 start_min 相同（并行）
3. 阻塞后，某行显示 "延后" 标签
4. 延后的任务（WARMUP）start_min = 25
5. CLEANING 保持在 start_min = 0（自动填充空窗期）

---

## Task 1: 修改后端配置与 seed 数据
**Files:**
- Modify: `frontend/playwright.config.ts`
- Modify: `frontend/e2e/seed.py`

**Step 1:** 修改 `playwright.config.ts`，添加后端 webServer：
```typescript
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
```

**Step 2:** 修改 `seed.py`，在 `seed_serial_states` 后添加新的 `seed_parallel_scenario` 函数：
```python
async def seed_parallel_scenario(session):
    """Seed parallel scenario: WARMUP + CLEANING can run in parallel."""
    # New current state: Cold Dirty Standby
    session.add(MachineState(id=5, machine_id=1, state_type="current",
                             label="Cold Dirty Standby"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=5, feature_key="temperature_level",
                            feature_value="cold"),
        MachineStateFeature(machine_state_id=5, feature_key="clean_level",
                            feature_value="dirty"),
        MachineStateFeature(machine_state_id=5, feature_key="calibration",
                            feature_value="off"),
    ])

    # New target state: Hot Clean Calibrated
    session.add(MachineState(id=6, machine_id=1, state_type="target",
                             label="Hot Clean Calibrated"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=6, feature_key="temperature_level",
                            feature_value="hot"),
        MachineStateFeature(machine_state_id=6, feature_key="clean_level",
                            feature_value="clean"),
        MachineStateFeature(machine_state_id=6, feature_key="calibration",
                            feature_value="on"),
    ])
```
在 `main()` 中调用 `await seed_parallel_scenario(session)`。

**Step 3:** 验证 seed
```bash
cd /mnt/e/Solver_demo_project
python frontend/e2e/seed.py
# 预期：Seeded: /mnt/e/Solver_demo_project/frontend/e2e/test.db
```

---

## Task 2: 创建真实后端 E2E 测试
**Files:**
- Create: `frontend/e2e/tests/blockage-strategy-a-fill-gaps.spec.ts`

**Step 1:** 创建测试（不使用 mock，依赖真实后端 webServer）：
```typescript
import { test, expect } from '@playwright/test'

test.describe('Blockage — Strategy A fill gaps with parallel activities', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('.el-header', { timeout: 10000 })
    await page.click('.el-menu-item:has-text("求解")')
    await page.waitForSelector('h2:has-text("求解")', { timeout: 10000 })
    await page.waitForTimeout(2000)

    // Select machine
    await page.click('.el-select__wrapper')
    await page.waitForSelector('.el-select-dropdown', { timeout: 5000 })
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe (M-001)")')
    await page.waitForTimeout(500)
  })

  test('initial solve shows parallel warmup and cleaning', async ({ page }) => {
    // Click solve
    await page.click('button:has-text("开始求解")')
    await page.waitForSelector('.el-table__body tr', { timeout: 30000 })

    // Verify 3 tasks
    const rows = page.locator('.el-table__body tr')
    await expect(rows).toHaveCount(3)

    // Verify WARMUP and CLEANING both start at 0 (parallel)
    const warmupRow = rows.filter({ hasText: 'OP_WARMUP' })
    const cleaningRow = rows.filter({ hasText: 'OP_CLEANING' })
    const calibrateRow = rows.filter({ hasText: 'OP_CALIBRATE' })

    await expect(warmupRow).toBeVisible()
    await expect(cleaningRow).toBeVisible()
    await expect(calibrateRow).toBeVisible()

    // Check start times in table cells
    const warmupStart = await warmupRow.locator('td').nth(3).textContent()
    const cleaningStart = await cleaningRow.locator('td').nth(3).textContent()
    expect(warmupStart).toContain('0')
    expect(cleaningStart).toContain('0')
  })

  test('not_before delay pushes warmup, cleaning fills gap', async ({ page }) => {
    // Initial solve
    await page.click('button:has-text("开始求解")')
    await page.waitForSelector('.el-table__body tr', { timeout: 30000 })

    // Mark WARMUP as blocked
    const warmupRow = page.locator('.el-table__body tr').filter({ hasText: 'OP_WARMUP' })
    await warmupRow.locator('button:has-text("标记阻塞")').click()

    // Dialog opens
    await page.waitForSelector('.el-dialog', { timeout: 5000 })
    await expect(page.locator('.el-dialog__title')).toContainText('标记阻塞并重排')

    // Strategy A with 25 min offset
    await page.click('.el-radio:has-text("策略 A")')
    await page.fill('.el-input-number input', '25')
    await page.click('.el-dialog__footer button:has-text("提交重排")')

    // Wait for success
    await page.waitForSelector('.el-message--success', { timeout: 30000 })
    await page.waitForTimeout(500)

    // Verify new schedule
    const rows = page.locator('.el-table__body tr')
    await expect(rows).toHaveCount(3)

    // Find WARMUP row - should have "延后" tag and start at 25
    const warmupRowNew = rows.filter({ hasText: 'OP_WARMUP' })
    const delayedTag = warmupRowNew.locator('.el-tag:has-text("延后")')
    await expect(delayedTag).toBeVisible()

    const warmupStartNew = await warmupRowNew.locator('td').nth(3).textContent()
    expect(warmupStartNew).toContain('25')

    // CLEANING should still start at 0 (fills the gap)
    const cleaningRowNew = rows.filter({ hasText: 'OP_CLEANING' })
    const cleaningStartNew = await cleaningRowNew.locator('td').nth(3).textContent()
    expect(cleaningStartNew).toContain('0')

    // CALIBRATE should start after delayed WARMUP ends
    const calibrateRowNew = rows.filter({ hasText: 'OP_CALIBRATE' })
    const calibrateStartNew = await calibrateRowNew.locator('td').nth(3).textContent()
    expect(calibrateStartNew).toContain('55')  // 25 + 30
  })
})
```

**Step 2:** 运行测试（RED 阶段，预期因 Element Plus 选择器需要调整）
```bash
cd /mnt/e/Solver_demo_project/frontend
npx playwright test e2e/tests/blockage-strategy-a-fill-gaps.spec.ts --headed
```

---

## Task 3: 修复选择器并验证通过
**Files:**
- Modify: `frontend/e2e/tests/blockage-strategy-a-fill-gaps.spec.ts`（按需调整）

**Step 1:** 根据 RED 阶段的失败日志调整定位器。

常见调整：
- `el-input-number input` → `.el-input-number .el-input__inner`
- `td:nth(3)` 的 start_min 列索引可能需要确认
- `el-tag:has-text("延后")` 可能需要更精确的定位

**Step 2:** 运行验证
```bash
cd /mnt/e/Solver_demo_project/frontend
npx playwright test e2e/tests/blockage-strategy-a-fill-gaps.spec.ts --reporter=list
```
**预期：** 2 tests pass, 0 failures

---

## Task 4: 提交
**Step 1:** 提交
```bash
cd /mnt/e/Solver_demo_project
git add frontend/
git commit -m "feat(e2e): Strategy A fill-gaps with real backend solver

- Add parallel scenario states (id=5,6) to seed.py
- Configure dual webServer in playwright.config.ts (backend + frontend)
- Add blockage-strategy-a-fill-gaps.spec.ts
  - Verifies initial parallel WARMUP + CLEANING
  - Verifies not_before=25 delays WARMUP, CLEANING auto-fills gap 0-20
  - All assertions against real CP-SAT solver output"
```

---

## 风险
| 风险 | 应对 |
|------|------|
| 后端 webServer 启动失败 | 检查 DATABASE_URL 路径，使用绝对路径 |
| 表格列索引不对 | 先截图确认 start_min 列位置 |
| CP-SAT 求解结果与预期不同 | 检查 seed 数据和 op rule preconditions |
| 状态 5/6 与现有 id 冲突 | id=5,6 在现有 seed 中未使用，安全 |

---

## 执行建议
**Subagent-Driven（Section 5）**
- Task 1: 一个 subagent（修改配置 + seed）
- Task 2-3: 一个 subagent（写测试 + 调试选择器）
- Task 4: 本 session 执行
