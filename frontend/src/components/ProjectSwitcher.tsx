import { useEffect, useRef, useState } from "react";
import { ChevronDown, Check, Plus } from "lucide-react";
import type { Summary } from "../domain/model";
export default function ProjectSwitcher({
  projects,
  currentId,
  revision,
  busy,
  onSelect,
  onCreate,
}: {
  projects: Summary[];
  currentId?: string;
  revision?: number;
  busy: boolean;
  onSelect: (id: string) => void;
  onCreate: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
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
  }, []);
  return (
    <div className="reference-project" ref={ref}>
      <button
        className="reference-project-trigger"
        aria-label="切换项目"
        data-project-id={currentId ?? ""}
        aria-expanded={open}
        disabled={busy}
        onClick={() => setOpen(!open)}
      >
        <span>
          {projects.find((p) => p.id === currentId)?.name ?? "选择项目"}
        </span>
        <small>V{revision ?? "—"}</small>
        <ChevronDown size={13} />
      </button>
      {open && (
        <div
          className="reference-project-menu"
          role="menu"
          aria-label="项目列表"
        >
          <header>
            <span>切换项目</span>
            <small>{projects.length} 个可用项目</small>
          </header>
          <div className="project-options">
            {projects.map((p) => (
              <button
                key={p.id}
                role="menuitem"
                aria-label={p.name}
                data-project-option={p.id}
                className={p.id === currentId ? "selected" : ""}
                onClick={() => {
                  setOpen(false);
                  onSelect(p.id);
                }}
              >
                <span>
                  <strong>{p.name}</strong>
                  <small>
                    {p.id === currentId ? "当前项目" : "切换到该项目"}
                  </small>
                </span>
                <small>V{p.revision}</small>
                {p.id === currentId && <Check size={14} />}
              </button>
            ))}
          </div>
          <button
            className="project-create"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onCreate();
            }}
          >
            <Plus size={14} />
            新建项目
          </button>
        </div>
      )}
    </div>
  );
}
