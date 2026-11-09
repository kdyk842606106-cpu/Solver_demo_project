import { test, expect, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

test.use({ timezoneId: 'Asia/Shanghai' });
const folder = process.env.INITIAL_CHECK_FIXTURES;
test.skip(!folder, 'Requires read-only Test A validation fixtures and API');
function fixtures() {
  return { requests: JSON.parse(readFileSync(resolve(folder!, 'requests.json'), 'utf8')),
    diagnoses: JSON.parse(readFileSync(resolve(folder!, 'diagnoses.json'), 'utf8')),
    project: JSON.parse(readFileSync(resolve(folder!, 'project-before.json'), 'utf8')) };
}
async function open(page: Page, name: string) {
  const { requests, project } = fixtures(), body = requests[name];
  await page.addInitScript(({id, body}) => {
    localStorage.setItem('planner-project', id);
    localStorage.setItem(`planner-form:${id}`, JSON.stringify({initial: body.current_state_ids, target: body.target_state_ids, start: '2026-11-06T08:00'}));
  }, {id: project.id, body});
  // A browser test must not accidentally create jobs or commit edits.
  await page.route('**/api/v1/**', async route => {
    if (route.request().method() !== 'GET' && !route.request().url().endsWith('/initial-state-check'))
      throw new Error('Unexpected mutation: '+route.request().url());
    await route.continue();
  });
  await page.goto('/'); await page.getByRole('button', {name:'联合求解',exact:true}).click();
  return page.getByRole('region', {name:'初始状态诊断'});
}
async function confirm(page: Page, name: string) {
  const card = page.locator('.initial-check-state').filter({has: page.getByText(name, {exact:true})});
  await card.getByRole('button', {name:'确认此状态…',exact:true}).click();
  await expect(page.getByRole('dialog', {name:'确认当前事实'})).toBeVisible();
  await page.getByRole('button', {name:'确认当前已成立并加入',exact:true}).click();
}

test('设置项目初始状态：立即展示草稿预览，继续编辑后可返回提交，成功后显示已保存', async ({page, request}) => {
  const {project, requests} = fixtures();
  const before = await (await request.get(`/api/v1/planner-scenarios/${project.id}`)).json();
  await open(page, 'cycle-no-start');
  let submitted: any = null;
  await page.route('**/draft-commit', async route => {
    submitted = route.request().postDataJSON();
    await route.fulfill({json: {revision: before.revision + 1, scenario: {
      ...before.scenario, initial_state_ids: requests['cycle-no-start'].current_state_ids,
    }}});
  });
  await page.getByRole('button',{name:'设为项目初始状态',exact:true}).click();
  const dialog = page.getByRole('dialog',{name:'统一提交草稿'});
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('更新项目初始状态');
  await expect(dialog).toContainText('下电完成');
  await expect(dialog).toContainText('集成检测完成完成');
  expect(submitted).toBeNull();
  await dialog.getByRole('button',{name:'继续编辑',exact:true}).click();
  await expect(page.getByText('尚未保存，请提交草稿',{exact:false})).toBeVisible();
  await expect(page.getByRole('button',{name:'已加入草稿',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'查看并提交初始状态草稿',exact:true}).click();
  await dialog.getByRole('button',{name:'确认正式提交',exact:true}).click();
  await expect(dialog).not.toBeVisible();
  expect(submitted.expected_revision).toBe(before.revision);
  expect(submitted.operations).toEqual([{operation:'update_scenario',payload:{initial_state_ids:requests['cycle-no-start'].current_state_ids}}]);
  await expect(page.getByRole('button',{name:'已是项目初始状态',exact:true})).toBeDisabled();
  await expect(page.getByText('尚未保存，请提交草稿',{exact:false})).toHaveCount(0);
  // The save response is mocked: the actual project and revision must remain untouched.
  expect(await (await request.get(`/api/v1/planner-scenarios/${project.id}`)).json()).toEqual(before);
});

test('设置初始状态遇到409：保留所有草稿，显示冲突，不误报已保存', async ({page}) => {
  await open(page,'cycle-no-start');
  await page.getByRole('checkbox',{name:'行吊作业独占',exact:true}).uncheck();
  await page.route('**/draft-commit', route => route.fulfill({status:409,json:{detail:{code:'SCENARIO_REVISION_CONFLICT'}}}));
  await page.getByRole('button',{name:'设为项目初始状态',exact:true}).click();
  const dialog = page.getByRole('dialog',{name:'统一提交草稿'});
  await expect(dialog).toContainText('2 项草稿变更');
  await dialog.getByRole('button',{name:'确认正式提交',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('草稿已保留');
  await expect(page.getByText('尚未保存，请提交草稿',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'查看并提交初始状态草稿',exact:true}).click();
  await expect(dialog).toContainText('2 项草稿变更');
  await expect(dialog.getByRole('button',{name:'确认正式提交',exact:true})).toBeDisabled();
});

test('测试A缺失故障：确认预览、取消、单项确认和撤销均不写项目', async ({page, request}, info) => {
  const {project, requests} = fixtures();
  const before = await (await request.get(`/api/v1/planner-scenarios/${project.id}`)).json();
  const panel = await open(page, 'missing-fault');
  await panel.getByRole('button', {name:'检查初始状态',exact:true}).click();
  await expect(panel).toContainText('缺少起始事实');
  const card = panel.locator('.initial-check-state').filter({has:page.getByText('模块A待维修',{exact:true})});
  await card.getByRole('button').click();
  await page.getByRole('dialog').getByRole('button',{name:'取消',exact:true}).click();
  expect(await page.evaluate(id=>JSON.parse(localStorage.getItem(`planner-form:${id}`)!).initial,project.id)).toEqual(requests['missing-fault'].current_state_ids);
  await panel.screenshot({path:info.outputPath('missing-fault.png')});
  await confirm(page, '模块A待维修');
  await expect(panel).toContainText('结构预检通过');
  await expect(panel).not.toContainText('配置已变化');
  await panel.getByRole('button',{name:'撤销此次确认'}).click();
  await expect(panel).toContainText('发现结构阻塞');
  expect(await (await request.get(`/api/v1/planner-scenarios/${project.id}`)).json()).toEqual(before);
});

test('测试A安装拆卸循环：逐项确认A/C后重新检查', async ({page}, info) => {
  const panel = await open(page, 'cycle-no-start');
  await panel.getByRole('button',{name:'检查初始状态',exact:true}).click();
  await expect(panel).toContainText('循环缺少起点');
  await confirm(page,'模块C拆卸完成');
  await expect(panel).not.toContainText('配置已变化');
  await expect(panel).toContainText('发现结构阻塞');
  await confirm(page,'模块A拆卸完成');
  await expect(panel).toContainText('结构预检通过');
  await panel.screenshot({path:info.outputPath('cycle-confirmed.png')});
});

test('测试A维修恢复：结构通过、修改后失效、草稿诊断不提交', async ({page}) => {
  const panel = await open(page, 'repair-confirmed');
  await panel.getByRole('button',{name:'检查初始状态',exact:true}).click();
  await expect(panel).toContainText('结构预检通过 · 不代表保证有解');
  await page.getByRole('checkbox',{name:'行吊作业独占',exact:true}).uncheck();
  await expect(panel).toContainText('配置已变化');
  await expect(page.getByRole('button',{name:'开始联合求解'})).toBeDisabled();
  const waiting = page.waitForRequest(r=>r.url().endsWith('/initial-state-check'));
  await panel.getByRole('button',{name:'检查初始状态',exact:true}).click();
  const sent = (await waiting).postDataJSON();
  expect(sent.draft_scenario.exclusive_rules.crane).toBe(false);
  await expect(panel).toContainText('当前草稿');
  await expect(panel).not.toContainText('配置已变化');
});

test('慢响应不得覆盖已修改输入，重新检查可恢复', async ({page}) => {
  const panel = await open(page, 'missing-fault');
  let release!:()=>void; const wait = new Promise<void>(r=>release=r);
  let delivered!:()=>void; const finished = new Promise<void>(r=>delivered=r);
  await page.route('**/initial-state-check', async route=>{
    await wait;
    try { await route.fulfill({json: {...fixtures().diagnoses['missing-fault'], scenario_id:fixtures().project.id}}); } catch { /* request cancelled */ } finally { delivered(); }
  }, {times:1});
  const sent = page.waitForRequest(r=>r.url().endsWith('/initial-state-check'));
  await panel.getByRole('button',{name:'检查初始状态',exact:true}).click(); await sent;
  await page.getByRole('button',{name:'当前状态',exact:true}).click();
  await page.getByRole('group',{name:'当前状态层级选项'}).getByRole('button',{name:'清空',exact:true}).click();
  await page.getByRole('group',{name:'当前状态层级选项'}).getByRole('button',{name:'完成',exact:true}).click();
  release(); await finished;
  await expect(panel.locator('.initial-check-group')).toHaveCount(0);
  await panel.getByRole('button',{name:'检查初始状态',exact:true}).click();
  await expect(panel).toContainText('循环缺少起点');
});

test('切换项目清除诊断和确认记录', async ({page}) => {
  const {project} = fixtures();
  const panel = await open(page, 'missing-fault');
  await panel.getByRole('button',{name:'检查初始状态',exact:true}).click();
  await confirm(page,'模块A待维修');
  await expect(panel).toContainText('结构预检通过');
  // Use a browser-only second project to avoid creating business data.
  const other = {...project, id:'diagnosis-other', name:'诊断隔离项目', scenario:{...project.scenario,id:'diagnosis-other',name:'诊断隔离项目'}};
  await page.route('**/api/v1/planner-scenarios', route=>route.fulfill({json:[{id:project.id,name:project.name,revision:project.revision},{id:other.id,name:other.name,revision:other.revision}]}));
  await page.route('**/api/v1/planner-scenarios/diagnosis-other', route=>route.fulfill({json:other}));
  await page.reload(); await page.getByRole('button',{name:'联合求解',exact:true}).click();
  await page.getByRole('button',{name:'检查初始状态',exact:true}).click();
  await expect(page.getByRole('region',{name:'初始状态诊断'})).toContainText('缺少起始事实');
  await confirm(page,'模块A待维修');
  await expect(page.getByRole('region',{name:'初始状态诊断'})).toContainText('结构预检通过');
  await page.getByRole('button',{name:'切换项目',exact:true}).click();
  await page.getByRole('menuitem',{name:'诊断隔离项目',exact:true}).click();
  await expect(page.getByRole('button',{name:'切换项目',exact:true})).toContainText('诊断隔离项目');
  await expect(page.locator('.initial-check-results')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'撤销此次确认'})).toHaveCount(0);
});
