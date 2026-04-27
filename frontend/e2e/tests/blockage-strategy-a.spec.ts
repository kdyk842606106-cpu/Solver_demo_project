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
