import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

async function showRun(page: Page, run: any, progress?: () => object) {
  const snapshot = run.request.effective_scenario_snapshot;
  const project = structuredClone(snapshot);
  project.activities.forEach((a: any) => { a.name = "当前名称已改动"; });
  await page.route("**/api/v1/**", async route => {
    expect(route.request().method()).toBe("GET");
    const path = new URL(route.request().url()).pathname.replace("/api/v1/", "");
    const data = path === "planner-scenarios" ? [project] :
      path.startsWith("planner-scenarios/") ? { scenario: project, revision: 1 } :
      path === "planner-runs/capabilities" ? { planner_available: true, async_runs_supported: true } :
      path === "planner-runs" ? [run] : path.endsWith("/progress") ? progress?.() ?? {
        run_id: run.id, scenario_id: run.scenario_id, job_status: "FINISHED", status: run.status, plan_version: 1, progress_version: 1,
      } : run;
    await route.fulfill({ json: data });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "联合求解", exact: true }).click();
  await page.getByRole("tab", { name: "甘特图" }).click();
  await expect(page.getByTestId("gantt-execution").first()).toBeVisible();
}

function sample() {
  const project = { id: "gantt-test", name: "甘特图验收", revision: 1, start_time: 100,
    activities: ["a", "b"].map(id => ({ id, name: id === "a" ? "精密装配" : "功能调测", duration: 10, resource_reqs: { crew: 1 } })),
    resources: [{ id: "crew", name: "装配组", kind: "crew", capacity: 2 }], states: [],
    initial_state_ids: [], goal_state_ids: [], activity_packages: [], activity_package_memberships: [],
    working_intervals: [[100, 130], [190, 400]],
  };
  const candidate = { validator_status: "VALID", metrics: { makespan: 120, execution_count: 3 }, executions: [
    { activity_id: "a", ordinal: 1, start_time: 103, end_time: 113 },
    { activity_id: "b", ordinal: 1, start_time: 105, end_time: 195 },
    { activity_id: "a", ordinal: 2, start_time: 210, end_time: 220 },
  ] };
  return { id: "gantt-run", scenario_id: project.id, job_status: "FINISHED", status: "OPTIMAL", created_at: new Date().toISOString(),
    request: { effective_scenario_snapshot: project, display_start_at: "2026-11-05T11:30:00+08:00", display_timezone: "Asia/Shanghai" },
    result: { results: { JOINT_CP_SAT: { status: "OPTIMAL", paths: [candidate] } } },
  };
}

test("甘特组件：分钟精度、并行重复、暂停空档、历史名称和只读", async ({ browser }, testInfo) => {
  // Different browser and run timezones must not change labels or elapsed widths.
  const context = await browser.newContext({ timezoneId: "America/New_York" });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  await showRun(page, sample());
  const bars = page.getByTestId("gantt-execution");
  await expect(bars).toHaveCount(3);
  await expect(bars.first()).toHaveAttribute("title", /精密装配 · 第 1 次\n2026\/11\/05 11:33 → 2026\/11\/05 11:43/);
  await expect(bars.last()).toHaveAttribute("title", /精密装配 · 第 2 次/);
  await expect(bars.nth(1).locator(".execution-work")).toHaveCount(2);
  const segments = bars.nth(1).locator(".execution-work");
  await expect(segments.first()).toHaveAttribute("data-end-minute", "130");
  await expect(segments.last()).toHaveAttribute("data-start-minute", "190");
  await page.getByLabel("甘特图时间刻度").selectOption("60");
  // The component can stretch a short timeline to fit the viewport. Verify
  // elapsed-time ratios and the two-minute parallel offset, not a fixed zoom.
  const first = (await bars.first().boundingBox())!;
  const parallel = (await bars.nth(1).boundingBox())!;
  expect(first.width).toBeGreaterThan(0);
  expect(Math.abs(first.width - parallel.width / 9)).toBeLessThan(1);
  expect(parallel.x - first.x).toBeCloseTo(first.width * 2 / 10, 0);
  expect(parallel.y).toBeGreaterThan(first.y);
  await page.mouse.move(first.x + 4, first.y + 8); await page.mouse.down();
  await page.mouse.move(first.x + 90, first.y + 8); await page.mouse.up();
  expect((await bars.first().boundingBox())!.x).toBeCloseTo(first.x, 1);
  expect(errors).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("gantt-component.png"), fullPage: true });
  await context.close();
});

for (const [name, file, count] of [
  ["20 活动", "../output/occurrence-pruning/assembly20.json", 20],
  ["150 活动", "../output/fixtures/night-calendar-150/result.json", 150],
] as const) {
  test(`历史真实求解结果：${name}、虚拟滚动与缩放`, async ({ page }, testInfo) => {
    test.skip(!process.env.GANTT_REAL_FIXTURES, "Optional local frozen solver results");
    const run = JSON.parse(readFileSync(file, "utf8"));
    await showRun(page, run);
    const chart = page.getByRole("region", { name: "执行实例甘特图" });
    await expect(chart).toHaveAttribute("data-execution-count", String(count));
    await page.getByLabel("甘特图时间刻度").selectOption("60");
    await expect(page.getByLabel("甘特图时间刻度")).toHaveValue("60");
    await chart.scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath(`gantt-${count}.png`), fullPage: true });
    // Exercise component vertical scrolling to see the final execution.
    const scroll = chart.locator(".wx-gantt");
    await expect(scroll).toHaveCount(1);
    await scroll.evaluate(n => { n.scrollTop = n.scrollHeight; n.dispatchEvent(new Event("scroll")); });
    await expect.poll(() => scroll.evaluate(n => n.scrollTop)).toBeGreaterThan(0);
    await page.getByRole("button", { name: "回到起点" }).click();
    await expect(page.getByTestId("gantt-execution").first()).toBeVisible();
  });
}

test("改善方案和仅指标更新保留缩放、水平及垂直滚动", async ({ page }) => {
  const run = sample();
  run.job_status = "RUNNING"; run.status = "RUNNING";
  const candidate = run.result.results.JOINT_CP_SAT.paths[0];
  (run as { result?: unknown }).result = undefined;
  run.request.effective_scenario_snapshot.working_intervals = [[100, 6000]];
  candidate.metrics = { makespan: 4200, execution_count: 40 };
  candidate.executions = Array.from({ length: 40 }, (_, i) => ({ activity_id: "a", ordinal: i + 1, start_time: 100 + i * 100, end_time: 140 + i * 100 }));
  let version = 1, calls = 0, sentVersion = 0;
  await page.clock.install();
  await showRun(page, run, () => {
    const updated = sentVersion !== version; sentVersion = version;
    return { run_id: run.id, scenario_id: run.scenario_id, job_status: "RUNNING", status: "RUNNING",
    progress_version: ++calls, plan_version: version, candidate: updated ? candidate : null,
    metrics: { phase: "MAKESPAN", branches: calls * 20, candidate_count: calls },
  }; });
  await page.getByLabel("甘特图时间刻度").selectOption("60");
  const vertical = page.locator(".schedule-gantt .wx-gantt");
  const horizontal = page.locator(".schedule-gantt .wx-chart");
  await page.clock.runFor(50);
  await vertical.evaluate(n => { n.scrollTop = 380; n.dispatchEvent(new Event("scroll")); });
  await horizontal.evaluate(n => { n.scrollLeft = 2600; n.dispatchEvent(new Event("scroll")); });
  await expect.poll(() => vertical.evaluate(n => n.scrollTop)).toBe(380);
  await expect.poll(() => horizontal.evaluate(n => n.scrollLeft)).toBe(2600);
  const before = await page.getByTestId("gantt-execution").first().elementHandle();
  await page.clock.fastForward(5000);
  await expect.poll(() => calls).toBe(2);
  expect(await before!.evaluate(n => n.isConnected)).toBe(true);
  version = 2; candidate.executions.pop(); candidate.metrics.execution_count = 39;
  await page.clock.fastForward(5000);
  await expect(page.getByRole("region", { name: "执行实例甘特图" })).toHaveAttribute("data-execution-count", "39");
  await page.clock.runFor(50);
  await expect(page.getByLabel("甘特图时间刻度")).toHaveValue("60");
  await expect.poll(() => vertical.evaluate(n => n.scrollTop)).toBe(380);
  await expect.poll(() => horizontal.evaluate(n => n.scrollLeft)).toBe(2600);
});
