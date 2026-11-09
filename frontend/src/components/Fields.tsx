import { useEffect, useRef, type ReactNode } from "react";
import { X, AlertTriangle, Trash2 } from "lucide-react";
import type { Scenario } from "../domain/model";
import { packageActivities } from "../domain/model";
export function Modal({
  title,
  children,
  onClose,
  drawer = false,
  subtitle,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  drawer?: boolean;
  subtitle?: string;
  wide?: boolean;
}) {
  const root = useRef<HTMLElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const panel = root.current!;
    const focusables = () =>
      Array.from(
        panel.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]',
        ),
      ).filter((el) => el.getClientRects().length);
    if (!panel.contains(document.activeElement))
      (
        panel.querySelector<HTMLElement>("[autofocus]") ??
        focusables()[1] ??
        panel
      ).focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        close.current();
      }
      if (e.key === "Tab") {
        const items = focusables(),
          first = items[0],
          last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    panel.addEventListener("keydown", key);
    return () => {
      panel.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, []);
  return (
    <div
      className={`modal-backdrop ${drawer ? "drawer-backdrop" : ""}`}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        ref={root}
        tabIndex={-1}
        className={`modal fidelity-modal ${wide ? "wide" : ""} ${drawer ? "activity-drawer" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className="modal-header">
          <div>
            {drawer && <span className="eyebrow">SHARED DEFINITION</span>}
            <h2>{title}</h2>
            {subtitle && <p className="modal-subtitle">{subtitle}</p>}
          </div>
          <button
            type="button"
            className="icon-button"
            aria-label="关闭"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}
export function ConfirmDelete({
  title,
  name,
  children,
  onClose,
  onConfirm,
  blocked = false,
}: {
  title: string;
  name: string;
  children: ReactNode;
  onClose: () => void;
  onConfirm: () => void;
  blocked?: boolean;
}) {
  return (
    <Modal
      title={title}
      subtitle="删除前请确认影响范围；提交草稿后才会更新已保存版本"
      onClose={onClose}
    >
      <div className="form-body">
        <div className="delete-confirmation">
          <AlertTriangle size={22} />
          <div>
            <strong>
              {blocked ? `暂时无法删除“${name}”` : `确认删除“${name}”？`}
            </strong>
            <div>{children}</div>
          </div>
        </div>
      </div>
      <footer className="modal-footer">
        <button onClick={onClose}>取消</button>
        <button
          className="danger-button"
          disabled={blocked}
          onClick={onConfirm}
        >
          <Trash2 size={14} />
          确认删除
        </button>
      </footer>
    </Modal>
  );
}
export function StatePicker({
  label,
  s,
  value,
  onChange,
  exclude = [],
}: {
  label: string;
  s: Scenario;
  value: string[];
  onChange: (v: string[]) => void;
  exclude?: string[];
}) {
  const select = (ids: string[]) =>
    onChange(
      [...new Set([...value, ...ids])].filter((x) => !exclude.includes(x)),
    );
  return (
    <fieldset className="state-picker">
      <legend>
        {label} <span className="muted">{value.length} 项</span>
      </legend>
      <select
        aria-label={`${label}按活动包选择`}
        value=""
        onChange={(e) => {
          select(
            packageActivities(s, e.target.value).map(
              (id) => s.activities.find((a) => a.id === id)!.output_state_id,
            ),
          );
        }}
      >
        <option value="">按活动包批量选择实现状态…</option>
        {s.activity_packages.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <div className="state-options">
        {s.states
          .filter((x) => !exclude.includes(x.id))
          .map((x) => (
            <label key={x.id} title={x.id}>
              <input
                type="checkbox"
                checked={value.includes(x.id)}
                onChange={(e) =>
                  onChange(
                    e.target.checked
                      ? [...value, x.id]
                      : value.filter((v) => v !== x.id),
                  )
                }
              />
              <span>
                {x.name}
                <small>
                  {x.id.startsWith("draft:") ? "未提交" : x.id.slice(-14)}
                </small>
              </span>
            </label>
          ))}
        {!s.states.length && (
          <p className="muted">请先在活动页添加活动或已知状态。</p>
        )}
      </div>
    </fieldset>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty-panel">{children}</div>;
}
