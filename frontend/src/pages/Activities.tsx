import { useEffect, useState } from "react";
import {
  Plus,
  Search,
  Trash2,
  RotateCcw,
  Columns3,
  ListFilter,
} from "lucide-react";
import type { Activity, Operation, Scenario } from "../domain/model";
import { draftId, stateName, packageActivities } from "../domain/model";
import { Modal, ConfirmDelete, Empty } from "../components/Fields";

import ActivityEditor from "../components/ActivityEditor";

export default function Activities({
  s,
  stage,
}: {
  s: Scenario;
  stage: (ops: Operation[]) => void;
}) {
  const [deleting, setDeleting] = useState<Activity | null>(null);
  const [query, setQuery] = useState(""),
    [editor, setEditor] = useState<Activity | "new" | null>(null),
    [seed, setSeed] = useState(false),
    [seedName, setSeedName] = useState("");
  const [packageFilter, setPackageFilter] = useState("all"),
    [selectedId, setSelectedId] = useState<string | null>(null);
  const columns = [
    {
      id: "required",
      label: "前置条件",
      width: 190,
      render: (a: Activity) =>
        a.preconditions
          .filter((p) => p.relation_role === "required")
          .map((p) => stateName(s, p.state_id))
          .join(" 且 ") || "—",
    },
    {
      id: "transition",
      label: "转移条件",
      width: 210,
      render: (a: Activity) =>
        a.preconditions
          .filter((p) => p.relation_role === "transition")
          .map(
            (p) =>
              `${stateName(s, p.state_id)} → ${stateName(s, a.output_state_id)}`,
          )
          .join(" 且 ") || "—",
    },
    {
      id: "output",
      label: "实现效果",
      width: 170,
      render: (a: Activity) => stateName(s, a.output_state_id),
    },
    {
      id: "delete",
      label: "破坏效果",
      width: 160,
      render: (a: Activity) =>
        a.delete_effect_state_ids.map((id) => stateName(s, id)).join("、") ||
        "—",
    },
    {
      id: "duration",
      label: "活动时长",
      width: 90,
      render: (a: Activity) => `${a.duration} 分钟`,
    },
    {
      id: "description",
      label: "活动描述",
      width: 250,
      render: (a: Activity) => String(a.metadata?.description ?? "—"),
    },
    {
      id: "crew",
      label: "作业人数",
      width: 90,
      render: (a: Activity) =>
        `${Object.entries(a.resource_reqs)
          .filter(
            ([id]) => s.resources.find((r) => r.id === id)?.kind === "crew",
          )
          .reduce((n, [, v]) => n + v, 0)} 人`,
    },
    {
      id: "risk",
      label: "涉及风险作业",
      width: 180,
      render: (a: Activity) =>
        Array.isArray(a.metadata?.risk_jobs)
          ? a.metadata.risk_jobs.join("、") || "—"
          : String(a.metadata?.risk_jobs || "—"),
    },
    {
      id: "lifting",
      label: "是否吊装",
      width: 90,
      render: (a: Activity) =>
        Object.keys(a.resource_reqs).some(
          (id) => s.resources.find((r) => r.id === id)?.kind === "crane",
        )
          ? "是"
          : "否",
    },
    {
      id: "workspace",
      label: "作业空间",
      width: 180,
      render: (a: Activity) =>
        Object.keys(a.resource_reqs)
          .filter(
            (id) => s.resources.find((r) => r.id === id)?.kind === "workspace",
          )
          .map((id) => s.resources.find((r) => r.id === id)?.name)
          .join("、") || "—",
    },
    {
      id: "resources",
      label: "资源需求",
      width: 220,
      render: (a: Activity) =>
        Object.entries(a.resource_reqs)
          .map(
            ([id, n]) =>
              `${s.resources.find((r) => r.id === id)?.name ?? id} × ${n}`,
          )
          .join("、") || "—",
    },
    {
      id: "packages",
      label: "所属活动包",
      width: 150,
      render: (a: Activity) =>
        s.activity_package_memberships
          .filter((m) => m.activity_id === a.id)
          .map(
            (m) => s.activity_packages.find((p) => p.id === m.package_id)?.name,
          )
          .join("、") || "未分配",
    },
  ];
  const [visible, setVisible] = useState<string[]>(() => {
    try {
      const v = JSON.parse(
        localStorage.getItem("planner-activity-columns") || "null",
      );
      return Array.isArray(v) ? v : columns.map((c) => c.id);
    } catch {
      return columns.map((c) => c.id);
    }
  });
  useEffect(
    () =>
      localStorage.setItem("planner-activity-columns", JSON.stringify(visible)),
    [visible],
  );
  const rows = s.activities.filter((a) => {
    const text = [
      a.name,
      a.display_code,
      ...a.preconditions.map((p) => stateName(s, p.state_id)),
      stateName(s, a.output_state_id),
      ...Object.values(a.metadata ?? {}),
    ]
      .join(" ")
      .toLowerCase();
    const matches =
      packageFilter === "all" ||
      (packageFilter === "unassigned"
        ? !s.activity_package_memberships.some((m) => m.activity_id === a.id)
        : packageActivities(s, packageFilter).includes(a.id));
    return matches && text.includes(query.toLowerCase());
  });
  const selected = rows.find((a) => a.id === selectedId) ?? rows[0];
  const activeColumns = columns.filter((c) => visible.includes(c.id));
  function deleteSelected() {
    if (selected) setDeleting(selected);
  }
  return (
    <>
      <div className="reference-filter-band">
        <div className="search-box">
          <Search size={14} />
          <input
            aria-label="搜索活动"
            placeholder="搜索活动、关系、描述、风险或作业空间"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <label>
          活动包
          <select
            aria-label="按活动包筛选"
            value={packageFilter}
            onChange={(e) => setPackageFilter(e.target.value)}
          >
            <option value="all">全部活动包</option>
            {s.activity_packages.map((p) => (
              <option key={p.id} value={p.id}>
                {p.parent_id
                  ? `${s.activity_packages.find((x) => x.id === p.parent_id)?.name} / `
                  : ""}
                {p.name}
              </option>
            ))}
            <option value="unassigned">未分配活动</option>
          </select>
        </label>
        <button
          className="text-action"
          onClick={() => {
            setQuery("");
            setPackageFilter("all");
          }}
        >
          <RotateCcw size={13} />
          重置
        </button>
        <div className="filter-right">
          <button className="text-action" onClick={() => setSeed(true)}>
            添加已知状态
          </button>
          <button className="primary-button" onClick={() => setEditor("new")}>
            <Plus size={15} />
            新建活动
          </button>
        </div>
      </div>
      <div className="reference-table-toolbar">
        <span>
          <ListFilter size={14} />
          筛选结果 <strong>{rows.length}</strong> / {s.activities.length}
        </span>
        <button
          className="delete-selected"
          disabled={!selected}
          onClick={deleteSelected}
        >
          <Trash2 size={13} />
          删除活动
        </button>
        <div className="reference-table-tools">
          <small>单击行选择，单击名称进入编辑</small>
          <details className="column-settings">
            <summary>
              <Columns3 size={13} />
              列设置
            </summary>
            <div className="column-options">
              <header>
                显示列
                <button
                  className="text-action"
                  onClick={() => setVisible(columns.map((c) => c.id))}
                >
                  恢复默认
                </button>
              </header>
              <label>
                <input type="checkbox" checked disabled />
                活动名称（固定）
              </label>
              {columns.map((c) => (
                <label key={c.id}>
                  <input
                    type="checkbox"
                    checked={visible.includes(c.id)}
                    onChange={(e) =>
                      setVisible(
                        e.target.checked
                          ? [...visible, c.id]
                          : visible.filter((x) => x !== c.id),
                      )
                    }
                  />
                  {c.label}
                </label>
              ))}
            </div>
          </details>
        </div>
      </div>
      <div className="table-scroll reference-activity-scroll">
        <table
          className="reference-activity-table"
          style={{
            width: 190 + activeColumns.reduce((sum, c) => sum + c.width, 0),
          }}
        >
          <thead>
            <tr>
              <th style={{ width: 190 }}>活动名称</th>
              {activeColumns.map((c) => (
                <th key={c.id} style={{ width: c.width }}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr
                key={a.id}
                className={selected?.id === a.id ? "selected" : ""}
                onClick={() => setSelectedId(a.id)}
                aria-selected={selected?.id === a.id}
              >
                <td>
                  <button
                    className="activity-name-link"
                    aria-label={`编辑${a.name}`}
                    onClick={() => setEditor(a)}
                  >
                    {a.name}
                  </button>
                  {a.id.startsWith("draft:") && (
                    <span className="draft-marker">草</span>
                  )}
                  {!a.is_active && <span className="inactive-badge">停用</span>}
                </td>
                {activeColumns.map((c) => (
                  <td key={c.id} title={c.render(a)}>
                    {c.id === "packages" ? (
                      <div className="package-tags">
                        {s.activity_package_memberships
                          .filter((m) => m.activity_id === a.id)
                          .slice(0, 2)
                          .map((m) => (
                            <span key={m.id}>
                              {
                                s.activity_packages.find(
                                  (p) => p.id === m.package_id,
                                )?.name
                              }
                            </span>
                          ))}
                        {s.activity_package_memberships.filter(
                          (m) => m.activity_id === a.id,
                        ).length > 2 && (
                          <span>
                            ＋
                            {s.activity_package_memberships.filter(
                              (m) => m.activity_id === a.id,
                            ).length - 2}
                          </span>
                        )}
                        {!s.activity_package_memberships.some(
                          (m) => m.activity_id === a.id,
                        ) && <em>未分配</em>}
                      </div>
                    ) : (
                      c.render(a)
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && (
          <Empty>
            <Search size={24} />
            <strong>
              {s.activities.length ? "没有匹配的活动" : "暂无活动"}
            </strong>
            <p>
              {s.activities.length
                ? "调整搜索词或重置筛选条件。"
                : "新建活动后配置状态关系、资源需求和实现效果。"}
            </p>
          </Empty>
        )}
      </div>
      {editor && (
        <ActivityEditor
          key={editor === "new" ? "new" : editor.id}
          s={s}
          activity={editor === "new" ? undefined : editor}
          onClose={() => setEditor(null)}
          onSave={(ops) => {
            stage(ops);
            setEditor(null);
          }}
        />
      )}
      {deleting && (
        <ConfirmDelete
          title="删除原子活动"
          name={deleting.name}
          onClose={() => setDeleting(null)}
          onConfirm={() => {
            stage([
              {
                operation: "delete_activity",
                object_id: deleting.id,
                payload: {},
              },
            ]);
            setDeleting(null);
          }}
        >
          <p>
            将移除活动定义及其{" "}
            {
              s.activity_package_memberships.filter(
                (m) => m.activity_id === deleting.id,
              ).length
            }{" "}
            个活动包引用。若实现状态被其他对象引用，提交会被拒绝并列出引用明细。
          </p>
        </ConfirmDelete>
      )}
      {seed && (
        <Modal title="添加已知状态" onClose={() => setSeed(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              stage([
                {
                  operation: "create_seed_state",
                  client_ref: draftId(),
                  payload: { name: seedName.trim() },
                },
              ]);
              setSeed(false);
              setSeedName("");
            }}
          >
            <div className="form-body">
              <label>
                状态名称
                <input
                  autoFocus
                  required
                  value={seedName}
                  onChange={(e) => setSeedName(e.target.value)}
                />
              </label>
              <p className="muted">
                仅创建状态定义。是否当前成立，由求解时的当前状态选择决定。
              </p>
            </div>
            <footer className="modal-footer">
              <button type="submit" className="primary-button">
                加入草稿
              </button>
            </footer>
          </form>
        </Modal>
      )}
    </>
  );
}
