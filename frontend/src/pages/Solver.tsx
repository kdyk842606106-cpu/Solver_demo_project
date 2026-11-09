import { lazy, Suspense, memo, useEffect, useState } from "react";
import { Play, RefreshCw, Clock, CheckCircle2 } from "lucide-react";
import { api } from "../api/client";
import type { Run, RunProgress, Candidate, Scenario, Operation } from "../domain/model";
import { Empty } from "../components/Fields";
import StateTreeSelect from "../components/StateTreeSelect";
import InitialStateCheck from '../components/InitialStateCheck';
import RunTimeWindows, { RunWindowHistory, serializeWindows, type WindowRow } from '../components/RunTimeWindows';
const ScheduleGantt = lazy(() => import("../components/ScheduleGantt"));
const labels: Record<string, string> = {
  BUILDING: "正在构建模型", FINDING_FIRST: "正在寻找首个可行方案",
  MAKESPAN: "正在优化总工期", EXECUTION_COUNT: "工期已证明最优 · 正在减少执行次数",
  QUEUED: "排队中",
  RUNNING: "求解中",
  FINISHED: "已结束",
  FAILED: "执行失败",
  OPTIMAL: "已证明最优",
  FEASIBLE: "已找到可行解",
  TIMEOUT_PARTIAL: "预算结束 · 已有可行解",
  TIMEOUT_EMPTY: "预算内未找到方案",
  INFEASIBLE: "已证明无解",
  UNKNOWN: "未确定",
  UNSUPPORTED: "不支持当前约束",
  ERROR: "求解错误",
};
function dateInput() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
export default function Solver({
  s,
  dirty,
  stage,
  initialPresetPending,
  onSaveInitialPreset,
  onReviewDrafts,
}: {
  s: Scenario;
  dirty: boolean;
  stage: (o: Operation[]) => void;
  initialPresetPending: boolean;
  onSaveInitialPreset: (ids: string[]) => void;
  onReviewDrafts: () => void;
}) {
  const [resultView, setResultView] = useState<"table" | "gantt" | "metrics">(
    "table",
  );
  const night=s.night_lift_rule??{enabled:false,night_start:"20:00",night_end:"08:00"};
  const changeNight=(patch:Partial<typeof night>)=>stage([{operation:"update_scenario",payload:{night_lift_rule:{...night,...patch}}}]);
  const exclusive=s.exclusive_rules??{crane:false,commissioning:false};
  const changeExclusive=(patch:Partial<typeof exclusive>)=>stage([{operation:"update_scenario",payload:{exclusive_rules:{...exclusive,...patch}}}]);
  const formKey = `planner-form:${s.id}`;
  const [windowRows,setWindowRows] = useState<WindowRow[]>([]);
  const [windowsSupported,setWindowsSupported] = useState(false);
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Shanghai';
  let windowError = '';
  try { serializeWindows(windowRows,s); } catch(e) { windowError = (e as Error).message; }
  useEffect(()=>setWindowRows([]),[s.id]);
  const [initial, setInitial] = useState<string[]>(() => {
    try {
      return (
        JSON.parse(localStorage.getItem(formKey) || "{}").initial ??
        s.initial_state_ids
      );
    } catch {
      return s.initial_state_ids;
    }
  });
  const [target, setTarget] = useState<string[]>(() => {
    try {
      return (
        JSON.parse(localStorage.getItem(formKey) || "{}").target ??
        s.goal_state_ids
      );
    } catch {
      return s.goal_state_ids;
    }
  });
  const [seed, setSeed] = useState(11),
    [start, setStart] = useState(() => {
      try {
        const saved=JSON.parse(localStorage.getItem(formKey)||"{}").start;
        return typeof saved === "string" && saved ? saved : dateInput();
      } catch { return dateInput(); }
    }),
    [submitting, setSubmitting] = useState(false),
    [error, setError] = useState(""),
    [networkError, setNetworkError] = useState(""),
    [runs, setRuns] = useState<Run[]>([]),
    [selected, setSelected] = useState<string | null>(null),
    [run, setRun] = useState<Run | null>(null),
    [progress, setProgress] = useState<RunProgress | null>(null),
    [refresh, setRefresh] = useState(0),
    [elapsed, setElapsed] = useState(0),
    [available, setAvailable] = useState<boolean | null>(null);
  useEffect(() => {
    localStorage.setItem(formKey, JSON.stringify({ initial, target, start }));
  }, [formKey, initial, target, start]);
  useEffect(() => {
    setError("");
  }, [initial, target, start, seed, s.revision, windowRows]);
  useEffect(() => {
    let alive = true;
    api
      .capabilities()
      .then((c) => {
        if (alive) setAvailable(c.planner_available && c.async_runs_supported);
        if (alive) setWindowsSupported(c.joint_cp_sat?.run_activity_time_windows_supported===true);
      })
      .catch((e) => {
        if (alive) setError(String(e));
      });
    return () => {
      alive = false;
    };
  }, []);
  useEffect(() => {
    let alive = true;
    let busy = false;
    let finished = false;
    let detail: Run | null = null;
    let latest: RunProgress | null = null;
    const controller = new AbortController();
    setProgress(null);
    setRun(null);
    async function poll() {
      if (busy || finished || !alive) return;
      busy = true;
      try {
        if (!detail) {
          const list = await api.runs(s.id, controller.signal);
          if (!alive) return;
          setRuns(list);
          const id = selected ?? list[0]?.id;
          if (!id) { finished = true; clearInterval(timer); setNetworkError(""); return; }
          detail = await api.run(id, controller.signal);
          if (!alive || detail.scenario_id !== s.id) return;
          setRun(detail);
        }
        const update = await api.progress(detail.id, latest?.plan_version ?? 0, controller.signal);
        if (!alive || update.run_id !== detail.id || update.scenario_id !== s.id ||
            (latest && update.progress_version < latest.progress_version)) return;
        latest = { ...update, candidate: update.candidate ??
          (latest?.plan_version === update.plan_version ? latest.candidate : null) };
        setProgress(latest);
        setNetworkError("");
        const active = ["QUEUED", "RUNNING"].includes(update.job_status);
        if (!active && (detail.job_status !== update.job_status || detail.status !== update.status)) {
          detail = await api.run(update.run_id, controller.signal);
          if (!alive) return;
        } else {
          detail = { ...detail, job_status: update.job_status, status: update.status,
            started_at: update.started_at, error_message: update.error_message };
        }
        setRun(detail);
        setRuns(rows => rows.map(row => row.id === update.run_id
          ? { ...row, status: update.status, job_status: update.job_status } : row));
        finished = !active;
        if (finished) clearInterval(timer);
      } catch (e) {
        if (alive) {
          setNetworkError(`状态查询失败，将自动重试：${String(e)}`);
        }
      } finally {
        busy = false;
      }
    }
    const timer = setInterval(poll, 5000);
    window.addEventListener("online", poll);
    void poll();
    return () => {
      alive = false;
      controller.abort();
      clearInterval(timer);
      window.removeEventListener("online", poll);
    };
  }, [s.id, selected, refresh]);
  useEffect(() => {
    if (!run?.started_at || run.job_status !== "RUNNING") return;
    const update = () =>
      setElapsed(
        Math.max(
          0,
          Math.floor((Date.now() - Date.parse(run.started_at!)) / 1000),
        ),
      );
    update();
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, [run?.started_at, run?.job_status]);
  async function solve() {
    setSubmitting(true);
    setError("");
    try {
      const activity_time_windows = serializeWindows(windowRows,s);
      if (activity_time_windows.length && !windowsSupported) throw new Error('当前后端不支持本次活动时间窗。');
      const body = {
        scenario_id: s.id,
        expected_revision: s.revision,
        current_state_ids: initial,
        target_state_ids: target,
        engine: "JOINT_CP_SAT",
        execution_bound_mode: "auto",
        seed,
        budget_mode: "auto",
        display_start_at: new Date(start).toISOString(),
        display_timezone:
          Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai",
        ...(activity_time_windows.length ? { activity_time_windows } : {}),
      };
      const key = `planner-submit:${s.id}`,
        signature = JSON.stringify(body);
      let previous;
      try {
        previous = JSON.parse(localStorage.getItem(key) || "null");
      } catch {
        previous = null;
      }
      const client_request_id =
        previous?.signature === signature ? previous.id : crypto.randomUUID();
      localStorage.setItem(
        key,
        JSON.stringify({ signature, id: client_request_id }),
      );
      const result = await api.solve({ ...body, client_request_id });
      localStorage.removeItem(key);
      setSelected(result.id);
      setRun(result);
      setRefresh((x) => x + 1);
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  }
  const result = run?.result?.results?.JOINT_CP_SAT,
    candidate = result?.paths?.find((p) => p.validator_status === "VALID") ??
      (run?.id === progress?.run_id && run?.job_status !== "FINISHED" && progress?.candidate?.validator_status === "VALID"
        ? progress.candidate : undefined),
    snapshot = run?.request?.effective_scenario_snapshot;
  const canSolve =
    !dirty &&
    !submitting &&
    !windowError &&
    available === true &&
    initial.length > 0 &&
    target.length > 0 &&
    !!start;

  return (
    <div className="reference-solver">
      <div className="solver-run-toolbar">
        <button
          className="primary-button"
          aria-label="开始联合求解"
          disabled={!canSolve}
          onClick={() => void solve()}
        >
          <Play size={14} />
          {submitting ? "提交中…" : "求解"}
        </button>
      </div>
      <section className="reference-solver-setup">
        <div className="reference-state-config">
          <h3>状态与时间配置</h3>
          <div className="reference-state-fields">
            <StateTreeSelect
              label="当前状态"
              s={s}
              value={initial}
              onChange={setInitial}
              presetIds={s.initial_state_ids}
              onSavePreset={onSaveInitialPreset}
              presetPending={initialPresetPending}
              onReviewPreset={onReviewDrafts}
            />
            <StateTreeSelect
              label="目标状态"
              s={s}
              value={target}
              onChange={setTarget}
              exclude={s.forbidden_state_ids}
            />
            <label>
              工作日历
              <select aria-label="工作日历" value={s.work_calendar_id ?? ""} onChange={e=>stage([{operation:"update_scenario",payload:{work_calendar_id:e.target.value||null}}])}>
                <option value="">连续自然分钟（不使用日历）</option>
                {(s.work_calendars??[]).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
            <label>
              开始日期时间
              <input
                aria-label="开始日期时间"
                type="datetime-local"
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </label>
          </div>
          <small className="time-help">
            {s.work_calendar_id || night.enabled || windowRows.some(w=>w.earliest||w.latest) ? "开始时间参与日历、夜班或时间窗计算 · " : "开始时间仅用于时间轴显示 · "}
            {Intl.DateTimeFormat().resolvedOptions().timeZone}
          </small>
        </div>
        <div className="reference-principles">
          <h3>
            计划制定原则 <small>作业独占及夜班限制已支持</small>
          </h3>
          <div>
            <label className="night-lift-toggle" title="有行吊资源需求的活动执行期间，不允许任何其他活动并行">
              <input type="checkbox" checked={exclusive.crane} onChange={e=>changeExclusive({crane:e.target.checked})}/>
              行吊作业独占
            </label>
            <label className="night-lift-toggle" title="活动类型为功能调测的活动执行期间，不允许任何其他活动并行">
              <input type="checkbox" checked={exclusive.commissioning} onChange={e=>changeExclusive({commissioning:e.target.checked})}/>
              调测作业独占
            </label>
            {[
              "按活动包连续",
              "按责任组连续",
            ].map((label) => (
              <label key={label} title="联合求解暂不支持此约束">
                <input type="checkbox" disabled checked={false} />
                {label}
              </label>
            ))}
            <label className="night-lift-toggle">
              <input type="checkbox" checked={night.enabled} onChange={e=>changeNight({enabled:e.target.checked})}/>
              精密易损吊装禁止夜班
            </label>
          </div>
          {(exclusive.crane||exclusive.commissioning)&&<p className="form-help">独占作业从开始到完成期间，不允许任何其他活动并行；等待开工时不占场。行吊按资源需求识别，调测按“功能调测”类型识别。修改后请提交草稿。</p>}
          {night.enabled&&<div className="form-grid night-lift-options">
            <label>夜班开始<input aria-label="夜班开始" type="time" required value={night.night_start} onChange={e=>changeNight({night_start:e.target.value})}/></label>
            <label>次日结束<input aria-label="夜班结束" type="time" required value={night.night_end} onChange={e=>changeNight({night_end:e.target.value})}/></label>
            <p className="span-2 form-help">仅约束有行吊需求且标记精密易损的活动；整项须在白天完成，不能跨夜续做。白天休息按日历暂停；其他活动仍可夜间执行。修改后请提交草稿。</p>
          </div>}
          <details className="solver-advanced">
            <summary>
              求解参数{" "}
              <span>
                预算与执行规模自动设置 ·{" "}
                {s.execution_mode === "parallel" ? "并行" : "串行"}
              </span>
            </summary>
            <div className="form-grid">
              <div className="automatic-bound-note">
                <span className="field-label">求解预算</span>
                <p>由系统按活动规模自动分配，求解完成后提前结束，无需填写。</p>
              </div>
              <label>
                随机种子
                <input
                  type="number"
                  value={seed}
                  onChange={(e) => setSeed(Number(e.target.value))}
                />
              </label>
              <div className="automatic-bound-note">
                <span className="field-label">执行规模</span>
                <p>
                  由系统根据活动数量、单项限制及重复恢复需求自动设置，无需填写。
                </p>
              </div>
              <label>
                执行模式
                <select
                  aria-label="执行模式"
                  value={s.execution_mode}
                  onChange={(e) =>
                    stage([
                      {
                        operation: "update_scenario",
                        payload: { execution_mode: e.target.value },
                      },
                    ])
                  }
                >
                  <option value="parallel">并行</option>
                  <option value="serial">串行</option>
                </select>
              </label>
            </div>
          </details>
        </div>
      </section>
      <InitialStateCheck s={s} dirty={dirty} initial={initial} target={target} onChange={setInitial}/>
      <RunTimeWindows s={s} rows={windowRows} onChange={setWindowRows} supported={windowsSupported} zone={zone} error={windowError}/>
      {dirty && (
        <div className="notice">请先提交草稿，再使用已保存版本求解。</div>
      )}
      {available === false && (
        <div className="error-box">联合求解环境不可用，请检查后端服务。</div>
      )}
      {error && (
        <pre role="alert" className="error-box">
          {error}
        </pre>
      )}
      {networkError && (
        <div role="alert" className="error-box">
          {networkError}
        </div>
      )}
      <section className="reference-plan-result" aria-live="polite">
        <div className="section-bar reference-result-heading">
          <strong>计划结果</strong>
          <div
            className="result-view-tabs"
            role="tablist"
            aria-label="结果视图"
          >
            {(
              [
                ["table", "活动计划"],
                ["gantt", "甘特图"],
                ["metrics", "求解指标"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                role="tab"
                aria-selected={resultView === id}
                onClick={() => setResultView(id)}
              >
                {label}
              </button>
            ))}
          </div>
          <select
            aria-label="运行历史"
            value={selected ?? runs[0]?.id ?? ""}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="" disabled>
              暂无运行记录
            </option>
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {new Date(r.created_at).toLocaleString("zh-CN")} ·{" "}
                {labels[
                  r.job_status === "RUNNING" || r.job_status === "QUEUED"
                    ? r.job_status
                    : r.status
                ] ?? r.status}
              </option>
            ))}
          </select>
          <button
            className="icon-button"
            title="刷新历史"
            aria-label="刷新历史"
            onClick={() => setRefresh((x) => x + 1)}
          >
            <RefreshCw size={13} />
          </button>
        </div>
        {!run ? (
          <Empty>
            <Clock size={24} />
            <strong>尚未生成计划</strong>
            <p>选择当前状态、目标状态与开始日期时间，点击右上角“求解”。</p>
          </Empty>
        ) : (
          <>
            <div className="result-banner">
              <strong>
                {run.request.execution_bound?.heuristic &&
                ["OPTIMAL", "INFEASIBLE"].includes(run.status)
                  ? "本次自动搜索范围内 · "
                  : ""}
                {labels[
                  run.job_status === "RUNNING" || run.job_status === "QUEUED" || run.job_status === "FAILED"
                    ? run.job_status
                    : run.status
                ] ?? run.status}
              </strong>
              <span>
                {run.job_status === "RUNNING"
                  ? `${labels[progress?.metrics?.phase ?? "BUILDING"]} · 已运行 ${elapsed} 秒`
                  : run.job_status === "QUEUED"
                    ? "等待后台任务执行"
                    : candidate
                      ? `${candidate.executions.length} 步活动 · 总工期 ${candidate.metrics.makespan} 分钟 · 回放校验 VALID`
                      : run.job_status === "FAILED"
                        ? "任务执行中断"
                        : "本次运行已结束"}
              </span>
            </div>
            {run.error_message && (
              <pre className="error-box">{run.error_message}</pre>
            )}
            <RunWindowHistory run={run} candidate={candidate}/>
            {progress?.run_id === run.id && progress.metrics && (
              <div className="search-progress" aria-label="实时求解指标">
                <span>当前最好工期 <b>{progress.metrics.best_makespan ?? "—"}</b> 分钟</span>
                <span>工期下界 <b>{progress.metrics.lower_bound ?? "—"}</b> 分钟</span>
                <span>执行次数 <b>{progress.metrics.best_execution_count ?? "—"}</b></span>
                <span>求解线程 <b>{progress.metrics.worker_threads ?? 1}</b></span>
                <span>{(progress.metrics.worker_threads ?? 1) > 1 ? "报告分支" : "搜索分支"} <b>{progress.metrics.branches ?? "—"}</b></span>
                <span>搜索速度 <b>{progress.metrics.branches_per_second ?? "—"}</b> 分支/秒</span>
                <span>冲突 <b>{progress.metrics.conflicts ?? "—"}</b></span>
                <span>已校验候选 <b>{progress.metrics.candidate_count}</b></span>
                <small>最近采样 {progress.metrics.sampled_at ? new Date(progress.metrics.sampled_at).toLocaleTimeString() : "—"}
                  {" · "}最近改善 {progress.metrics.last_improved_at ? new Date(progress.metrics.last_improved_at).toLocaleTimeString() : "—"}
                  {run.job_status === "RUNNING" && " · 每 5 秒刷新"}</small>
                {(progress.metrics.worker_threads ?? 1) > 1 && <small>分支及冲突为主搜索器的分阶段报告，非全部线程合计；暂不提供跨线程搜索速度。</small>}
              </div>
            )}
            {resultView === "metrics" && result && (
              <div className="reference-metrics">
                <div className="metric-grid">
                  <div>
                    <small>总工期</small>
                    <strong>
                      {candidate?.metrics.makespan ?? "—"} <em>分钟</em>
                    </strong>
                  </div>
                  <div>
                    <small>活动执行实例</small>
                    <strong>{candidate?.metrics.execution_count ?? "—"}</strong>
                  </div>
                  <div>
                    <small>工期下界</small>
                    <strong>{result.lower_bound ?? "—"}</strong>
                  </div>
                  <div>
                    <small>求解耗时</small>
                    <strong>
                      {result.elapsed_seconds?.toFixed(2) ?? "—"} <em>秒</em>
                    </strong>
                  </div>
                </div>
                <div className="notice">
                  <CheckCircle2 size={14} />
                  {result.proven_optimal
                    ? "已证明最优"
                    : result.proven_infeasible
                      ? "已证明无解"
                      : "未证明最优"}
                  ；证明范围受总执行次数与单活动上限约束。{result.error}
                  {candidate && result.stats?.tie_breaker === "minimize_execution_count" && (
                    <p>{result.stats.execution_count_proven_optimal
                      ? "已证明在最短工期下，活动执行次数最少。"
                      : result.stats.makespan_proven_optimal
                        ? "最短工期已证明，活动执行次数是否最少仍未确定。"
                        : "当前方案已通过校验，最短工期和最少执行次数均未证明。"}</p>
                  )}
                  {snapshot?.night_lift_rule?.enabled&&<p>当次夜班限制：{snapshot.night_lift_rule.night_start}–次日{snapshot.night_lift_rule.night_end}禁止精密易损吊装，整项不得跨夜。</p>}
                  <p>当次作业独占：{[snapshot?.exclusive_rules?.crane&&"行吊作业",snapshot?.exclusive_rules?.commissioning&&"调测作业"].filter(Boolean).join("、")||"未启用"}。启用的作业执行期间禁止其他活动并行。</p>
                  {snapshot?.work_calendar_id && <p>工作日历：{snapshot.work_calendars?.find(c=>c.id===snapshot.work_calendar_id)?.name}；活动时长为工作分钟，总工期包含休息等待。甘特图空档表示暂停。</p>}
                  {run?.request.budget_allocation && (
                    <p>本次系统分配预算：{run.request.budget_allocation.time_limit_seconds} 秒。</p>
                  )}
                  {run?.request.execution_bound && (
                    <p>
                      本次系统设置：最多 {run.request.execution_bound.value}{" "}
                      次执行。
                      {run.request.execution_bound.heuristic
                        ? "含重复执行预留；这是有限搜索范围，不代表对任意次数的全局证明。"
                        : "已覆盖当前所有单活动执行次数限制。"}
                    </p>
                  )}
                </div>
              </div>
            )}
            {candidate && <ScheduleView key={run.id} candidate={candidate} snapshot={snapshot} request={run.request} resultView={resultView} />}
            {!candidate &&
              run.job_status === "FINISHED" &&
              resultView !== "metrics" && (
                <Empty>
                  {run.status === "TIMEOUT_EMPTY"
                    ? "本次系统预算内尚未找到可交付方案，尚不能判定无解。"
                    : run.status === "INFEASIBLE"
                      ? "在当前约束与执行次数范围内，已证明不存在方案。"
                      : "本次运行未交付通过校验的方案。"}
                </Empty>
              )}
          </>
        )}
      </section>
    </div>
  );
}

const ScheduleView = memo(function ScheduleView({ candidate, snapshot, request, resultView }: {
  candidate: Candidate; snapshot?: Scenario; request: Run["request"]; resultView: string;
}) {
  const tasks = candidate.executions, origin = snapshot?.start_time ?? 0;
  const displayTime = (minute: number) => {
    if (!request.display_start_at) return `${minute} 分钟`;
    const date = new Date(
      Date.parse(request.display_start_at) + (minute - origin) * 60000,
    );
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: request.display_timezone || "Asia/Shanghai",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);
  };
  const taskResources = (activityId: string, kind?: string) => {
    const a = snapshot?.activities.find((a) => a.id === activityId);
    return (
      Object.entries(a?.resource_reqs ?? {})
        .filter(
          ([id]) =>
            !kind ||
            snapshot?.resources.find((r) => r.id === id)?.kind === kind,
        )
        .map(
          ([id, n]) =>
            `${snapshot?.resources.find((r) => r.id === id)?.name ?? id} × ${n}`,
        )
        .join("、") || "—"
    );
  };
  return (
              <>
                {!tasks.length && (
                  <Empty>目标状态已经满足，无需执行活动。</Empty>
                )}
                {resultView === "table" && tasks.length > 0 && (
                  <div className="table-scroll">
                    <table className="reference-result-table">
                      <thead>
                        <tr>
                          <th>序号</th>
                          <th>活动名称</th>
                          <th>活动开始时间</th>
                          <th>活动结束时间</th>
                          <th>活动包</th>
                          <th>责任组</th>
                          <th>时长</th>
                          <th>行吊</th>
                          <th>作业空间</th>
                          {snapshot?.resources.some((r) => r.kind === "material") && <th>周转物料</th>}
                        </tr>
                      </thead>
                      <tbody>
                        {tasks.map((t, i) => {
                          const a = snapshot?.activities.find(
                            (a) => a.id === t.activity_id,
                          );
                          const packages =
                            snapshot?.activity_package_memberships
                              ?.filter((m) => m.activity_id === t.activity_id)
                              .map(
                                (m) =>
                                  snapshot.activity_packages.find(
                                    (p) => p.id === m.package_id,
                                  )?.name,
                              )
                              .filter(Boolean);
                          return (
                            <tr key={`${t.activity_id}#${t.ordinal}`}>
                              <td>
                                <span className="solver-step">
                                  {String(i + 1).padStart(2, "0")}
                                </span>
                              </td>
                              <td>
                                <strong>{a?.name ?? t.activity_id}</strong>
                                <small>
                                  {t.ordinal > 1
                                    ? `第 ${t.ordinal} 次执行`
                                    : ""}
                                </small>
                              </td>
                              <td>{displayTime(t.start_time)}</td>
                              <td>{displayTime(t.end_time)}</td>
                              <td>{packages?.join("、") || "未分配"}</td>
                              <td>{taskResources(t.activity_id, "crew")}</td>
                              <td>{a?.duration ?? t.end_time - t.start_time} 工作分钟</td>
                              <td>{taskResources(t.activity_id, "crane")}</td>
                              <td>
                                {taskResources(t.activity_id, "workspace")}
                              </td>
                              {snapshot?.resources.some((r) => r.kind === "material") && <td>{taskResources(t.activity_id, "material")}</td>}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
                {resultView === "gantt" && tasks.length > 0 && (
                  <Suspense fallback={<div className="notice">正在加载甘特图…</div>}>
                    <ScheduleGantt candidate={candidate} snapshot={snapshot} request={request} />
                  </Suspense>
                )}
              </>
  );
});
