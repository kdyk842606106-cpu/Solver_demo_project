// Read-only browser acceptance of the packaged frontend on the isolated port.
const { chromium, expect } = require('../frontend/node_modules/@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const out = process.argv[2] ? path.resolve(process.argv[2]) : path.resolve(__dirname, '../output/deploy-acceptance/final-validation');
const saved = JSON.parse(fs.readFileSync(path.join(out, 'imported.json'), 'utf8'));
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('response', response => {
      if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`);
    });
    await page.addInitScript(({ id, initial, target }) => {
      localStorage.setItem('planner-project', id);
      localStorage.setItem(`planner-form:${id}`, JSON.stringify({ initial, target, start: '2026-11-04T19:00' }));
    }, { id: saved.id, initial: saved.scenario.initial_state_ids, target: saved.scenario.goal_state_ids });
    await page.goto('http://127.0.0.1:8026/');
    await page.getByRole('button', { name: '联合求解', exact: true }).click();
    await expect(page.locator('.result-banner')).toContainText('150 步活动 · 总工期 3033 分钟 · 回放校验 VALID');
    for (const label of ['行吊作业独占', '调测作业独占', '精密易损吊装禁止夜班']) {
      await expect(page.getByLabel(label, { exact: true })).toBeChecked();
    }
    await expect(page.locator('.reference-result-table tbody tr')).toHaveCount(150);
    await page.getByRole('tab', { name: '求解指标', exact: true }).click();
    await expect(page.locator('.reference-metrics')).toContainText('已证明最优');
    await expect(page.locator('.reference-metrics')).toContainText('工作日历：');
    await page.screenshot({ path: path.join(out, 'metrics.png'), animations: 'disabled' });
    await page.getByRole('tab', { name: '甘特图', exact: true }).click();
    await expect(page.getByRole('region', { name: '执行实例甘特图' })).toHaveAttribute('data-execution-count', '150');
    await expect(page.getByTestId('gantt-execution').first()).toBeVisible();
    await page.getByLabel('甘特图时间刻度').selectOption('60');
    await page.screenshot({ path: path.join(out, 'gantt.png'), animations: 'disabled' });
    await page.reload();
    await page.getByRole('button', { name: '联合求解', exact: true }).click();
    await expect(page.locator('.result-banner')).toContainText('3033 分钟');
    if (errors.length) throw new Error(JSON.stringify(errors));
    fs.writeFileSync(path.join(out, 'browser.json'), JSON.stringify({
      status: 'PASS', url: 'http://127.0.0.1:8026/', activities: 150,
      rules_checked: 3, result_rows: 150, gantt_rows: 150, refresh_history: 'PASS', errors,
    }, null, 2));
    console.log('PASS: packaged frontend, 150 rows, Gantt, metrics, rules and refreshed history');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
