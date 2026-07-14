import { expect, test } from '@playwright/test'
import { BASE_SCHEDULE, createMockRouteHandler } from '../fixtures/mock-api'

const weeklyWindows = Array.from({ length: 7 }, (_, index) => index + 1).flatMap((weekday) => [
  {
    weekday,
    start_time: '08:00',
    end_time: '20:00',
    spans_next_day: false,
    shift_code: 'DAY_SHIFT',
    shift_name: '白班',
  },
  {
    weekday,
    start_time: '20:00',
    end_time: '08:00',
    spans_next_day: true,
    shift_code: 'NIGHT_SHIFT',
    shift_name: '夜班',
  },
])

test('system default dual-shift calendar is grouped by named shift', async ({ page }) => {
  const fallback = createMockRouteHandler(BASE_SCHEDULE)
  await page.route(/\/(health|api\/v1\/)/, async (route, request) => {
    if (request.url().endsWith('/api/v1/work-calendars')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{
          id: 10,
          code: 'DEFAULT_DUAL_SHIFT',
          name: '默认白夜双班日历',
          description: null,
          is_active: true,
          is_system_default: true,
          current_revision_id: 20,
          created_at: '2026-07-13T00:00:00Z',
          updated_at: '2026-07-13T00:00:00Z',
          current_revision: {
            id: 20,
            work_calendar_id: 10,
            revision_no: 1,
            timezone: 'Asia/Shanghai',
            weekly_windows: weeklyWindows,
            date_exceptions: [],
            checksum: 'test',
            created_at: '2026-07-13T00:00:00Z',
          },
        }]),
      })
      return
    }
    await fallback(route, request)
  })

  await page.goto('/')
  await page.getByRole('tab', { name: '工作日历' }).click()
  await expect(page.getByText('默认白夜双班日历', { exact: true })).toBeVisible()
  await expect(page.getByText('系统默认', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: '编辑' }).click()
  await expect(page.locator('.schedule-group')).toHaveCount(2)
  await expect(page.locator('input[placeholder="班次编码，如 DAY_SHIFT"]').first()).toHaveValue('DAY_SHIFT')
  await expect(page.locator('input[placeholder="班次名称，如 白班"]').first()).toHaveValue('白班')
  await expect(page.locator('input[placeholder="班次编码，如 DAY_SHIFT"]').nth(1)).toHaveValue('NIGHT_SHIFT')
  await expect(page.locator('input[placeholder="班次名称，如 白班"]').nth(1)).toHaveValue('夜班')
})
