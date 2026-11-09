import {test,expect,type Page} from '@playwright/test';
import {readFileSync,writeFileSync} from 'node:fs';

test.use({timezoneId:'Asia/Shanghai'});

async function mock(page: Page) {
  const project={id:'windows-p',name:'时间窗项目',revision:1,start_time:0,execution_mode:'parallel',max_steps:8,default_budget:{},
    activities:['a1','a2'].map((id,i)=>({id,name:'同名作业',display_code:`ACT-00${i+1}`,duration:5,output_state_id:'done',preconditions:[],is_active:true})),
    states:[{id:'ready',name:'就绪',state_kind:'seed'},{id:'done',name:'完成',state_kind:'seed'}],resources:[],
    initial_state_ids:['ready'],goal_state_ids:['done'],forbidden_state_ids:[],
    activity_packages:[{id:'pa',name:'装配包',parent_id:null},{id:'pb',name:'调测包',parent_id:null}],
    activity_package_memberships:[{id:'ma',package_id:'pa',activity_id:'a1'},{id:'mb',package_id:'pb',activity_id:'a2'}],
    time_windows:[{id:'legacy',activity_id:'a1',earliest_start:0,latest_finish:300}]};
  const other={...project,id:'windows-other',name:'另一个项目'};
  const bodies: any[]=[];
  let run: any=null;
  await page.route('**/api/v1/**',async route=>{
    const url=new URL(route.request().url()),path=url.pathname.replace('/api/v1/','');
    let data:any;
    if(path==='planner-scenarios') data=[project,other];
    else if(path==='planner-scenarios/'+project.id) data={scenario:project,revision:1};
    else if(path==='planner-scenarios/'+other.id) data={scenario:other,revision:1};
    else if(path==='planner-runs/capabilities') data={planner_available:true,async_runs_supported:true,joint_cp_sat:{run_activity_time_windows_supported:true}};
    else if(path==='planner-runs/async') {
      const body=route.request().postDataJSON();bodies.push(body);
      const snapshot=structuredClone(project);snapshot.activities[0].name='冻结的活动名称';
      run={id:'window-run',scenario_id:project.id,created_at:new Date().toISOString(),job_status:'FINISHED',status:'OPTIMAL',
        request:{...body,effective_scenario_snapshot:snapshot},result:{results:{JOINT_CP_SAT:{status:'OPTIMAL',proven_optimal:true,
          stats:{},paths:[{validator_status:'VALID',metrics:{makespan:125,execution_count:1},executions:[{activity_id:'a1',ordinal:1,start_time:120,end_time:125}]}]}}}};
      data=run;
    } else if(path==='planner-runs') data=run && url.searchParams.get('scenario_id')===project.id?[run]:[];
    else if(path==='planner-runs/window-run') data=run;
    else if(path==='planner-runs/window-run/progress') data={run_id:run.id,job_status:'FINISHED',status:'OPTIMAL',plan_version:1,progress_version:1};
    await route.fulfill({json:data??{}});
  });
  await page.goto('/');
  await page.getByRole('button',{name:'联合求解',exact:true}).click();
  await expect(page.getByRole('button',{name:'添加时间窗',exact:true})).toBeEnabled();
  return bodies;
}

test('日期窗口、同名活动、仅本次运行和冻结历史',async({page},testInfo)=>{
  const bodies=await mock(page);
  await page.getByLabel('开始日期时间',{exact:true}).fill('2026-11-05T08:00');
  await page.getByRole('button',{name:'添加时间窗',exact:true}).click();
  await page.getByLabel('绑定活动1',{exact:true}).selectOption('a1');
  await page.getByLabel('最早开始时间1',{exact:true}).fill('2026-11-05T10:00');
  await page.getByLabel('最晚完成时间1',{exact:true}).fill('2026-11-05T11:00');
  await page.getByRole('button',{name:'添加时间窗',exact:true}).click();
  await expect(page.getByLabel('绑定活动2',{exact:true}).locator('option[value="a1"]')).toBeDisabled();
  await page.getByLabel('搜索绑定活动2',{exact:true}).fill('调测包');
  await page.getByLabel('绑定活动2',{exact:true}).selectOption('a2');
  await page.getByLabel('最晚完成时间2',{exact:true}).fill('2026-11-05T12:00');
  await page.getByLabel('开始日期时间',{exact:true}).fill('2026-11-05T09:00');
  await expect(page.getByLabel('最早开始时间1',{exact:true})).toHaveValue('2026-11-05T10:00');
  await page.getByRole('button',{name:'开始联合求解',exact:true}).click();
  await expect.poll(()=>bodies.length).toBe(1);
  expect(bodies[0].activity_time_windows).toEqual([
    {activity_id:'a1',earliest_start_at:'2026-11-05T02:00:00.000Z',latest_finish_at:'2026-11-05T03:00:00.000Z'},
    {activity_id:'a2',earliest_start_at:null,latest_finish_at:'2026-11-05T04:00:00.000Z'}]);
  await expect(page.getByLabel('当次时间窗')).toContainText('冻结的活动名称');
  await expect(page.getByLabel('当次时间窗')).toContainText('本次未执行');
  expect(await page.evaluate(()=>localStorage.getItem('planner-form:windows-p'))).not.toContain('activity_time_windows');
  await page.screenshot({path:testInfo.outputPath('run-window-editor.png'),fullPage:true});
  await page.reload();await page.getByRole('button',{name:'联合求解',exact:true}).click();
  await expect(page.getByLabel('本次活动时间窗').locator('tbody tr')).toHaveCount(0);
  await expect(page.getByLabel('当次时间窗')).toContainText('冻结的活动名称');
  await page.getByRole('button',{name:'添加时间窗',exact:true}).click();
  await page.getByLabel('切换项目').click();await page.getByRole('menuitem',{name:'另一个项目'}).click();
  await expect(page.getByLabel('本次活动时间窗').locator('tbody tr')).toHaveCount(0);
});

test('窗口输入校验、两端留空和删除',async({page})=>{
  const bodies=await mock(page);
  await page.getByRole('button',{name:'添加时间窗',exact:true}).click();
  await page.getByLabel('最早开始时间1',{exact:true}).fill('2026-11-05T10:00');
  await expect(page.getByRole('button',{name:'开始联合求解',exact:true})).toBeDisabled();
  await page.getByLabel('绑定活动1',{exact:true}).selectOption('a1');
  await page.getByLabel('最晚完成时间1',{exact:true}).fill('2026-11-05T09:00');
  await expect(page.getByText('最晚完成时间不得早于最早开始时间。',{exact:true})).toBeVisible();
  await page.getByLabel('最早开始时间1',{exact:true}).fill('');
  await page.getByLabel('最晚完成时间1',{exact:true}).fill('');
  await page.getByRole('button',{name:'开始联合求解',exact:true}).click();
  await expect.poll(()=>bodies.length).toBe(1);
  expect(bodies[0].activity_time_windows).toBeUndefined();
  await page.getByLabel('删除时间窗1',{exact:true}).click();
  await expect(page.getByLabel('本次活动时间窗').locator('tbody tr')).toHaveCount(0);
});

test('隔离 PostgreSQL 与 worker：首次上电窗口和后续恢复',async({page,request},testInfo)=>{
  test.skip(!process.env.RUN_WINDOWS_ENV,'Requires isolated acceptance environment');
  const env=JSON.parse(readFileSync(process.env.RUN_WINDOWS_ENV!,'utf8'));
  const before=await(await request.get(`/api/v1/planner-scenarios/${env.project_id}`)).json();
  await page.addInitScript(id=>localStorage.setItem('planner-project',id),env.project_id);
  await page.goto('/');await page.getByRole('button',{name:'联合求解',exact:true}).click();
  await page.getByLabel('开始日期时间',{exact:true}).fill('2026-11-05T08:00');
  await page.getByRole('button',{name:'添加时间窗',exact:true}).click();
  await page.getByLabel('绑定活动1',{exact:true}).selectOption('power_on');
  await page.getByLabel('最早开始时间1',{exact:true}).fill('2026-11-05T08:10');
  await page.getByLabel('最晚完成时间1',{exact:true}).fill('2026-11-05T08:15');
  const pending=page.waitForResponse(r=>r.url().endsWith('/planner-runs/async')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'开始联合求解',exact:true}).click();
  const response=await pending;expect(response.status()).toBe(202);
  const queued=await response.json();
  await expect(page.locator('.result-banner')).toContainText('已证明最优',{timeout:90000});
  await expect(page.locator('.result-banner')).toContainText('285 分钟');
  const record=await(await request.get(`/api/v1/planner-runs/${queued.id}`)).json();
  const p=record.result.results.JOINT_CP_SAT.paths[0];
  expect(p.validator_status).toBe('VALID');
  const ons=p.executions.filter((e:any)=>e.activity_id==='power_on');
  expect(ons).toHaveLength(3);expect([ons[0].start_time,ons[0].end_time]).toEqual([10,15]);
  expect(ons.slice(1).every((e:any)=>e.start_time>15)).toBe(true);
  expect(await(await request.get(`/api/v1/planner-scenarios/${env.project_id}`)).json()).toEqual(before);
  await page.screenshot({path:testInfo.outputPath('real-window-solve.png'),fullPage:true});
  writeFileSync(testInfo.outputPath('real-run.json'),JSON.stringify(record,null,2));
  await page.reload();await page.getByRole('button',{name:'联合求解',exact:true}).click();
  await expect(page.getByLabel('当次时间窗')).toContainText('上电');
  await expect(page.getByLabel('本次活动时间窗').locator('tbody tr')).toHaveCount(0);
});
