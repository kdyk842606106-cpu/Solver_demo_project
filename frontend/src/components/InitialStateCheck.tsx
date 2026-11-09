import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { Scenario } from '../domain/model';
import { Modal } from './Fields';
import './initial-state-check.css';

interface ActivityInfo { id: string; name: string; display_code?: string; package_paths: string[]; is_active: boolean; in_scope: boolean }
interface StateSuggestion {
  id: string; name: string; confirmable: boolean; is_goal: boolean; forbidden_at_finish: boolean;
  producer_activities: ActivityInfo[]; consumer_activities: ActivityInfo[];
}
export interface InitialDiagnosis {
  scenario_id: string; revision: number; source: 'saved' | 'draft'; input_signature: string;
  status: 'INVALID_INPUT' | 'STRUCTURALLY_BLOCKED' | 'STRUCTURALLY_REACHABLE';
  activity_count: number; already_satisfied_goal_ids: string[];
  input_issues: { code: string; message: string }[];
  blocked_goals: { id: string; name: string; blocked_activities: { id: string; name: string; missing_preconditions: {id: string; name: string}[] }[] }[];
  groups: { reason: string; message: string; states: StateSuggestion[]; affected_goals: {id: string; name: string}[] }[];
}
const reasonLabels: Record<string, string> = {
  missing_initial_fact: '缺少起始事实', dependency_cycle: '循环缺少起点', provider_unavailable: '产生者不可用',
};
const activityLabel = (a: ActivityInfo) => `${a.name}${a.display_code ? ` · ${a.display_code}` : ''}${a.package_paths.length ? ` · ${a.package_paths.join('、')}` : ''}`;

export default function InitialStateCheck({ s, dirty, initial, target, onChange }: {
  s: Scenario; dirty: boolean; initial: string[]; target: string[]; onChange: (ids: string[]) => void;
}) {
  const signature = JSON.stringify({ s, dirty, initial, target });
  const latest = useRef(signature); latest.current = signature;
  const serial = useRef(0), controller = useRef<AbortController | null>(null);
  const [result, setResult] = useState<{key: string; value: InitialDiagnosis} | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [pending, setPending] = useState<{state: StateSuggestion; key: string} | null>(null);
  const [undo, setUndo] = useState<StateSuggestion | null>(null);
  const [recheck, setRecheck] = useState(false);
  const stale = !!result && result.key !== signature;
  useEffect(() => {
    serial.current++; controller.current?.abort(); setBusy(false); setError(''); setPending(null);
    return () => { serial.current++; controller.current?.abort(); };
  }, [signature]);
  async function check() {
    const key = signature, requestId = ++serial.current;
    controller.current?.abort(); controller.current = new AbortController();
    setBusy(true); setError('');
    try {
      const value = await api.checkInitialStates(s.id, {
        expected_revision: s.revision, current_state_ids: initial, target_state_ids: target,
        ...(dirty ? { draft_scenario: s } : {}),
      }, controller.current.signal);
      if (serial.current === requestId && latest.current === key && value.scenario_id === s.id && value.revision === s.revision)
        setResult({key, value});
    } catch (e) {
      if (serial.current === requestId && latest.current === key) setError(String(e));
    } finally { if (serial.current === requestId && latest.current === key) setBusy(false); }
  }
  useEffect(() => { if (recheck) { setRecheck(false); void check(); } }, [signature, recheck]);
  function confirm() {
    if (!pending || pending.key !== signature || stale || !pending.state.confirmable || initial.includes(pending.state.id)) return;
    setUndo(pending.state); onChange([...initial, pending.state.id]); setPending(null); setRecheck(true);
  }
  return <section className="initial-state-check" aria-label="初始状态诊断">
    <div className="initial-check-heading"><div><strong>初始状态检查</strong><small>检查本次目标与活动范围 · {dirty ? '当前草稿' : `已保存 V${s.revision}`} · 不修改项目</small></div>
      <button type="button" onClick={() => void check()} disabled={busy || !target.length}>{busy ? '检查中…' : '检查初始状态'}</button></div>
    <p className="initial-check-help">仅检查状态关系的宽松可达性。资源、时间窗、日历和状态破坏仍需正式求解验证；建议不代表现场事实。</p>
    {undo && initial.includes(undo.id) && <div className="initial-check-notice">已确认并加入：{undo.name}。仅更新当前选择。 <button type="button" onClick={() => {onChange(initial.filter(id => id !== undo.id)); setUndo(null); setRecheck(true);}}>撤销此次确认</button></div>}
    {error && <div role="alert" className="initial-check-error">{error}</div>}
    {stale && <div role="status" className="initial-check-notice">配置已变化，请重新检查。下方为上次诊断，确认操作已停用。</div>}
    {result && <div className={stale ? 'initial-check-results stale' : 'initial-check-results'}>
      <div role="status" className="initial-check-status">{result.value.status === 'STRUCTURALLY_REACHABLE' ? '结构预检通过 · 不代表保证有解' : result.value.status === 'INVALID_INPUT' ? '请先修正输入' : '发现结构阻塞 · 请确认实际状态或检查活动关系'} <small>范围内 {result.value.activity_count} 个活动</small></div>
      {result.value.input_issues.map((i,n) => <p key={n} className="initial-check-error">{i.message}</p>)}
      {result.value.already_satisfied_goal_ids.length > 0 && <p className="initial-check-notice">部分或全部目标已被选为当前状态。请确认这符合实际；全部目标及终态要求已满足时，可能得到零步方案。</p>}
      {result.value.blocked_goals.length > 0 && <details><summary>查看受阻目标及其直接依赖</summary>{result.value.blocked_goals.map(g => <div key={g.id}><strong>{g.name}</strong>{g.blocked_activities.map(a => <p key={a.id}>活动“{a.name}”缺少：{a.missing_preconditions.map(p => p.name).join('、')}</p>)}</div>)}</details>}
      {result.value.groups.map((g,n) => <article className="initial-check-group" key={n}>
        <h4>{reasonLabels[g.reason] ?? g.reason}</h4><p>{g.message}</p>
        <small>影响目标：{g.affected_goals.map(x => x.name).join('、')}。候选涉及不同路径，不要求全部补齐；单项确认后重新检查。</small>
        {g.states.map(state => <div className="initial-check-state" key={state.id}>
          <div><strong>{state.name}</strong>{s.states.filter(x => x.name === state.name).length > 1 && <small className="state-id">同名状态标识：{state.id}</small>}
            {state.producer_activities.length > 0 && <small>产生于：{state.producer_activities.map(a => `${activityLabel(a)}${!a.is_active ? '（已停用）' : !a.in_scope ? '（范围外）' : ''}`).join('；')}</small>}
            {state.consumer_activities.length > 0 && <small>被读取：{state.consumer_activities.map(activityLabel).join('；')}</small>}
            {state.forbidden_at_finish && <small>终态要求消除该状态；它可以在开始时成立。</small>}
            {state.is_goal && <small>这是本次目标，不作为补齐捷径；若确实已完成，请在当前状态选择器中明确选择。</small>}
            {g.reason === 'provider_unavailable' && <small>请在活动全集检查启用情况及项目求解范围，不用完成状态代替未执行活动。</small>}
          </div>
          {state.confirmable && <button type="button" disabled={stale || busy} onClick={() => setPending({state, key: signature})}>确认此状态…</button>}
        </div>)}
      </article>)}
    </div>}
    {pending && pending.key === signature && <Modal title="确认当前事实" onClose={() => setPending(null)}>
      <div className="form-body"><p>你正在确认：<strong>{pending.state.name}</strong></p><p>该状态在计划开始时已经成立，而不是希望求解器以后完成它。</p>
        {pending.state.producer_activities.length > 0 && <p>这是一项活动效果，请确认相关工作确实已完成且该状态仍有效。</p>}
        <p>确认后仅加入本次当前状态并重新检查，不修改项目默认状态、不提交草稿、不自动求解。</p></div>
      <footer className="modal-footer"><button type="button" onClick={() => setPending(null)}>取消</button><button type="button" className="primary-button" onClick={confirm}>确认当前已成立并加入</button></footer>
    </Modal>}
  </section>;
}
