import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";

test("五秒轮询、相同工期减少执行、断线恢复和终态停止", async ({ page }) => {
  const project = { id: "p", name: "实时验收", revision: 1, activities: [], resources: [],
    states: [], initial_state_ids: [], goal_state_ids: [], activity_packages: [], activity_package_memberships: [] };
  const run = { id: "r", scenario_id: "p", status: "RUNNING", job_status: "RUNNING",
    started_at: new Date().toISOString(), created_at: new Date().toISOString(),
    request: { effective_scenario_snapshot: project } };
  const plan = (count: number) => ({ validator_status: "VALID", metrics: { makespan: 10, execution_count: count },
    executions: Array.from({length: count}, (_, i) => ({ activity_id: "a", ordinal: i+1, start_time: i, end_time: i+1 })) });
  let version = 1, offline = false, failed = false, calls = 0;
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url()), path = url.pathname.replace("/api/v1/", "");
    let data;
    const other = {...project, id:"p2", name:"其他项目"};
    if (path === "planner-scenarios") data = [project,other];
    if (path === "planner-scenarios/p2") data = {scenario:other, revision:1};
    if (path === "planner-scenarios/p") data = { scenario: project, revision: 1 };
    if (path === "planner-runs/capabilities") data = { planner_available: true, async_runs_supported: true };
    if (path === "planner-runs") data = url.searchParams.get("scenario_id") === "p2" ? [] : [run];
    if (path === "planner-runs/r") data = { ...run, job_status: failed ? "FAILED" : "RUNNING",
      status: failed ? "ERROR" : "RUNNING", error_message: failed ? "执行中断" : null };
    if (path === "planner-runs/r/progress") {
      calls++;
      if (offline) return route.abort();
      const known = Number(url.searchParams.get("known_plan_version"));
      data = { run_id: "r", scenario_id: "p", job_status: failed ? "FAILED" : "RUNNING",
        status: failed ? "ERROR" : "RUNNING", started_at: run.started_at,
        plan_version: version, progress_version: calls, candidate: known === version ? null : plan(version===1 ? 5 : 2),
        metrics: {phase:"MAKESPAN", candidate_count:calls, branches:calls*10, best_makespan:10} };
    }
    await route.fulfill({ json: data });
  });
  await page.clock.install();
  await page.goto("/");
  await page.getByRole("button", {name:"联合求解",exact:true}).click();
  await page.getByRole("tab",{name:"甘特图"}).click();
  const rows = page.locator('[data-testid="gantt-execution"]');
  await expect(rows).toHaveCount(5);
  const first = await rows.first().elementHandle();
  await page.clock.fastForward(4000);
  expect(calls).toBe(1);
  await page.clock.fastForward(1000);
  await expect.poll(()=>calls).toBe(2);
  expect(await first!.evaluate(el=>el.isConnected)).toBe(true);
  offline = true;
  await page.clock.fastForward(5000);
  await expect(page.getByText(/状态查询失败/)).toBeVisible();
  await expect(rows).toHaveCount(5);
  offline = false; version = 2;
  await page.evaluate(()=>window.dispatchEvent(new Event("online")));
  await expect(rows).toHaveCount(2);
  await page.getByLabel("切换项目").click();
  await page.getByRole("menuitem",{name:"其他项目"}).click();
  await expect(page.getByText("尚未生成计划")).toBeVisible();
  await expect(rows).toHaveCount(0);
  await page.getByLabel("切换项目").click();
  await page.getByRole("menuitem",{name:"实时验收"}).click();
  await page.getByRole("tab",{name:"甘特图"}).click();
  await expect(rows).toHaveCount(2);
  failed = true;
  await page.clock.fastForward(5000);
  await expect(page.getByText("执行失败",{exact:true})).toBeVisible();
  await expect(rows).toHaveCount(2);
  const finalCalls = calls;
  await page.clock.fastForward(15000);
  expect(calls).toBe(finalCalls);
  await page.reload();
  await page.getByRole("button", {name:"联合求解",exact:true}).click();
  await page.getByRole("tab",{name:"甘特图"}).click();
  await expect(rows).toHaveCount(2);
});

test("真实 worker：150 活动中途显示甘特图并恢复最终结果", async ({ page, request }, testInfo) => {
  test.skip(!process.env.LIVE_PROGRESS_REQUEST, "Requires the installed acceptance fixture");
  const body = JSON.parse(readFileSync(process.env.LIVE_PROGRESS_REQUEST!, "utf8"));
  await page.addInitScript(id=>localStorage.setItem("planner-project",id),body.scenario_id);
  await page.goto("/");
  await expect(page.getByLabel("切换项目")).toHaveAttribute("data-project-id", body.scenario_id);
  const response = await request.post("/api/v1/planner-runs/async", { data:{...body,client_request_id:randomUUID()} });
  expect(response.status()).toBe(202);
  await page.getByRole("button",{name:"联合求解",exact:true}).click();
  await page.getByRole("tab",{name:"甘特图"}).click();
  await expect(page.getByRole("region", { name: "执行实例甘特图" })).toHaveAttribute("data-execution-count", "150");
  await expect(page.getByTestId("gantt-execution").first()).toBeVisible();
  await expect(page.getByText("求解中",{exact:true})).toBeVisible();
  await page.screenshot({path:testInfo.outputPath("live-gantt.png")});
  await page.reload();
  await page.getByRole("button",{name:"联合求解",exact:true}).click();
  await expect(page.locator(".result-banner")).toContainText("已证明最优",{timeout:60000});
  await expect(page.locator(".result-banner")).toContainText("3033 分钟");
  await expect(page.getByLabel("实时求解指标")).toContainText("搜索分支");
});
