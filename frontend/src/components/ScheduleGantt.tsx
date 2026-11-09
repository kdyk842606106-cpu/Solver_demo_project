import { memo, useMemo, useRef, useState, useEffect } from "react";
import { Gantt, Willow, type ITask, type IApi, type IColumnConfig, type IScaleConfig } from "@svar-ui/react-gantt";
import "@svar-ui/react-gantt/all.css";
import "./schedule-gantt.css";
import type { Candidate, Run, Scenario } from "../domain/model";

type Segment = { start: number; end: number; label: string };
type ExecutionTask = ITask & {
  startMinute: number; endMinute: number; workSegments: Segment[]; details: string;
};

// The component positions the execution envelope. The template only paints the
// backend's working intervals within it; calendar gaps remain unoccupied.
function ExecutionBar({ data }: { data: ITask }) {
  const task = data as ExecutionTask;
  const span = task.endMinute - task.startMinute;
  return <div className="execution-bar" data-testid="gantt-execution" data-execution-id={task.id}
    title={task.details} aria-label={task.details}>
    {task.workSegments.map(segment => <span className="execution-work" key={segment.start}
      data-start-minute={segment.start} data-end-minute={segment.end}
      title={segment.label} style={{
        left: `${100 * (segment.start - task.startMinute) / span}%`,
        width: `${100 * (segment.end - segment.start) / span}%`,
      }}><span>{segment.end - segment.start} 分钟</span></span>)}
  </div>;
}

const columns: IColumnConfig[] = [
  { id: "text", header: "活动 / 执行序号", width: 250 },
  { id: "workMinutes", header: "工作分钟", width: 90 },
];
const emptyLinks: [] = [];
const scaleOptions = [
  { value: "auto", label: "总览", minutes: 0 },
  { value: "60", label: "1 小时", minutes: 60 },
  { value: "360", label: "6 小时", minutes: 360 },
  { value: "1440", label: "24 小时", minutes: 1440 },
];

export default memo(function ScheduleGantt({ candidate, snapshot, request }: {
  candidate: Candidate; snapshot?: Scenario; request: Run["request"];
}) {
  const [scale, setScale] = useState("auto");
  const api = useRef<IApi>(null);
  const position = useRef({ left: 0, top: 0 });
  const origin = snapshot?.start_time ?? 0;
  const timezone = request.display_timezone || "Asia/Shanghai";
  const base = request.display_start_at ? Date.parse(request.display_start_at) : Date.UTC(2000, 0, 1);
  const formatter = useMemo(() => new Intl.DateTimeFormat("zh-CN", {
    timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }), [timezone]);
  const hasDate = !!request.display_start_at;
  const format = useMemo(() => (date: Date) => hasDate ? formatter.format(date) :
    `${Math.round((date.getTime() - base) / 60000) + origin} 分钟`, [hasDate, formatter, base, origin]);
  const tasks = useMemo<ExecutionTask[]>(() => candidate.executions.map(t => {
    const activity = snapshot?.activities.find(a => a.id === t.activity_id);
    const date = (minute: number) => new Date(base + (minute - origin) * 60000);
    const intervals = snapshot?.working_intervals?.length ? snapshot.working_intervals : [[t.start_time, t.end_time]];
    const workSegments = intervals.map(([a, b]) => [Math.max(a, t.start_time), Math.min(b, t.end_time)])
      .filter(([a, b]) => a < b).map(([start, end]) => ({ start, end,
        label: `${format(date(start))} → ${format(date(end))} · ${end - start} 工作分钟` }));
    const resources = Object.entries(activity?.resource_reqs ?? {}).map(([id, n]) =>
      `${snapshot?.resources.find(r => r.id === id)?.name ?? id} × ${n}`).join("、");
    const text = `${activity?.name ?? t.activity_id} · 第 ${t.ordinal} 次`;
    return { id: JSON.stringify([t.activity_id, t.ordinal]), text,
      start: date(t.start_time), end: date(t.end_time), type: "task",
      startMinute: t.start_time, endMinute: t.end_time, workSegments,
      workMinutes: workSegments.reduce((sum, segment) => sum + segment.end - segment.start, 0),
      details: `${text}\n${format(date(t.start_time))} → ${format(date(t.end_time))}${resources ? `\n资源：${resources}` : ""}`,
    };
  }), [candidate, snapshot, base, origin, format]);
  const span = Math.max(1, candidate.metrics.makespan, ...candidate.executions.map(t => t.end_time - origin));
  const minutes = scale === "auto" ? Math.max(60, Math.ceil(span / 10 / 60) * 60) : Number(scale);
  // Minute/hour scales use elapsed time, not browser-local calendar days. All
  // labels use the run's timezone, including when the browser is in another zone.
  const scales = useMemo<IScaleConfig[]>(() => [{
    unit: "hour", step: minutes / 60, format,
  }], [minutes, format]);
  const start = useMemo(() => new Date(base), [base]);
  const end = useMemo(() => new Date(base + (span + minutes) * 60000), [base, span, minutes]);
  const previousTasks = useRef(tasks);
  useEffect(() => {
    if (previousTasks.current === tasks) return;
    previousTasks.current = tasks;
    const saved = { ...position.current };
    const frame = requestAnimationFrame(() => api.current?.exec("scroll-chart", saved));
    return () => cancelAnimationFrame(frame);
  }, [tasks]);

  return <section className="schedule-gantt" aria-label="执行实例甘特图" data-execution-count={tasks.length}>
    <div className="schedule-gantt-toolbar">
      <label>时间刻度 <select aria-label="甘特图时间刻度" value={scale} onChange={e => setScale(e.target.value)}>
        {scaleOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select></label>
      <button type="button" onClick={() => api.current?.exec("scroll-chart", { left: 0, top: 0 })}>回到起点</button>
      <span>{tasks.length} 次执行 · 总工期 {candidate.metrics.makespan} 分钟 · {hasDate ? timezone : "相对分钟"}</span>
      <small>蓝色为工作时段，条内空档为日历暂停；排程只读。</small>
    </div>
    <div className="schedule-gantt-canvas">
      <Willow fonts={false}>
        <Gantt ref={api} tasks={tasks} links={emptyLinks} columns={columns} gridWidth={340}
          scales={scales} start={start} end={end} lengthUnit="minute" durationUnit="hour"
          cellWidth={160 * 60 / minutes} cellHeight={38} scaleHeight={48} readonly autoScale={false}
          taskTemplate={ExecutionBar}
          onScrollChart={(ev: { left?: number; top?: number }) => {
            position.current = { left: ev.left ?? position.current.left, top: ev.top ?? position.current.top };
          }} />
      </Willow>
    </div>
  </section>;
});
