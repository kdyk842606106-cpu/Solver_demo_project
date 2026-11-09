import { Plus, Trash2, Link2 } from "lucide-react";
import type { Scenario } from "../domain/model";
import { packageActivities, stateName } from "../domain/model";
export type Relation = {
  key: string;
  kind: "required" | "transition" | "delete";
  state: string;
};
const labels = {
  required: "依赖关系",
  transition: "转移关系",
  delete: "破坏效果",
};
export default function RelationEditor({
  s,
  value,
  onChange,
  name,
  output,
  onOutput,
  own,
  detailed = false,
}: {
  s: Scenario;
  value: Relation[];
  onChange: (r: Relation[]) => void;
  name: string;
  output: string;
  onOutput: (v: string) => void;
  own: string[];
  detailed?: boolean;
}) {
  const update = (key: string, patch: Partial<Relation>) =>
    onChange(value.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const states = s.states.filter((x) => !own.includes(x.id));
  return (
    <div className={`fidelity-relations ${detailed ? "detailed" : "compact"}`}>
      <div className="dependency-heading">
        <span>关系配置</span>
        <button
          type="button"
          className="text-action"
          onClick={() =>
            onChange([
              ...value,
              { key: crypto.randomUUID(), kind: "required", state: "" },
            ])
          }
        >
          <Plus size={13} />
          添加关系
        </button>
      </div>
      <div className="fidelity-relation-columns">
        <span>关系类型</span>
        <span>{detailed ? "来源" : "状态"}</span>
        {detailed && (
          <>
            <span>目标</span>
            <span>条件 / 效果</span>
          </>
        )}
        <span />
      </div>
      {value.map((r, index) => (
        <div className="fidelity-relation-row" key={r.key}>
          <select
            aria-label={`关系 ${index + 1} 类型`}
            value={r.kind}
            onChange={(e) =>
              update(r.key, { kind: e.target.value as Relation["kind"] })
            }
          >
            {Object.entries(labels).map(([id, text]) => (
              <option key={id} value={id}>
                {text}
              </option>
            ))}
          </select>
          {detailed && r.kind === "delete" ? (
            <input
              aria-label={`关系 ${index + 1} 来源`}
              readOnly
              value={name || "当前活动"}
            />
          ) : (
            <select
              required
              aria-label={`关系 ${index + 1} 状态`}
              value={r.state}
              onChange={(e) => update(r.key, { state: e.target.value })}
            >
              <option value="">请选择原子状态</option>
              {states.map((st) => (
                <option
                  key={st.id}
                  value={st.id}
                  disabled={value.some(
                    (x) => x.key !== r.key && x.state === st.id,
                  )}
                >
                  {st.name}
                  {states.filter((x) => x.name === st.name).length > 1
                    ? ` · ${st.id.slice(-12)}`
                    : ""}
                </option>
              ))}
            </select>
          )}
          {detailed &&
            (r.kind === "delete" ? (
              <select
                required
                aria-label={`关系 ${index + 1} 状态`}
                value={r.state}
                onChange={(e) => update(r.key, { state: e.target.value })}
              >
                <option value="">请选择原子状态</option>
                {states.map((st) => (
                  <option
                    key={st.id}
                    value={st.id}
                    disabled={value.some(
                      (x) => x.key !== r.key && x.state === st.id,
                    )}
                  >
                    {st.name}
                  </option>
                ))}
              </select>
            ) : (
              <input
                readOnly
                aria-label={`关系 ${index + 1} 目标`}
                value={
                  r.kind === "required"
                    ? name || "当前活动"
                    : output || `${name}完成`
                }
              />
            ))}
          {detailed && (
            <span
              className="relation-code"
              title="首期仅支持布尔状态；数值条件和增减运算暂不支持"
            >
              {r.kind === "required"
                ? "状态成立"
                : r.kind === "transition"
                  ? "消耗状态"
                  : "移除状态"}
            </span>
          )}
          <button
            type="button"
            className="icon-button"
            aria-label={`删除关系 ${index + 1}`}
            onClick={() => onChange(value.filter((x) => x.key !== r.key))}
          >
            <Trash2 size={14} />
          </button>
        </div>
      ))}
      <div className="fidelity-relation-row auto-achieve-row">
        <span className="fixed-relation-type">
          <strong>实现效果</strong>
          <small>自动绑定</small>
        </span>
        {detailed && (
          <input
            readOnly
            value={name || "当前活动"}
            aria-label="实现效果来源"
          />
        )}
        <input
          aria-label="实现效果名称"
          value={output}
          placeholder={`${name || "活动"}完成`}
          onChange={(e) => onOutput(e.target.value)}
        />
        {detailed && <span className="relation-code">产生状态</span>}
        <span className="relation-binding">
          <Link2 size={14} />
        </span>
      </div>
      {own.slice(1).map((id) => (
        <div className="preserved-effect" key={id}>
          附加实现效果：{stateName(s, id)} <span>保留已有绑定</span>
        </div>
      ))}
      <div className="relation-batch">
        <select
          aria-label="按活动包添加前置状态"
          value=""
          onChange={(e) => {
            const ids = packageActivities(s, e.target.value)
              .map(
                (id) => s.activities.find((a) => a.id === id)!.output_state_id,
              )
              .filter(
                (id) => !own.includes(id) && !value.some((r) => r.state === id),
              );
            onChange([
              ...value,
              ...[...new Set(ids)].map((state) => ({
                key: crypto.randomUUID(),
                kind: "required" as const,
                state,
              })),
            ]);
          }}
        >
          <option value="">按活动包批量添加前置状态…</option>
          {s.activity_packages.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>
      <p className="form-help">
        实现效果自动绑定，仅可改名。依赖保留状态，转移消耗状态，破坏使状态失效；状态包展开为原子状态并去重。
      </p>
    </div>
  );
}
