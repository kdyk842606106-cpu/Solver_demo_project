import { test, expect } from '@playwright/test'
import { DELAYED_SCHEDULE, createMockRouteHandler } from '../fixtures/mock-api'

test.describe('Blockage — Strategy A (not_before)', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(/\/(health|api\/v1\/)/, createMockRouteHandler(DELAYED_SCHEDULE))
    await page.goto('/')
    await page.waitForSelector('.el-header', { timeout: 10000 })
    await page.click('.el-menu-item:has-text("求解")')
    await page.waitForSelector('h2:has-text("求解")', { timeout: 10000 })
    await page.waitForTimeout(2000)

    // Run initial solve
    await page.click('.el-select__wrapper')
    await page.waitForSelector('.el-select-dropdown', { timeout: 5000 })
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe (M-001)")')
    await page.waitForTimeout(500)
    await page.click('button:has-text("开始求解")')
    await page.click('.el-tabs__item:has-text("任务明细")')
    await page.waitForSelector('.el-table__body tr:visible', { timeout: 30000 })
  })

  test('can apply not_before and verify delayed task', async ({ page }) => {
    const firstRow = page.locator('.el-table__body tr:visible').first()
    await firstRow.locator('button:has-text("标记阻塞")').click()

    await page.waitForSelector('.el-dialog', { timeout: 5000 })
    await expect(page.locator('.el-dialog__title')).toContainText('标记阻塞并重排')

    await page.click('.el-radio:has-text("策略 A")')
    await page.fill('.el-input-number input', '25')
    await page.click('.el-dialog__footer button:has-text("提交重排")')

    await page.waitForSelector('.el-message--success', { timeout: 30000 })
    await page.waitForTimeout(500)

    const rows = page.locator('.el-table__body tr:visible')
    const delayedTag = rows.locator('.el-tag:has-text("延后")')
    await expect(delayedTag.first()).toBeVisible()
  })
})
