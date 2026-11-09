import { useState } from "react";
import { CalendarDays, Plus, Pencil, Trash2 } from "lucide-react";
import { Modal, ConfirmDelete } from "./Fields";
import type {
  Scenario,
  Operation,
  WorkCalendar,
  WorkPeriod,
} from "../domain/model";
const days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
const defaults = [
  { start: "08:00", end: "12:00" },
  { start: "13:00", end: "17:00" },
];
function Periods({
  value,
  onChange,
  label,
}: {
  value: WorkPeriod[];
  onChange: (p: WorkPeriod[]) => void;
  label: string;
}) {
  return (
    <div>
      <div className="calendar-period-heading">
        <span>{label}</span>
        <button
          type="button"
          onClick={() => onChange([...value, { start: "08:00", end: "12:00" }])}
        >
          <Plus size={13} />
          增加时段
        </button>
      </div>
      {value.map((p, i) => (
        <div className="calendar-period-row" key={i}>
          <span>时段 {i + 1}</span>
          <input
            required
            type="time"
            aria-label={`${label} ${i + 1} 开始时间`}
            value={p.start}
            onChange={(e) =>
              onChange(
                value.map((v, j) =>
                  i === j ? { ...v, start: e.target.value } : v,
                ),
              )
            }
          />
          <span>至</span>
          <input
            required
            type="text"
            inputMode="numeric"
            pattern="([01][0-9]|2[0-3]):[0-5][0-9]|24:00"
            title="HH:MM，可填写 24:00 表示午夜"
            aria-label={`${label} ${i + 1} 结束时间`}
            value={p.end}
            onChange={(e) =>
              onChange(
                value.map((v, j) =>
                  i === j ? { ...v, end: e.target.value } : v,
                ),
              )
            }
          />
          <button
            type="button"
            aria-label={`删除${label}时段 ${i + 1}`}
            onClick={() => onChange(value.filter((_, j) => j !== i))}
          >
            <Trash2 size={13} />
          </button>
        </div>
      ))}
    </div>
  );
}
export default function CalendarPreview({
  s,
  stage,
}: {
  s: Scenario;
  stage: (ops: Operation[]) => void;
}) {
  const calendars = s.work_calendars ?? [];
  const [editing, setEditing] = useState<WorkCalendar | null>(null),
    [deleting, setDeleting] = useState<WorkCalendar | null>(null),
    [error, setError] = useState("");
  const update = (list: WorkCalendar[]) =>
    stage([
      { operation: "update_scenario", payload: { work_calendars: list } },
    ]);
  function save(e: React.FormEvent) {
    e.preventDefault();
    if (!editing) return;
    const valid = (ps: WorkPeriod[]) => {
      const sorted = [...ps].sort((a, b) => a.start.localeCompare(b.start));
      return sorted.every(
        (p, i) => p.start < p.end && (!i || sorted[i - 1].end <= p.start),
      );
    };
    if (
      !editing.name.trim() ||
      !editing.weekdays.length ||
      !editing.periods.length ||
      !valid(editing.periods) ||
      editing.exceptions.some((e) => !e.date || !valid(e.periods)) ||
      new Set(editing.exceptions.map((e) => e.date)).size !==
        editing.exceptions.length
    ) {
      setError(
        "请输入名称，至少选择一个工作日和时段；时段不能重叠或跨午夜，例外日期不能重复。",
      );
      return;
    }
    const item = { ...editing, name: editing.name.trim() };
    update(
      calendars.some((c) => c.id === item.id)
        ? calendars.map((c) => (c.id === item.id ? item : c))
        : [...calendars, item],
    );
    setEditing(null);
  }
  return (
    <div className="calendar-layout fidelity-calendar">
      <div className="capability-note">
        <CalendarDays size={18} />
        <div>
          <strong>按工作时段累计工时，休息时暂停续做</strong>
          <p>
            每次求解应用一个项目日历。日期例外覆盖每周规则；没有时段的例外日期为休息日。保存后需提交草稿。
          </p>
        </div>
      </div>
      <section className="calendar-panel">
        <div className="section-bar">
          <strong>工作日历</strong>
          <button
            className="primary-button"
            onClick={() => {
              setError("");
              setEditing({
                id: `calendar:${crypto.randomUUID()}`,
                name: "",
                weekdays: [0, 1, 2, 3, 4],
                periods: structuredClone(defaults),
                exceptions: [],
              });
            }}
          >
            <Plus size={14} />
            新增工作日历
          </button>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>日历名称</th>
                <th>每周工作日</th>
                <th>每日工作时段</th>
                <th>日期例外</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {calendars.map((c) => (
                <tr key={c.id}>
                  <td>
                    {c.name}
                    {s.work_calendar_id === c.id && <small> · 当前应用</small>}
                  </td>
                  <td>{c.weekdays.map((d) => days[d]).join("、")}</td>
                  <td>
                    {c.periods.map((p) => `${p.start}–${p.end}`).join(" / ")}
                  </td>
                  <td>{c.exceptions?.length ?? 0} 个</td>
                  <td>
                    <button
                      aria-label={`编辑日历${c.name}`}
                      onClick={() => {
                        setError("");
                        setEditing(
                          structuredClone({
                            ...c,
                            exceptions: c.exceptions ?? [],
                          }),
                        );
                      }}
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      aria-label={`删除日历${c.name}`}
                      onClick={() => setDeleting(c)}
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!calendars.length && (
            <div className="resource-empty">
              暂无工作日历，请新增后在联合求解页面选择
            </div>
          )}
        </div>
      </section>
      {(Boolean(s.calendar) || Boolean(s.calendars)) && (
        <details>
          <summary>旧版日历输入（尚未转换）</summary>
          <pre>{JSON.stringify(s.calendar ?? s.calendars, null, 2)}</pre>
          <p>旧格式会阻止求解，需明确转换后使用。</p>
        </details>
      )}
      {editing && (
        <Modal
          title="编辑工作日历"
          subtitle="项目统一日历 · 暂停续做"
          onClose={() => setEditing(null)}
        >
          <form onSubmit={save}>
            <div className="form-body">
              <label>
                日历名称
                <input
                  required
                  value={editing.name}
                  onChange={(e) =>
                    setEditing({ ...editing, name: e.target.value })
                  }
                />
              </label>
              <fieldset className="calendar-workdays">
                <legend>每周工作日</legend>
                <div>
                  {days.map((d, i) => (
                    <label key={d}>
                      <input
                        type="checkbox"
                        checked={editing.weekdays.includes(i)}
                        onChange={(e) =>
                          setEditing({
                            ...editing,
                            weekdays: e.target.checked
                              ? [...editing.weekdays, i].sort()
                              : editing.weekdays.filter((v) => v !== i),
                          })
                        }
                      />
                      {d}
                    </label>
                  ))}
                </div>
              </fieldset>
              <Periods
                label="每日工作时段"
                value={editing.periods}
                onChange={(periods) => setEditing({ ...editing, periods })}
              />
              <div className="calendar-period-heading">
                <strong>日期例外（休息或补班）</strong>
                <button
                  type="button"
                  onClick={() =>
                    setEditing({
                      ...editing,
                      exceptions: [
                        ...editing.exceptions,
                        { date: "", periods: [] },
                      ],
                    })
                  }
                >
                  添加日期例外
                </button>
              </div>
              {editing.exceptions.map((ex, i) => (
                <fieldset key={i}>
                  <label>
                    例外日期
                    <input
                      aria-label={`例外日期 ${i + 1}`}
                      required
                      type="date"
                      value={ex.date}
                      onChange={(e) =>
                        setEditing({
                          ...editing,
                          exceptions: editing.exceptions.map((x, j) =>
                            i === j ? { ...x, date: e.target.value } : x,
                          ),
                        })
                      }
                    />
                  </label>
                  <p>
                    {ex.periods.length
                      ? "按以下时段补班或调整工作时间"
                      : "全天休息"}
                  </p>
                  <Periods
                    label={`例外 ${i + 1} 工作时段`}
                    value={ex.periods}
                    onChange={(periods) =>
                      setEditing({
                        ...editing,
                        exceptions: editing.exceptions.map((x, j) =>
                          i === j ? { ...x, periods } : x,
                        ),
                      })
                    }
                  />
                  <button
                    type="button"
                    onClick={() =>
                      setEditing({
                        ...editing,
                        exceptions: editing.exceptions.filter(
                          (_, j) => j !== i,
                        ),
                      })
                    }
                  >
                    删除日期例外
                  </button>
                </fieldset>
              ))}
              <p className="form-help">
                跨午夜班次请分成午夜前、午夜后两个时段。所有活动共用所选日历，暂不支持人员或设备各自的班次日历。
              </p>
              {error && (
                <p role="alert" className="error-box">
                  {error}
                </p>
              )}
            </div>
            <footer className="modal-footer">
              <button type="button" onClick={() => setEditing(null)}>
                取消
              </button>
              <button className="primary-button" type="submit">
                保存到草稿
              </button>
            </footer>
          </form>
        </Modal>
      )}
      {deleting && (
        <ConfirmDelete
          title="删除工作日历"
          name={deleting.name}
          blocked={s.work_calendar_id === deleting.id}
          onClose={() => setDeleting(null)}
          onConfirm={() => {
            update(calendars.filter((c) => c.id !== deleting.id));
            setDeleting(null);
          }}
        >
          {s.work_calendar_id === deleting.id
            ? "此日历正在应用，请先在联合求解页面切换日历并提交。"
            : "历史运行保留当次日历快照。"}
        </ConfirmDelete>
      )}
    </div>
  );
}
