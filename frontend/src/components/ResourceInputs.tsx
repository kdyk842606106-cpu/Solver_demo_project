import { X } from "lucide-react";
import type { Scenario, ResourceKind } from "../domain/model";
export default function ResourceInputs({
  s,
  kind,
  label,
  value,
  onChange,
}: {
  s: Scenario;
  kind: ResourceKind;
  label: string;
  value: Record<string, number>;
  onChange: (v: Record<string, number>) => void;
}) {
  const resources = s.resources.filter(
    (r) => (r.kind ?? "unclassified") === kind,
  );
  const selected = resources.filter((r) => Object.hasOwn(value, r.id));
  const name = (id: string) => {
    const r = s.resources.find((r) => r.id === id)!;
    return (
      r.name +
      (s.resources.filter((x) => x.name === r.name).length > 1
        ? ` · ${r.id.slice(-8)}`
        : "")
    );
  };
  return (
    <div className="resource-token-field">
      <span className="field-label">{label}</span>
      <div className="resource-token-editor">
        {selected.map((r) => (
          <div className="tool-token" key={r.id}>
            <span>{name(r.id)}</span>
            <span className="tool-quantity-prefix">×</span>
            <input
              className="tool-quantity"
              aria-label={`${r.name}需求数量`}
              title={`容量 ${r.capacity}`}
              type="number"
              min={1}
              max={r.capacity}
              step={1}
              required
              value={value[r.id]}
              onChange={(e) =>
                onChange({ ...value, [r.id]: Number(e.target.value) })
              }
            />
            <button
              type="button"
              aria-label={`移除需求${r.name}`}
              onClick={() => {
                const next = { ...value };
                delete next[r.id];
                onChange(next);
              }}
            >
              <X size={12} />
            </button>
          </div>
        ))}
        <select
          aria-label={`添加${label}`}
          value=""
          onChange={(e) => {
            if (e.target.value) onChange({ ...value, [e.target.value]: 1 });
          }}
        >
          <option value="">
            {resources.length ? "选择资源…" : `暂无${label}资源`}
          </option>
          {resources
            .filter((r) => !value[r.id] && r.is_active !== false)
            .map((r) => (
              <option key={r.id} value={r.id}>
                {name(r.id)} · 容量 {r.capacity}
              </option>
            ))}
        </select>
      </div>
    </div>
  );
}
