import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Search } from "lucide-react";
import type { Scenario } from "../domain/model";

function Check({
  checked,
  partial,
  label,
  onChange,
}: {
  checked: boolean;
  partial: boolean;
  label: string;
  onChange: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = partial;
  }, [partial]);
  return (
    <input
      ref={ref}
      type="checkbox"
      aria-label={label}
      checked={checked}
      onChange={onChange}
    />
  );
}
export default function StateTreeSelect({
  label,
  s,
  value,
  onChange,
  exclude = [],
  presetIds,
  onSavePreset,
  presetPending = false,
  onReviewPreset,
}: {
  label: string;
  s: Scenario;
  value: string[];
  onChange: (value: string[]) => void;
  exclude?: string[];
  presetIds?: string[];
  onSavePreset?: (value: string[]) => void;
  presetPending?: boolean;
  onReviewPreset?: () => void;
}) {
  const [open, setOpen] = useState(false),
    [expanded, setExpanded] = useState<string[]>([]),
    [query, setQuery] = useState("");
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", key);
    };
  }, [open]);
  const states = s.states.filter((x) => !exclude.includes(x.id));
  const preset = [...new Set(presetIds ?? [])].filter((id) => states.some((state) => state.id === id));
  const packages = [
    ...s.activity_packages,
    {
      id: "__unassigned",
      name: "未分配 / 已知状态",
      parent_id: null,
      level: 1,
      is_active: true,
    },
  ];
  const own = new Map<string, string[]>();
  for (const state of states) {
    let related = s.activities.filter(
      (a) =>
        a.output_state_id === state.id ||
        a.additional_output_state_ids.includes(state.id),
    );
    if (!related.length)
      related = s.activities.filter((a) =>
        a.preconditions.some((p) => p.state_id === state.id),
      );
    const ids = [
      ...new Set(
        s.activity_package_memberships
          .filter((m) => related.some((a) => a.id === m.activity_id))
          .map((m) => m.package_id),
      ),
    ];
    for (const id of ids.length ? ids : ["__unassigned"])
      own.set(id, [...(own.get(id) ?? []), state.id]);
  }
  function subtree(id: string, seen = new Set<string>()): string[] {
    if (seen.has(id)) return [];
    seen.add(id);
    return [
      ...new Set([
        ...(own.get(id) ?? []),
        ...packages
          .filter((p) => p.parent_id === id)
          .flatMap((p) => subtree(p.id, seen)),
      ]),
    ];
  }
  function toggle(ids: string[]) {
    onChange(
      ids.every((id) => value.includes(id))
        ? value.filter((id) => !ids.includes(id))
        : [...new Set([...value, ...ids])],
    );
  }
  function stateRow(id: string, depth: number) {
    const state = states.find((x) => x.id === id)!;
    const duplicate = states.filter((x) => x.name === state.name).length > 1;
    return (
      <label
        className="reference-state-leaf"
        key={id}
        style={{ paddingLeft: 14 + depth * 20 }}
      >
        <input
          type="checkbox"
          checked={value.includes(id)}
          onChange={() => toggle([id])}
        />
        <span>
          {state.name}
          {duplicate && <small>{id.slice(-12)}</small>}
        </span>
      </label>
    );
  }
  function branch(id: string, depth: number) {
    const p = packages.find((x) => x.id === id)!;
    const ids = subtree(id);
    if (!ids.length) return null;
    const count = ids.filter((id) => value.includes(id)).length,
      isOpen = expanded.includes(id);
    return (
      <div key={id}>
        <div
          className="reference-state-branch"
          style={{ paddingLeft: 8 + depth * 20 }}
        >
          <button
            type="button"
            className="icon-button"
            aria-label={`${isOpen ? "收起" : "展开"}${p.name}状态`}
            aria-expanded={isOpen}
            onClick={() =>
              setExpanded(
                isOpen ? expanded.filter((x) => x !== id) : [...expanded, id],
              )
            }
          >
            {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </button>
          <label>
            <Check
              checked={count === ids.length}
              partial={count > 0 && count < ids.length}
              label={`选择${p.name}下全部状态`}
              onChange={() => toggle(ids)}
            />
            {p.name}
          </label>
          <small>
            {count}/{ids.length}
          </small>
        </div>
        {isOpen && (
          <>
            {packages
              .filter((x) => x.parent_id === id)
              .map((x) => branch(x.id, depth + 1))}
            {(own.get(id) ?? []).map((id) => stateRow(id, depth + 1))}
          </>
        )}
      </div>
    );
  }
  const selectedNames = value.map(
    (id) => s.states.find((x) => x.id === id)?.name ?? "已失效状态",
  );
  const matchesPreset = value.length === preset.length && value.every(id => preset.includes(id));
  return (
    <div className="reference-state-select" ref={root}>
      <div className="state-select-label">
        <span className="field-label">{label}</span>
        <small aria-label={`${label}已选数量`}>已选 {value.length} 项</small>
      </div>
      <button
        type="button"
        className="reference-state-trigger"
        aria-label={label}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span
          className={!value.length ? "muted" : ""}
          title={selectedNames.join("、")}
        >
          {value.length
            ? selectedNames.join("、")
            : `按活动包展开并选择${label}`}
        </span>
        <ChevronDown size={14} />
      </button>
      {presetIds !== undefined && (
        <div className="state-preset-actions">
          <span>{presetPending ? "项目初始状态草稿" : "项目初始状态"} {preset.length} 项 · {presetPending ? "尚未保存，请提交草稿" : "已保存，请按实际情况确认"}</span>
          <button type="button" className="text-action" disabled={!preset.length}
            onClick={() => onChange(preset)}>
            恢复项目初始状态
          </button>
          {onSavePreset && <button type="button" className="text-action"
            disabled={matchesPreset}
            title="加入项目草稿，与活动关系一起提交后保存"
            onClick={() => onSavePreset([...new Set(value)])}>
            {matchesPreset ? (presetPending ? "已加入草稿" : "已是项目初始状态") : "设为项目初始状态"}
          </button>}
          {presetPending && onReviewPreset && <button type="button" className="text-action" onClick={onReviewPreset}>
            查看并提交初始状态草稿
          </button>}
        </div>
      )}
      {open && (
        <div
          className="reference-state-menu"
          role="group"
          aria-label={`${label}层级选项`}
        >
          <header>
            <span>按活动包层级选择</span>
            <button
              type="button"
              className="text-action"
              onClick={() => setExpanded(packages.map((p) => p.id))}
            >
              展开全部
            </button>
            <button
              type="button"
              className="text-action"
              disabled={!value.length}
              onClick={() => onChange([])}
            >
              清空
            </button>
          </header>
          <div className="state-menu-search">
            <Search size={13} />
            <input
              aria-label={`搜索${label}`}
              placeholder="搜索状态"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="reference-state-body">
            {query
              ? states
                  .filter((x) => x.name.includes(query))
                  .map((x) => stateRow(x.id, 0))
              : packages
                  .filter((x) => !x.parent_id)
                  .map((x) => branch(x.id, 0))}
            {!states.length && <p className="muted">暂无可选状态</p>}
          </div>
          <footer>
            {value.length} 个已选状态
            <button
              type="button"
              className="text-action"
              onClick={() => setOpen(false)}
            >
              完成
            </button>
          </footer>
        </div>
      )}
    </div>
  );
}
