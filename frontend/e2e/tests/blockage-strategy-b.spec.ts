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
