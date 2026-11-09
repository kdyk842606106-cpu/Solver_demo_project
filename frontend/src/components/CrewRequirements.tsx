import { useState } from "react";
import { Plus } from "lucide-react";
import type { Scenario } from "../domain/model";

export default function CrewRequirements({
  s,
  value,
  onChange,
}: {
  s: Scenario;
  value: Record<string, number>;
  onChange: (v: Record<string, number>) => void;
}) {
  const [adding, setAdding] = useState(false);
  const crews = s.resources.filter((r) => r.kind === "crew");
  const selected = crews.filter((r) => Object.hasOwn(value, r.id));
  const rows = [...selected, ...(!selected.length || adding ? [null] : [])];
  return (
    <div className="crew-requirements span-2">
      {rows.map((r, i) => (
        <div className="form-grid crew-requirement-row" key={r?.id ?? "new"}>
          <label>
            责任组
            <select
              aria-label={i === 0 ? "责任组" : `责任组 ${i + 1}`}
              value={r?.id ?? ""}
              onChange={(e) => {
                const next = { ...value },
                  quantity = r ? next[r.id] : 1;
                if (r) delete next[r.id];
                if (e.target.value) next[e.target.value] = quantity;
                setAdding(false);
                onChange(next);
              }}
            >
              <option value="">
                {crews.length ? "请选择责任组" : "暂无责任组资源"}
              </option>
              {crews
                .filter(
                  (c) =>
                    c.id === r?.id ||
                    (!Object.hasOwn(value, c.id) && c.is_active !== false),
                )
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                    {crews.filter((x) => x.name === c.name).length > 1
                      ? ` · ${c.id.slice(-8)}`
                      : ""}
                  </option>
                ))}
            </select>
          </label>
          <label>
            作业人数
            <input
              aria-label={i === 0 ? "作业人数" : `作业人数 ${i + 1}`}
              type="number"
              required
              disabled={!r}
              min={1}
              max={r?.capacity}
              step={1}
              value={r ? value[r.id] : ""}
              placeholder="先选择责任组"
              title={r ? `责任组容量 ${r.capacity}` : undefined}
              onChange={(e) =>
                r && onChange({ ...value, [r.id]: Number(e.target.value) })
              }
            />
          </label>
        </div>
      ))}
      {!!selected.length &&
        !adding &&
        crews.some(
          (c) => !Object.hasOwn(value, c.id) && c.is_active !== false,
        ) && (
          <button
            type="button"
            className="text-action"
            onClick={() => setAdding(true)}
          >
            <Plus size={12} />
            添加责任组
          </button>
        )}
    </div>
  );
}
