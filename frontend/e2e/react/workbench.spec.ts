import {
  test,
  expect,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

test("参考交互：列设置、侧边编辑、资源分区与状态树去重", async ({
  page,
  request,
}) => {
  const s = await seed(request, `参考交互 ${Date.now()}`);
  const response = await request.post(
    `/api/v1/planner-scenarios/${s.id}/draft-commit`,
    {
      data: {
        expected_revision: s.revision,
        operations: [
          {
            operation: "create_package",
            client_ref: "draft:root",
            payload: { name: "总装", parent_id: null },
          },
          {
            operation: "create_package",
            client_ref: "draft:left",
            payload: { name: "装配", parent_id: "draft:root" },
          },
          {
            operation: "create_package",
            client_ref: "draft:right",
            payload: { name: "验收", parent_id: "draft:root" },
          },
          {
            operation: "add_membership",
            client_ref: "draft:m1",
            payload: {
              package_id: "draft:left",
              activity_id: s.activities[0].id,
            },
          },
          {
            operation: "add_membership",
            client_ref: "draft:m2",
            payload: {
              package_id: "draft:right",
              activity_id: s.activities[0].id,
            },
          },
          {
            operation: "add_membership",
            client_ref: "draft:m3",
            payload: {
              package_id: "draft:right",
              activity_id: s.activities[1].id,
            },
          },
        ],
      },
    },
  );
  expect(response.ok(), await response.text()).toBeTruthy();
  const updated = (await response.json()).scenario;
  await openProject(page, s.id);
  await page
    .getByLabel("按活动包筛选")
    .selectOption(
      updated.activity_packages.find((p: { name: string }) => p.name === "装配")
        .id,
    );
  await expect(page.locator(".reference-activity-table tbody tr")).toHaveCount(
    1,
  );
  await page.getByRole("button", { name: "重置", exact: true }).click();
  await expect(page.locator(".reference-activity-table tbody tr")).toHaveCount(
    2,
  );
  await page.locator(".column-settings summary").click();
  await page
    .locator(".column-options")
    .getByLabel("破坏效果", { exact: true })
    .uncheck();
  await expect(
    page.getByRole("columnheader", { name: "破坏效果", exact: true }),
  ).toHaveCount(0);
  await page.reload();
  await expect(
    page.getByRole("columnheader", { name: "破坏效果", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "编辑并行活动甲", exact: true })
    .click();
  await expect
    .poll(async () => {
      const drawer = await page.getByRole("dialog").boundingBox();
      return Math.round(drawer!.x + drawer!.width);
    })
    .toBe(1440);
  await page.getByRole("button", { name: "关闭", exact: true }).click();
  await page.getByLabel("切换项目").click();
  await expect(page.getByRole("menu")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);
  await page.getByRole("button", { name: "资源管理", exact: true }).click();
  await expect(page.locator(".reference-resource-panel")).toHaveCount(5);
  await page.getByRole("button", { name: "联合求解", exact: true }).click();
  await page.getByRole("button", { name: "目标状态", exact: true }).click();
  const menu = page.getByRole("group", { name: "目标状态层级选项" });
  await menu.getByRole("button", { name: "展开全部" }).click();
  await menu.getByLabel("选择总装下全部状态", { exact: true }).check();
  await expect(menu.locator("footer")).toContainText("3 个已选状态");
  await menu.getByLabel("并行活动甲完成", { exact: true }).first().uncheck();
  await expect(
    menu.getByLabel("选择总装下全部状态", { exact: true }),
  ).toHaveJSProperty("indeterminate", true);
  await expect(
    menu.getByLabel("并行活动甲完成", { exact: true }).last(),
  ).not.toBeChecked();
  await expect(menu.locator("footer")).toContainText("2 个已选状态");
  await menu.getByRole("button", { name: "清空", exact: true }).click();
  await expect(menu.locator("footer")).toContainText("0 个已选状态");
  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
});
const screenshotPath = (file: string) =>
  `${test.info().project.outputDir}/${file}`;

test("自动执行上限：无需填写，覆盖旧上限并冻结到运行快照", async ({
  page,
  request,
}) => {
  const p = await createProject(request, `自动执行规模 ${Date.now()}`);
  const committed = await request.post(
    `/api/v1/planner-scenarios/${p.id}/draft-commit`,
    {
      data: {
        expected_revision: p.revision,
        operations: [
          { operation: "update_scenario", payload: { max_steps: 1 } },
          {
            operation: "create_seed_state",
            client_ref: "draft:s",
            payload: { name: "就绪" },
          },
          ...[0, 1, 2].map((i) => ({
            operation: "create_activity",
            client_ref: `draft:a${i}`,
            payload: {
              name: `串联工序 ${i + 1}`,
              duration: 1,
              max_instances: 1,
              preconditions: [
                {
                  state_id: i ? `draft:a${i - 1}:output` : "draft:s",
                  relation_role: "required",
                },
              ],
            },
          })),
        ],
      },
    },
  );
  expect(committed.ok(), await committed.text()).toBeTruthy();
  const s = (await committed.json()).scenario;
  await openProject(page, s.id);
  await page.getByRole("button", { name: "联合求解", exact: true }).click();
  await selectState(page, "当前状态", "就绪");
  await selectState(page, "目标状态", "串联工序 3完成");
  await page.locator(".solver-advanced summary").click();
  await expect(page.getByLabel("总执行次数上限", { exact: true })).toHaveCount(
    0,
  );
  await expect(page.locator(".automatic-bound-note")).toContainText(["无需填写", "无需填写"]);
  const submitted = page.waitForResponse(
    (r) =>
      r.url().endsWith("/planner-runs/async") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "开始联合求解" }).click();
  const response = await submitted;
  expect(response.status()).toBe(202);
  const run = await response.json();
  expect(run.request.execution_bound).toMatchObject({
    mode: "auto",
    value: 3,
    heuristic: false,
  });
  expect(run.request.effective_scenario_snapshot.max_steps).toBe(3);
  await expect(page.locator(".result-banner")).toContainText("已证明最优", {
    timeout: 45000,
  });
  await page.getByRole("tab", { name: "求解指标", exact: true }).click();
  await expect(page.locator(".reference-metrics")).toContainText(
    "本次系统设置：最多 3 次执行",
  );
  const saved = (
    await (await request.get(`/api/v1/planner-scenarios/${s.id}`)).json()
  ).scenario;
  expect(saved.max_steps).toBe(1);
  expect(saved.revision).toBe(s.revision);
});

test("六处标注：吊装联动、人数分栏与只编辑活动定义", async ({
  page,
  request,
}) => {
  const initial = await seed(request, `标注验收 ${Date.now()}`);
  const response = await request.post(
    `/api/v1/planner-scenarios/${initial.id}/draft-commit`,
    {
      data: {
        expected_revision: initial.revision,
        operations: [
          {
            operation: "create_resource",
            client_ref: "draft:crane",
            payload: { name: "通用行吊", kind: "crane", capacity: 2 },
          },
          {
            operation: "create_package",
            client_ref: "draft:root",
            payload: { name: "总装", parent_id: null },
          },
          {
            operation: "create_package",
            client_ref: "draft:child",
            payload: { name: "装配", parent_id: "draft:root" },
          },
          {
            operation: "add_membership",
            client_ref: "draft:m",
            payload: {
              activity_id: initial.activities[0].id,
              package_id: "draft:child",
            },
          },
          {
            operation: "update_activity",
            object_id: initial.activities[0].id,
            payload: {
              metadata: { category: "旧分类", business_code: "LEGACY-CODE" },
            },
          },
        ],
      },
    },
  );
  expect(response.ok(), await response.text()).toBeTruthy();
  const s = (await response.json()).scenario;
  await page.setViewportSize({ width: 1118, height: 704 });
  await openProject(page, s.id);
  await expect(page.getByText("LEGACY-CODE", { exact: true })).toHaveCount(0);
  await page
    .getByRole("button", { name: "编辑并行活动甲", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("活动编码")).toHaveCount(0);
  await expect(dialog.getByLabel("活动类别")).toHaveCount(0);
  await expect(dialog.getByRole("group", { name: /所属活动包/ })).toHaveCount(
    0,
  );
  await expect(dialog.getByLabel("是否精密易损", { exact: true })).toHaveCount(
    0,
  );
  await expect(dialog.getByLabel("添加行吊")).toHaveCount(0);
  await expect(dialog.getByLabel("责任组", { exact: true })).toHaveValue(
    s.resources.find((r: { kind: string }) => r.kind === "crew").id,
  );
  await dialog.getByLabel("作业人数", { exact: true }).fill("2");
  await dialog.locator(".resource-field-grid").scrollIntoViewIfNeeded();
  const grid = await dialog.locator(".resource-field-grid").boundingBox(),
    tool = await dialog.locator(".tool-resource-field").boundingBox();
  expect(tool!.width).toBeCloseTo(grid!.width, 0);
  await page.screenshot({
    path: screenshotPath("annotations-no-lifting.png"),
    animations: "disabled",
  });
  await dialog.getByLabel("是否吊装", { exact: true }).selectOption("yes");
  await expect(
    dialog.getByLabel("是否精密易损", { exact: true }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "保存到草稿" }).click();
  await expect(dialog.getByRole("alert")).toContainText("请选择行吊资源");
  const crane = s.resources.find((r: { kind: string }) => r.kind === "crane");
  await dialog.getByLabel("添加行吊").selectOption(crane.id);
  await dialog.getByLabel("是否精密易损", { exact: true }).check();
  await dialog.getByLabel("是否吊装", { exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({
    path: screenshotPath("annotations-lifting.png"),
    animations: "disabled",
  });
  await dialog.getByRole("button", { name: "保存到草稿" }).click();
  await page.getByRole("button", { name: "提交草稿", exact: true }).click();
  await page.getByRole("button", { name: "确认正式提交" }).click();
  await expect(dialog).toHaveCount(0);
  let saved = (
    await (await request.get(`/api/v1/planner-scenarios/${s.id}`)).json()
  ).scenario;
  let activity = saved.activities.find(
    (a: { id: string }) => a.id === initial.activities[0].id,
  );
  expect(activity.resource_reqs).toMatchObject({
    [crane.id]: 1,
    [s.resources.find((r: { kind: string }) => r.kind === "crew").id]: 2,
  });
  expect(activity.metadata).toMatchObject({
    category: "旧分类",
    business_code: "LEGACY-CODE",
    precision_fragile: true,
  });
  expect(activity.max_instances).toBe(initial.activities[0].max_instances);
  expect(saved.activity_package_memberships).toEqual(
    s.activity_package_memberships,
  );
  await page
    .getByRole("button", { name: "编辑并行活动甲", exact: true })
    .click();
  await expect(dialog.getByLabel("是否吊装", { exact: true })).toHaveValue(
    "yes",
  );
  await dialog.getByLabel("是否吊装", { exact: true }).selectOption("no");
  await expect(dialog.getByLabel("是否精密易损", { exact: true })).toHaveCount(
    0,
  );
  await dialog.getByRole("button", { name: "保存到草稿" }).click();
  await page.getByRole("button", { name: "提交草稿", exact: true }).click();
  await page.getByRole("button", { name: "确认正式提交" }).click();
  await expect(dialog).toHaveCount(0);
  saved = (
    await (await request.get(`/api/v1/planner-scenarios/${s.id}`)).json()
  ).scenario;
  activity = saved.activities.find(
    (a: { id: string }) => a.id === initial.activities[0].id,
  );
  expect(activity.resource_reqs[crane.id]).toBeUndefined();
  expect(activity.metadata.precision_fragile).toBe(false);
  expect(saved.activity_package_memberships).toEqual(
    s.activity_package_memberships,
  );
});
async function createProject(request: APIRequestContext, name: string) {
  const r = await request.post("/api/v1/planner-scenarios", { data: { name } });
  expect(r.ok()).toBeTruthy();
  return r.json();
}
async function openProject(page: Page, id: string) {
  await page.goto("/");
  await page.evaluate((id) => localStorage.setItem("planner-project", id), id);
  await page.reload();
  await expect(page.getByLabel("切换项目")).toHaveAttribute(
    "data-project-id",
    id,
  );
}
async function selectState(
  page: Page,
  label: string,
  name: string,
  checked = true,
) {
  await page.getByRole("button", { name: label, exact: true }).click();
  const menu = page.getByRole("group", { name: `${label}层级选项` });
  await menu.getByRole("button", { name: "展开全部" }).click();
  await menu.getByLabel(name, { exact: true }).first().setChecked(checked);
  await menu.getByRole("button", { name: "完成", exact: true }).click();
}

test("完整参考流程：包内向导、关系编辑、跨包引用与提交预览", async ({
  page,
  request,
}) => {
  const initial = await seed(request, `完整参考流程 ${Date.now()}`);
  const r = await request.post(
    `/api/v1/planner-scenarios/${initial.id}/draft-commit`,
    {
      data: {
        expected_revision: initial.revision,
        operations: [
          {
            operation: "create_seed_state",
            client_ref: "draft:duplicate",
            payload: { name: "已就绪" },
          },
          {
            operation: "create_seed_state",
            client_ref: "draft:trans",
            payload: { name: "待转移" },
          },
          {
            operation: "create_seed_state",
            client_ref: "draft:delete",
            payload: { name: "将失效" },
          },
          ...(["crane", "workspace", "tool"] as const).map((kind, i) => ({
            operation: "create_resource",
            client_ref: `draft:r${i}`,
            payload: {
              name: {
                crane: "通用行吊",
                workspace: "装配工位",
                tool: "校准工具",
              }[kind],
              capacity: 2,
              kind,
            },
          })),
          {
            operation: "create_package",
            client_ref: "draft:p",
            payload: { name: "总装", parent_id: null },
          },
          {
            operation: "create_package",
            client_ref: "draft:c1",
            payload: { name: "装配", parent_id: "draft:p" },
          },
          {
            operation: "create_package",
            client_ref: "draft:c2",
            payload: { name: "交付", parent_id: "draft:p" },
          },
        ],
      },
    },
  );
  expect(r.ok(), await r.text()).toBeTruthy();
  const s = (await r.json()).scenario;
  const capture = async (name: string) =>
    page.screenshot({
      path: screenshotPath(`fidelity-${name}.png`),
      fullPage: true,
      animations: "disabled",
    });
  await openProject(page, s.id);
  await page.getByRole("button", { name: "活动包", exact: true }).click();
  await page
    .getByRole("button", { name: "在装配中新建原子活动", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("创建后引用到“总装 / 装配”");
  await dialog.getByLabel("活动名称", { exact: true }).fill("完整装配");
  await expect(dialog.getByLabel("活动类别")).toHaveCount(0);
  await expect(dialog.getByLabel("活动编码")).toHaveCount(0);
  await expect(dialog).toContainText("完整装配完成");
  await capture("wizard-definition");
  await dialog.getByRole("button", { name: "下一步" }).click();
  for (const [i, kind, state] of [
    [
      1,
      "required",
      initial.states.find((st: { name: string }) => st.name === "已就绪").id,
    ],
    [
      2,
      "transition",
      s.states.find((st: { name: string }) => st.name === "待转移").id,
    ],
    [
      3,
      "delete",
      s.states.find((st: { name: string }) => st.name === "将失效").id,
    ],
  ] as const) {
    await dialog.getByRole("button", { name: "添加关系", exact: true }).click();
    await dialog
      .getByLabel(`关系 ${i} 类型`, { exact: true })
      .selectOption(kind);
    await dialog
      .getByLabel(`关系 ${i} 状态`, { exact: true })
      .selectOption(state);
  }
  await dialog.getByLabel("实现效果名称").fill("明确完成");
  for (const [label, kind] of [
    ["责任组", "crew"],
    ["行吊", "crane"],
    ["作业空间", "workspace"],
    ["工装工具", "tool"],
  ]) {
    if (kind === "crane")
      await dialog.getByLabel("是否吊装", { exact: true }).selectOption("yes");
    await dialog
      .getByLabel(kind === "crew" ? "责任组" : `添加${label}`, { exact: true })
      .selectOption(
        s.resources.find((r: { kind: string }) => r.kind === kind).id,
      );
  }
  await dialog.getByLabel("活动时长（分钟）").fill("7");
  await expect(dialog.getByLabel("单活动执行上限")).toHaveCount(0);
  await expect(
    dialog
      .getByRole("group", { name: /所属活动包/ })
      .getByRole("checkbox")
      .first(),
  ).toBeChecked();
  await capture("wizard-relations");
  await dialog.getByRole("button", { name: "创建并保存草稿" }).click();
  await page.getByRole("button", { name: "编辑完整装配", exact: true }).click();
  await expect(dialog.getByLabel("单活动执行上限")).toHaveCount(0);
  await dialog.getByRole("button", { name: "功能调测", exact: true }).click();
  await dialog.locator(".risk-dropdown summary").click();
  await dialog.getByLabel("高处作业", { exact: true }).check();
  await dialog.locator(".risk-dropdown summary").click();
  await dialog.getByLabel("是否精密易损", { exact: true }).check();
  await dialog
    .getByLabel("说明", { exact: true })
    .fill("检查共享定义、容量和四类关系");
  await capture("edit-definition");
  await dialog.locator(".fidelity-relations").scrollIntoViewIfNeeded();
  await capture("edit-relations");
  await dialog.getByRole("button", { name: "保存到草稿" }).click();
  await page.getByRole("button", { name: "引用到交付", exact: true }).click();
  await dialog.getByLabel(/完整装配/).check();
  await capture("reference-picker");
  await dialog.getByRole("button", { name: "添加 1 个引用" }).click();
  await page.getByRole("button", { name: "提交草稿", exact: true }).click();
  await capture("commit");
  await dialog.getByRole("button", { name: "继续编辑" }).click();
  let saved = (
    await (await request.get(`/api/v1/planner-scenarios/${s.id}`)).json()
  ).scenario;
  expect(
    saved.activities.some((a: { name: string }) => a.name === "完整装配"),
  ).toBeFalsy();
  await page.getByRole("button", { name: "提交草稿", exact: true }).click();
  await dialog.getByRole("button", { name: "确认正式提交" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
  saved = (
    await (await request.get(`/api/v1/planner-scenarios/${s.id}`)).json()
  ).scenario;
  const a = saved.activities.find(
    (a: { name: string }) => a.name === "完整装配",
  );
  expect(a.max_instances).toBeNull();
  expect(a.preconditions).toEqual(
    expect.arrayContaining([
      {
        state_id: initial.states.find(
          (st: { name: string }) => st.name === "已就绪",
        ).id,
        relation_role: "required",
      },
      {
        state_id: s.states.find((st: { name: string }) => st.name === "待转移")
          .id,
        relation_role: "transition",
      },
    ]),
  );
  expect(a.delete_effect_state_ids).toEqual([
    s.states.find((st: { name: string }) => st.name === "将失效").id,
  ]);
  expect(
    saved.states.find((st: { id: string }) => st.id === a.output_state_id).name,
  ).toBe("明确完成");
  expect(a.metadata).toMatchObject({
    activity_type: "功能调测",
    risk_jobs: ["高处作业"],
    precision_fragile: true,
  });
  expect(Object.keys(a.resource_reqs)).toHaveLength(4);
  expect(
    saved.activity_package_memberships.filter(
      (m: { activity_id: string }) => m.activity_id === a.id,
    ),
  ).toHaveLength(2);
  await page.reload();
  await page.getByRole("button", { name: "活动包", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "编辑完整装配", exact: true }),
  ).toHaveCount(2);
  await page
    .getByRole("button", { name: "移出完整装配", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("button", { name: "编辑完整装配", exact: true }),
  ).toHaveCount(1);
  await page.getByRole("button", { name: "活动全集", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "编辑完整装配", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "活动包", exact: true }).click();
  await page.getByRole("button", { name: "重命名交付", exact: true }).click();
  await dialog.getByLabel("包名称").fill("交付与检验");
  await capture("package-editor");
  await dialog.getByRole("button", { name: "加入草稿", exact: true }).click();
  await page.getByRole("button", { name: "删除包总装", exact: true }).click();
  await expect(dialog).toContainText("2 个下级活动包");
  await capture("delete-package");
  await dialog.getByRole("button", { name: "确认删除" }).click();
  await expect(page.locator(".package-row")).toHaveCount(0);
  await page.getByRole("button", { name: "提交草稿", exact: true }).click();
  await dialog.getByRole("button", { name: "确认正式提交" }).click();
  await expect(dialog).toHaveCount(0);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "编辑完整装配", exact: true }),
  ).toBeVisible();
});

test("删除与日历界面：引用阻止删除，取消编辑不修改场景", async ({
  page,
  request,
}) => {
  const s = await seed(request, `删除和只读 ${Date.now()}`);
  await openProject(page, s.id);
  await page.getByRole("button", { name: "资源管理", exact: true }).click();
  await page
    .getByRole("button", { name: "删除资源装配班组", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("并行活动甲");
  await expect(dialog.getByRole("button", { name: "确认删除" })).toBeDisabled();
  await page.screenshot({
    path: screenshotPath("fidelity-delete-blocked.png"),
    animations: "disabled",
  });
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await page.getByRole("button", { name: "新增工装工具", exact: true }).click();
  await dialog.getByLabel("名称", { exact: true }).fill("临时工具");
  await page.screenshot({
    path: screenshotPath("fidelity-resource-editor.png"),
    animations: "disabled",
  });
  await dialog.getByRole("button", { name: "保存到草稿" }).click();
  await page
    .getByRole("button", { name: "删除资源临时工具", exact: true })
    .click();
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "编辑资源临时工具", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "删除资源临时工具", exact: true })
    .click();
  await dialog.getByRole("button", { name: "确认删除" }).click();
  await expect(
    page.getByRole("button", { name: "编辑资源临时工具", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("tab", { name: /工作日历/ }).click();
  await expect(
    page.getByRole("button", { name: "新增工作日历", exact: true }),
  ).toBeEnabled();
  await page.screenshot({
    path: screenshotPath("fidelity-calendar.png"),
    animations: "disabled",
  });
  await page.getByRole("button", { name: "新增工作日历" }).click();
  await expect(dialog.getByRole("button", { name: "保存到草稿" })).toBeEnabled();
  await expect(dialog.getByLabel("日历名称")).toBeEnabled();
  await page.screenshot({
    path: screenshotPath("fidelity-calendar-editor.png"),
    animations: "disabled",
  });
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  const saved = (
    await (await request.get(`/api/v1/planner-scenarios/${s.id}`)).json()
  ).scenario;
  expect(saved.revision).toBe(s.revision);
  await page.getByRole("button", { name: "活动全集", exact: true }).click();
  await page.getByRole("button", { name: "删除活动", exact: true }).click();
  await page.screenshot({
    path: screenshotPath("fidelity-delete-activity.png"),
    animations: "disabled",
  });
  await dialog.getByRole("button", { name: "确认删除" }).click();
  await expect(page.locator(".reference-activity-table tbody tr")).toHaveCount(
    1,
  );
});
async function seed(request: APIRequestContext, name: string) {
  const p = await createProject(request, name);
  const r = await request.post(
    `/api/v1/planner-scenarios/${p.id}/draft-commit`,
    {
      data: {
        expected_revision: p.revision,
        operations: [
          {
            operation: "create_seed_state",
            client_ref: "draft:s",
            payload: { name: "已就绪" },
          },
          {
            operation: "create_resource",
            client_ref: "draft:r",
            payload: { name: "装配班组", capacity: 2, kind: "crew" },
          },
          {
            operation: "create_activity",
            client_ref: "draft:a",
            payload: {
              name: "并行活动甲",
              duration: 4,
              max_instances: 1,
              preconditions: [
                { state_id: "draft:s", relation_role: "required" },
              ],
              resource_reqs: { "draft:r": 1 },
            },
          },
          {
            operation: "create_activity",
            client_ref: "draft:b",
            payload: {
              name: "并行活动乙",
              duration: 6,
              max_instances: 1,
              preconditions: [
                { state_id: "draft:s", relation_role: "required" },
              ],
              resource_reqs: { "draft:r": 1 },
            },
          },
        ],
      },
    },
  );
  expect(r.ok(), await r.text()).toBeTruthy();
  return (await r.json()).scenario;
}
test("管理四页闭环、草稿引用解析、刷新后真实求解", async ({
  page,
  request,
}) => {
  const p = await createProject(request, `UI端到端 ${Date.now()}`);
  await openProject(page, p.id);
  await page.getByRole("button", { name: "添加已知状态" }).click();
  await page.getByLabel("状态名称", { exact: true }).fill("已就绪");
  await page.getByRole("button", { name: "加入草稿", exact: true }).click();
  await page.getByRole("button", { name: "资源管理", exact: true }).click();
  await page.getByRole("button", { name: "新增作业人数" }).click();
  await page
    .getByRole("dialog")
    .getByLabel("名称", { exact: true })
    .fill("装配班组");
  await page.getByRole("dialog").getByLabel("容量", { exact: true }).fill("2");
  await page.getByRole("button", { name: "保存到草稿" }).click();
  await page.getByRole("button", { name: "活动包", exact: true }).click();
  await page.getByRole("button", { name: "增加一级活动包" }).click();
  await page.getByLabel("包名称").fill("总装");
  await page.getByRole("button", { name: "加入草稿", exact: true }).click();
  await page.getByRole("button", { name: "在总装下添加二级包" }).click();
  await page.getByLabel("包名称").fill("装配");
  await page.getByRole("button", { name: "加入草稿", exact: true }).click();
  await page.getByRole("button", { name: "活动全集", exact: true }).click();
  await page.getByRole("button", { name: "新建活动", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("活动名称", { exact: true }).fill("装配任务");
  await dialog.getByRole("button", { name: "下一步" }).click();
  await dialog.getByLabel("活动时长（分钟）").fill("5");
  await dialog.getByRole("button", { name: "添加关系", exact: true }).click();
  await dialog.getByLabel("关系 1 状态").selectOption({ label: "已就绪" });
  await dialog
    .getByLabel("责任组", { exact: true })
    .selectOption({ label: "装配班组" });
  await dialog.getByLabel("作业人数", { exact: true }).fill("1");
  await dialog
    .getByRole("group", { name: /所属活动包/ })
    .getByRole("checkbox")
    .check();
  await dialog.getByRole("button", { name: "创建并保存草稿" }).click();
  await page.getByRole("button", { name: "提交草稿", exact: true }).click();
  await page.getByRole("button", { name: "确认正式提交", exact: true }).click();
  await expect(page.locator(".commit-workspace")).toBeDisabled();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.reload();
  await expect(page.getByText("装配任务", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "活动包", exact: true }).click();
  await expect(page.getByText("装配任务", { exact: true })).toBeVisible();
  await page.screenshot({
    path: screenshotPath("packages.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "联合求解", exact: true }).click();
  await selectState(page, "当前状态", "已就绪", true);
  await selectState(page, "目标状态", "装配任务完成", true);
  await expect(page.getByLabel("工作日历", { exact: true })).toBeEnabled();
  await expect(page.getByLabel("工作日历", { exact: true })).toHaveValue("");
  await page.getByRole("button", { name: "开始联合求解" }).click();
  await expect(page.locator(".result-banner")).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "联合求解", exact: true }).click();
  await expect(page.locator(".result-banner")).toContainText("已证明最优", {
    timeout: 45000,
  });
  await page.getByRole("tab", { name: "求解指标", exact: true }).click();
  await expect(page.locator(".metric-grid")).toContainText("5");
  await page.getByRole("tab", { name: "甘特图", exact: true }).click();
  await expect(page.locator(".gantt-row")).toHaveCount(1);
  await expect(page.getByText(/回放校验 VALID/)).toBeVisible();
  await page.screenshot({
    path: screenshotPath("solver.png"),
    fullPage: true,
  });
});
test("真实并行排程与快照历史不受更名影响", async ({ page, request }) => {
  const s = await seed(request, `并行快照 ${Date.now()}`);
  await openProject(page, s.id);
  await page.getByRole("button", { name: "联合求解", exact: true }).click();
  await selectState(page, "当前状态", "已就绪", true);
  for (const name of ["并行活动甲完成", "并行活动乙完成"])
    await selectState(page, "目标状态", name, true);
  await page.getByRole("button", { name: "开始联合求解" }).click();
  await expect(page.locator(".result-banner")).toContainText("已证明最优", {
    timeout: 45000,
  });
  await page.getByRole("tab", { name: "甘特图", exact: true }).click();
  await expect(page.locator(".gantt-row")).toHaveCount(2);
  await page.getByRole("tab", { name: "求解指标", exact: true }).click();
  await expect(page.locator(".metric-grid>div").first()).toContainText("6");
  const r = await request.patch(
    `/api/v1/planner-scenarios/${s.id}/activities/${s.activities[0].id}`,
    { data: { expected_revision: s.revision, name: "更名后活动" } },
  );
  expect(r.ok()).toBeTruthy();
  await page.reload();
  await page.getByRole("button", { name: "联合求解", exact: true }).click();
  await page.getByRole("tab", { name: "甘特图", exact: true }).click();
  await expect(page.locator(".gantt")).toContainText("并行活动甲");
  await expect(page.locator(".gantt")).not.toContainText("更名后活动");
  await page.context().setOffline(true);
  await page.getByRole("button", { name: "刷新历史" }).click();
  await expect(page.getByRole("alert")).toContainText("状态查询失败");
  await page.context().setOffline(false);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.locator(".gantt-row")).toHaveCount(2);
});
test("版本冲突保留草稿，切换项目可取消或放弃", async ({ page, request }) => {
  const s = await seed(request, `冲突测试 ${Date.now()}`),
    other = await createProject(request, `另一项目 ${Date.now()}`);
  await openProject(page, s.id);
  await page
    .getByRole("button", { name: "编辑并行活动甲", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByLabel("活动名称", { exact: true })
    .fill("本地草稿");
  await page.getByRole("button", { name: "保存到草稿" }).click();
  const updated = await request.patch(`/api/v1/planner-scenarios/${s.id}`, {
    data: { expected_revision: s.revision, name: "外部更名" },
  });
  expect(updated.ok()).toBeTruthy();
  await page.getByRole("button", { name: "提交草稿", exact: true }).click();
  await page.getByRole("button", { name: "确认正式提交", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("草稿已保留");
  await expect(page.getByText("本地草稿", { exact: true })).toBeVisible();
  await page.getByLabel("切换项目").click();
  await page.locator(`[data-project-option="${other.id}"]`).click();
  await page.getByRole("button", { name: "取消切换" }).click();
  await expect(page.getByLabel("切换项目")).toHaveAttribute(
    "data-project-id",
    s.id,
  );
  await page.getByLabel("切换项目").click();
  await page.locator(`[data-project-option="${other.id}"]`).click();
  await page.getByRole("button", { name: "放弃并切换" }).click();
  await expect(page.getByLabel("切换项目")).toHaveAttribute(
    "data-project-id",
    other.id,
  );
  await expect(page.getByText("本地草稿", { exact: true })).toHaveCount(0);
});
test("预算耗尽不误报无解，目标已满足交付零步方案", async ({
  page,
  request,
}) => {
  const s = await seed(request, `状态测试 ${Date.now()}`);
  // Legacy API budgets remain supported; the UI itself always requests auto.
  const queued = await request.post("/api/v1/planner-runs/async", { data: {
    scenario_id: s.id, expected_revision: s.revision,
    current_state_ids: [s.states.find((st: {name: string}) => st.name === "已就绪").id],
    target_state_ids: [s.activities[0].output_state_id],
    budget: {time_limit_seconds: 0}, client_request_id: crypto.randomUUID(),
    display_start_at: new Date().toISOString(), display_timezone: "Asia/Shanghai",
  }});
  expect(queued.status()).toBe(202);
  await openProject(page, s.id);
  await page.getByRole("button", { name: "联合求解", exact: true }).click();
  await selectState(page, "当前状态", "已就绪", true);
  await selectState(page, "目标状态", "并行活动甲完成", true);
  await page.locator(".solver-advanced summary").click();
  await expect(page.getByLabel("求解预算", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("执行模式", { exact: true })).toHaveValue("parallel");
  await expect(page.locator(".result-banner")).toContainText(
    "预算内未找到方案",
    { timeout: 45000 },
  );
  await expect(page.locator(".gantt-row")).toHaveCount(0);
  await selectState(page, "目标状态", "并行活动甲完成", false);
  await selectState(page, "目标状态", "已就绪", true);
  await page.getByRole("button", { name: "开始联合求解" }).click();
  await expect(page.getByText("目标状态已经满足，无需执行活动。")).toBeVisible({
    timeout: 45000,
  });
  const history = await (await request.get(`/api/v1/planner-runs?scenario_id=${s.id}`)).json();
  const latest = await (await request.get(`/api/v1/planner-runs/${history[0].id}`)).json();
  expect(latest.request.budget_mode).toBe("auto");
  expect(latest.request.effective_budget.time_limit_seconds).toBe(60);
  expect(latest.request.effective_scenario_snapshot.execution_mode).toBe("parallel");
});

test.describe("工作日历真实求解", () => {
  test.use({ timezoneId: "Asia/Shanghai" });
  test("休息续做、日期例外、甘特分段及历史日历快照", async ({page,request}) => {
    await page.setViewportSize({width:1118,height:704});
    let s=await seed(request,`日历验收 ${Date.now()}`);
    const changed=await request.patch(`/api/v1/planner-scenarios/${s.id}/activities/${s.activities[0].id}`,{data:{expected_revision:s.revision,duration:180}});
    expect(changed.ok()).toBeTruthy();
    s=(await (await request.get(`/api/v1/planner-scenarios/${s.id}`)).json()).scenario;
    await openProject(page,s.id);
    await page.getByRole('button',{name:'资源管理',exact:true}).click();
    await page.getByRole('tab',{name:'工作日历',exact:true}).click();
    await page.getByRole('button',{name:'新增工作日历',exact:true}).click();
    const dialog=page.getByRole('dialog');
    await dialog.getByLabel('日历名称',{exact:true}).fill('标准工作日历');
    await dialog.getByRole('button',{name:'添加日期例外',exact:true}).click();
    await dialog.getByLabel('例外日期 1',{exact:true}).fill('2026-11-09');
    await page.screenshot({path:screenshotPath('calendar-edit.png'),animations:'disabled'});
    await dialog.getByRole('button',{name:'保存到草稿',exact:true}).click();
    await page.getByRole('button',{name:'联合求解',exact:true}).click();
    const option=page.getByLabel('工作日历',{exact:true}).getByRole('option',{name:'标准工作日历'});
    await page.getByLabel('工作日历',{exact:true}).selectOption((await option.getAttribute('value'))!);
    await page.getByRole('button',{name:'提交草稿',exact:true}).click();
    await dialog.getByRole('button',{name:'确认正式提交',exact:true}).click();
    await expect(dialog).toHaveCount(0);
    await selectState(page,'当前状态','已就绪');
    await selectState(page,'目标状态','并行活动甲完成');
    await page.getByLabel('开始日期时间',{exact:true}).fill('2026-11-06T16:00');
    await page.getByRole('button',{name:'开始联合求解'}).click();
    await expect(page.locator('.result-banner')).toContainText('已证明最优',{timeout:45000});
    await page.getByRole('tab',{name:'求解指标',exact:true}).click();
    await expect(page.locator('.reference-metrics')).toContainText('5400');
    await expect(page.locator('.reference-metrics')).toContainText('标准工作日历');
    await page.getByRole('tab',{name:'甘特图',exact:true}).click();
    await expect(page.locator('.gantt-row').filter({hasText:'并行活动甲'}).locator('.gantt-bar')).toHaveCount(2);
    await page.screenshot({path:screenshotPath('calendar-gantt.png'),animations:'disabled'});
    await page.reload();
    await page.getByRole('button',{name:'联合求解',exact:true}).click();
    await expect(page.getByLabel('开始日期时间',{exact:true})).toHaveValue('2026-11-06T16:00');
    await page.getByRole('button',{name:'资源管理',exact:true}).click();
    await page.getByRole('tab',{name:'工作日历',exact:true}).click();
    await page.getByRole('button',{name:'删除日历标准工作日历',exact:true}).click();
    await expect(dialog.getByRole('button',{name:'确认删除'})).toBeDisabled();
    await dialog.getByRole('button',{name:'取消',exact:true}).click();
    await page.getByRole('button',{name:'编辑日历标准工作日历',exact:true}).click();
    await dialog.getByLabel('日历名称',{exact:true}).fill('新日历名称');
    await dialog.getByRole('button',{name:'保存到草稿',exact:true}).click();
    await page.getByRole('button',{name:'提交草稿',exact:true}).click();
    await dialog.getByRole('button',{name:'确认正式提交',exact:true}).click();
    await expect(dialog).toHaveCount(0);
    await page.getByRole('button',{name:'联合求解',exact:true}).click();
    await page.getByRole('tab',{name:'求解指标',exact:true}).click();
    await expect(page.locator('.reference-metrics')).toContainText('标准工作日历');
    await expect(page.locator('.reference-metrics')).toContainText('5400');
  });
});

test.describe('精密吊装夜班与空档填补',()=>{
  test.use({timezoneId:'Asia/Shanghai'});
  test('精密吊装等待白班，普通吊装利用夜间同一行吊',async({page,request})=>{
    let s=await seed(request,`精密吊装空档填补验收 ${Date.now()}`);
    const changed=await request.post(`/api/v1/planner-scenarios/${s.id}/draft-commit`,{data:{expected_revision:s.revision,operations:[
      {operation:'create_resource',client_ref:'draft:crane',payload:{name:'共享行吊',capacity:1,kind:'crane'}},
      {operation:'update_activity',object_id:s.activities[0].id,payload:{name:'精密设备吊装',duration:120,metadata:{precision_fragile:true},resource_reqs:{'draft:crane':1}}},
      {operation:'update_activity',object_id:s.activities[1].id,payload:{name:'普通构件吊装',duration:120,metadata:{precision_fragile:false},resource_reqs:{'draft:crane':1}}},
    ]}});
    expect(changed.ok()).toBeTruthy();s=(await changed.json()).scenario;
    await openProject(page,s.id);
    await page.getByRole('button',{name:'联合求解',exact:true}).click();
    await page.getByLabel('精密易损吊装禁止夜班',{exact:true}).check();
    await expect(page.getByLabel('夜班开始',{exact:true})).toHaveValue('20:00');
    await expect(page.getByLabel('夜班结束',{exact:true})).toHaveValue('08:00');
    await expect(page.getByRole('button',{name:'开始联合求解'})).toBeDisabled();
    await page.getByRole('button',{name:'提交草稿',exact:true}).click();
    await page.getByRole('button',{name:'确认正式提交',exact:true}).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await selectState(page,'当前状态','已就绪');
    for(const name of ['精密设备吊装完成','普通构件吊装完成'])await selectState(page,'目标状态',name);
    await page.getByLabel('开始日期时间',{exact:true}).fill('2026-11-04T19:00');
    const submitted=page.waitForResponse(r=>r.url().endsWith('/planner-runs/async')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'开始联合求解'}).click();
    const run=await (await submitted).json();
    await expect(page.locator('.result-banner')).toContainText('已证明最优',{timeout:45000});
    const result=await (await request.get(`/api/v1/planner-runs/${run.id}`)).json();
    const candidate=result.result.results.JOINT_CP_SAT.paths[0];
    expect(candidate.validator_status).toBe('VALID');
    expect(candidate.metrics.makespan).toBe(900);
    const fragile=candidate.executions.find((e:{activity_id:string})=>e.activity_id===s.activities[0].id);
    const normal=candidate.executions.find((e:{activity_id:string})=>e.activity_id===s.activities[1].id);
    expect([fragile.start_time,fragile.end_time]).toEqual([780,900]);
    expect([normal.start_time,normal.end_time]).toEqual([0,120]);
    await page.getByRole('tab',{name:'甘特图',exact:true}).click();
    await expect(page.locator('.gantt-row')).toHaveCount(2);
    await page.screenshot({path:screenshotPath('night-lift-gap.png'),animations:'disabled'});
    await page.reload();
    await page.getByRole('button',{name:'联合求解',exact:true}).click();
    await expect(page.getByLabel('精密易损吊装禁止夜班',{exact:true})).toBeChecked();
    await page.getByLabel('夜班开始',{exact:true}).fill('22:00');
    await page.getByRole('button',{name:'提交草稿',exact:true}).click();
    await page.getByRole('button',{name:'确认正式提交',exact:true}).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await page.getByRole('tab',{name:'求解指标',exact:true}).click();
    await expect(page.locator('.reference-metrics')).toContainText('20:00–次日08:00');
  });
});

test('全局作业独占：两类开关、普通并行、保存与历史快照',async({page,request})=>{
  let s=await seed(request,`全局作业独占验收 ${Date.now()}`);
  const changed=await request.post(`/api/v1/planner-scenarios/${s.id}/draft-commit`,{data:{expected_revision:s.revision,operations:[
    {operation:'create_resource',client_ref:'draft:crane',payload:{name:'双容量行吊池',capacity:2,kind:'crane'}},
    {operation:'update_activity',object_id:s.activities[0].id,payload:{name:'独占吊装',duration:10,resource_reqs:{'draft:crane':1},metadata:{activity_type:'机械集成'}}},
    {operation:'update_activity',object_id:s.activities[1].id,payload:{name:'独占调测',duration:10,resource_reqs:{},metadata:{activity_type:'功能调测'}}},
    ...['普通甲','普通乙'].map(name=>({operation:'create_activity',payload:{name,duration:10,max_instances:1,metadata:{activity_type:'机械集成'}}})),
  ]}});
  expect(changed.ok(),await changed.text()).toBeTruthy();s=(await changed.json()).scenario;
  await openProject(page,s.id);
  await page.getByRole('button',{name:'联合求解',exact:true}).click();
  for(const label of ['行吊作业独占','调测作业独占'])await page.getByLabel(label,{exact:true}).check();
  await expect(page.getByRole('button',{name:'开始联合求解'})).toBeDisabled();
  await expect(page.getByLabel('按活动包连续',{exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'提交草稿',exact:true}).click();
  await page.getByRole('button',{name:'确认正式提交',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await selectState(page,'当前状态','已就绪');
  for(const name of ['独占吊装完成','独占调测完成','普通甲完成','普通乙完成'])await selectState(page,'目标状态',name);
  const submitted=page.waitForResponse(r=>r.url().endsWith('/planner-runs/async')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'开始联合求解'}).click();
  const run=await(await submitted).json();
  await expect(page.locator('.result-banner')).toContainText('已证明最优',{timeout:45000});
  const result=await(await request.get(`/api/v1/planner-runs/${run.id}`)).json();
  const candidate=result.result.results.JOINT_CP_SAT.paths[0];
  expect(candidate.validator_status).toBe('VALID');expect(candidate.metrics.makespan).toBe(30);
  const rows=candidate.executions as {activity_name:string;start_time:number;end_time:number}[];
  for(const a of rows.filter(e=>e.activity_name.startsWith('独占')))for(const b of rows.filter(e=>e!==a)){
    expect(a.end_time<=b.start_time||b.end_time<=a.start_time).toBeTruthy();
  }
  expect(rows.filter(e=>e.activity_name.startsWith('普通')).map(e=>e.start_time)).toEqual([expect.any(Number),expect.any(Number)]);
  const ordinary=rows.filter(e=>e.activity_name.startsWith('普通'));expect(ordinary[0].start_time).toBe(ordinary[1].start_time);
  await page.getByRole('tab',{name:'甘特图',exact:true}).click();
  await page.screenshot({path:screenshotPath('exclusive-gantt.png'),animations:'disabled'});
  await page.reload();await page.getByRole('button',{name:'联合求解',exact:true}).click();
  for(const label of ['行吊作业独占','调测作业独占']){
    await expect(page.getByLabel(label,{exact:true})).toBeChecked();
    await page.getByLabel(label,{exact:true}).uncheck();
  }
  await page.getByRole('button',{name:'提交草稿',exact:true}).click();
  await page.getByRole('button',{name:'确认正式提交',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('tab',{name:'求解指标',exact:true}).click();
  await expect(page.locator('.reference-metrics')).toContainText('当次作业独占：行吊作业、调测作业');
  const disabledSubmit=page.waitForResponse(r=>r.url().endsWith('/planner-runs/async')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'开始联合求解'}).click();
  const second=await(await disabledSubmit).json();
  await expect(page.locator('.result-banner')).toContainText('已证明最优',{timeout:45000});
  await expect(page.locator('.reference-metrics')).toContainText('当次作业独占：未启用');
  const withoutRules=await(await request.get(`/api/v1/planner-runs/${second.id}`)).json();
  expect(withoutRules.result.results.JOINT_CP_SAT.paths[0].metrics.makespan).toBe(10);
});
