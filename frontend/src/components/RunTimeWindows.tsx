import { useState } from 'react';
import type { ActivityTimeWindow, Candidate, Run, Scenario } from '../domain/model';
import { packageActivities } from '../domain/model';

export interface WindowRow { key: string; activity_id: string; earliest: string; latest: string }
export const localDateTime = (value: Date) => new Date(value.getTime() - value.getTimezoneOffset()*60000).toISOString().slice(0,16);

function availableActivities(s: Scenario) {
  const ids = s.activity_package_scope_ids?.length ? new Set(s.activity_package_scope_ids.flatMap(id=>packageActivities(s,id))) : null;
  return s.activities.filter(a=>a.is_active!==false && (!ids || ids.has(a.id)));
}

function timestamp(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value) || !Number.isFinite(date.getTime()) || localDateTime(date) !== value)
    throw new Error('日期时间无效，请填写所在时区实际存在的整分钟时间。');
  return date.toISOString();
}

export function serializeWindows(rows: WindowRow[], s: Scenario): ActivityTimeWindow[] {
  const seen = new Set<string>();
  const result: ActivityTimeWindow[] = [];
  for (const row of rows) {
    if (row.activity_id) {
      if (seen.has(row.activity_id)) throw new Error('同一活动只能配置一个本次时间窗。');
      seen.add(row.activity_id);
    }
    if (!row.earliest && !row.latest) continue;
    if (!availableActivities(s).some(a=>a.id===row.activity_id))
      throw new Error('请为每个已填写的时间窗选择有效活动。');
    const earliest = timestamp(row.earliest), latest = timestamp(row.latest);
    if (earliest && latest && latest < earliest) throw new Error('最晚完成时间不得早于最早开始时间。');
    result.push({ activity_id: row.activity_id, earliest_start_at: earliest, latest_finish_at: latest });
  }
  return result;
}

function activityLabel(s: Scenario, aid: string) {
  const a = s.activities.find(a=>a.id===aid);
  if (!a) return '活动不存在';
  const paths = s.activity_package_memberships.filter(m=>m.activity_id===aid).map(m=>{
    const names: string[] = [], seen = new Set<string>();
    let id: string | null = m.package_id;
    while (id && !seen.has(id)) {
      seen.add(id);
      const p = s.activity_packages.find(p=>p.id===id);
      if (!p) break;
      names.unshift(p.name); id=p.parent_id;
    }
    return names.join(' / ');
  });
  return [a.name,a.display_code,paths.join('、')].filter(Boolean).join(' · ');
}

function WindowEditorRow({row,index,s,rows,onChange,onRemove}: {
  row: WindowRow; index: number; s: Scenario; rows: WindowRow[];
  onChange: (row: WindowRow)=>void; onRemove: ()=>void;
}) {
  const [query,setQuery] = useState('');
  return <tr>
    <td><input type="search" aria-label={`搜索绑定活动${index+1}`} placeholder="搜索名称、编码或活动包" value={query} onChange={e=>setQuery(e.target.value)}/>
      <select aria-label={`绑定活动${index+1}`} value={row.activity_id} onChange={e=>onChange({...row,activity_id:e.target.value})}>
        <option value="">选择活动</option>
        {row.activity_id && !availableActivities(s).some(a=>a.id===row.activity_id) && <option value={row.activity_id}>原绑定活动已失效，请重新选择</option>}
        {availableActivities(s).filter(a=>a.id===row.activity_id || activityLabel(s,a.id).toLowerCase().includes(query.toLowerCase())).map(a=><option key={a.id} value={a.id}
          disabled={rows.some(other=>other.key!==row.key && other.activity_id===a.id)}>{activityLabel(s,a.id)}</option>)}
      </select></td>
    <td><input aria-label={`最早开始时间${index+1}`} type="datetime-local" step="60" value={row.earliest} onChange={e=>onChange({...row,earliest:e.target.value})}/></td>
    <td><input aria-label={`最晚完成时间${index+1}`} type="datetime-local" step="60" value={row.latest} onChange={e=>onChange({...row,latest:e.target.value})}/></td>
    <td>仅首次执行</td>
    <td><button type="button" aria-label={`删除时间窗${index+1}`} onClick={onRemove}>删除</button></td>
  </tr>;
}

export default function RunTimeWindows({s,rows,onChange,supported,zone,error}: {
  s: Scenario; rows: WindowRow[]; onChange: (rows: WindowRow[])=>void; supported: boolean; zone: string; error: string;
}) {
  return <section className="run-time-windows" aria-label="本次活动时间窗">
    <div className="section-bar"><strong>本次活动时间窗</strong><span className="muted">{zone} · 仅本次运行</span>
      <button type="button" disabled={!supported} onClick={()=>onChange([...rows,{key:crypto.randomUUID(),activity_id:'',earliest:'',latest:''}])}>添加时间窗</button>
      <button type="button" disabled={!rows.length} onClick={()=>onChange([])}>清空时间窗</button></div>
    <p className="form-help">最早开始、最晚完成均可留空；只约束首次执行，后续恢复执行不受此窗口限制。配置不修改项目，刷新或离开项目后清空。</p>
    {!supported && <p className="form-help">当前后端尚未提供本次活动时间窗，请更新后端后使用。</p>}
    {!!rows.length && <div className="window-table-scroll"><table className="window-table"><thead><tr><th>绑定活动</th><th>最早开始（可空）</th><th>最晚完成（可空）</th><th>适用范围</th><th>操作</th></tr></thead>
      <tbody>{rows.map((row,index)=><WindowEditorRow key={row.key} row={row} index={index} s={s} rows={rows}
        onChange={value=>onChange(rows.map(r=>r.key===row.key?value:r))} onRemove={()=>onChange(rows.filter(r=>r.key!==row.key))}/>)}</tbody></table></div>}
    {error && <p role="alert" className="error-box">{error}</p>}
    {!!s.time_windows?.length && <details className="legacy-window-note"><summary>项目已有时间窗（所有执行均受约束，与本次窗口同时生效）</summary>
      {s.time_windows.map(w=><p key={w.id}>{activityLabel(s,w.activity_id)}：计划开始后第 {w.earliest_start-s.start_time} 分钟起，第 {w.latest_finish-s.start_time} 分钟前完成。</p>)}</details>}
  </section>;
}

export function RunWindowHistory({run,candidate}: {run: Run; candidate?: Candidate}) {
  const windows = (run.request.activity_time_windows??[]).filter(w=>w.earliest_start_at || w.latest_finish_at);
  if (!windows.length) return null;
  const snapshot=run.request.effective_scenario_snapshot;
  const zone=run.request.display_timezone||'Asia/Shanghai';
  const date=(value: string|null)=>value?new Date(value).toLocaleString('zh-CN',{timeZone:zone,hour12:false}):'不限制';
  return <section className="run-time-windows window-history" aria-label="当次时间窗">
    <strong>当次时间窗</strong><span className="muted"> · {zone} · 仅首次执行</span>
    {windows.map(w=><p key={w.activity_id}>{snapshot?activityLabel(snapshot,w.activity_id):'历史活动'}：最早开始 {date(w.earliest_start_at)}；最晚完成 {date(w.latest_finish_at)}
      {candidate ? (candidate.executions.some(e=>e.activity_id===w.activity_id)?' · 已执行':' · 本次未执行') : ' · 尚无有效方案'}</p>)}
  </section>;
}
