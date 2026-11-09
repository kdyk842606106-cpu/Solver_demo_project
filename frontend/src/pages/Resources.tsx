import { useState } from "react";
import { Plus, Pencil, Trash2, Database, CalendarDays } from "lucide-react";
import { draftId, resourceLabels } from "../domain/model";
import type {
  Operation,
  Resource,
  ResourceKind,
  Scenario,
} from "../domain/model";
import { Modal, ConfirmDelete } from "../components/Fields";
import CalendarPreview from "../components/CalendarPreview";
export default function Resources({
  s,
  stage,
}: {
  s: Scenario;
  stage: (o: Operation[]) => void;
}) {
  const [tab, setTab] = useState<"resources" | "calendars">("resources"),
    [deleting, setDeleting] = useState<Resource | null>(null);
  const [editing, setEditing] = useState<Resource | "new" | null>(null),
    [name, setName] = useState(""),
    [capacity, setCapacity] = useState(1),
    [editKind, setEditKind] = useState<ResourceKind>("crew"),
    [error, setError] = useState("");
  function open(r: Resource) {
    setEditing(r);
    setName(r.name);
    setCapacity(r.capacity);
    setEditKind(r.kind ?? "unclassified");
    setError("");
  }
  function remove(r: Resource) {
    setDeleting(r);
    setError("");
  }
  return (
    <>
      <div className="resource-reference-bar">
        <div
          className="resource-workspace-tabs"
          role="tablist"
          aria-label="资源管理配置"
        >
          <button
            role="tab"
            aria-selected={tab === "resources"}
            className={tab === "resources" ? "active" : ""}
            onClick={() => setTab("resources")}
          >
            <Database size={14} />
            资源配置
          </button>
          <button
            role="tab"
            aria-selected={tab === "calendars"}
            className={tab === "calendars" ? "active" : ""}
            onClick={() => setTab("calendars")}
          >
            <CalendarDays size={14} />
            工作日历
          </button>
        </div>
        <span>人员、行吊、空间、工具与周转物料按容量占用，结束后释放</span>
      </div>
      {tab === "calendars" ? (
        <CalendarPreview s={s} stage={stage} />
      ) : (
        <>
          {error && (
            <div role="alert" className="error-box">
              {error}
            </div>
          )}
          <div className="reference-resource-grid">
            {(
              [
                "crew",
                "crane",
                "workspace",
                "tool",
                "material",
                ...(s.resources.some(
                  (r) => (r.kind ?? "unclassified") === "unclassified",
                )
                  ? ["unclassified"]
                  : []),
              ] as ResourceKind[]
            ).map((panelKind) => {
              const items = s.resources.filter(
                (r) => (r.kind ?? "unclassified") === panelKind,
              );
              return (
                <section
                  className="reference-resource-panel"
                  key={panelKind}
                  aria-label={resourceLabels[panelKind]}
                >
                  <header>
                    <strong>{resourceLabels[panelKind]}</strong>
                    <small>{items.length}</small>
                    <button
                      className="icon-button"
                      aria-label={`新增${resourceLabels[panelKind]}`}
                      title={`新增${resourceLabels[panelKind]}`}
                      onClick={() => {
                        setEditing("new");
                        setName("");
                        setCapacity(1);
                        setEditKind(panelKind);
                        setError("");
                      }}
                    >
                      <Plus size={15} />
                    </button>
                  </header>
                  <div className="resource-panel-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>
                            {panelKind === "crew"
                              ? "责任组"
                              : panelKind === "crane"
                                ? "行吊资源池"
                                : resourceLabels[panelKind]}
                          </th>
                          <th>{panelKind === "crew" ? "人数" : "容量"}</th>
                          <th>操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {items.map((r) => (
                          <tr key={r.id}>
                            <td
                              title={`${s.activities.filter((a) => a.resource_reqs[r.id]).length} 个活动引用`}
                            >
                              {r.name}
                              {r.is_active === false && (
                                <span className="inactive-badge">停用</span>
                              )}
                              {r.id.startsWith("draft:") && (
                                <span className="draft-marker">草</span>
                              )}
                            </td>
                            <td className="resource-quantity">{r.capacity}</td>
                            <td>
                              <div className="row-actions">
                                <button
                                  className="icon-button"
                                  title="编辑"
                                  aria-label={`编辑资源${r.name}`}
                                  onClick={() => open(r)}
                                >
                                  <Pencil size={13} />
                                </button>
                                <button
                                  className="icon-button"
                                  title="删除"
                                  aria-label={`删除资源${r.name}`}
                                  onClick={() => remove(r)}
                                >
                                  <Trash2 size={13} />
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {!items.length && (
                      <div className="resource-empty">
                        暂无{resourceLabels[panelKind]}配置
                      </div>
                    )}
                  </div>
                </section>
              );
            })}
          </div>
        </>
      )}
      {deleting && (
        <ConfirmDelete
          title={`删除${resourceLabels[deleting.kind ?? "unclassified"]}`}
          name={deleting.name}
          blocked={s.activities.some((a) => a.resource_reqs[deleting.id])}
          onClose={() => setDeleting(null)}
          onConfirm={() => {
            stage([
              {
                operation: "delete_resource",
                object_id: deleting.id,
                payload: {},
              },
            ]);
            setDeleting(null);
          }}
        >
          {s.activities.some((a) => a.resource_reqs[deleting.id]) ? (
            <>
              <p>被以下活动引用，请先移除这些资源需求：</p>
              <ul>
                {s.activities
                  .filter((a) => a.resource_reqs[deleting.id])
                  .map((a) => (
                    <li key={a.id}>
                      {a.name} · 需求 {a.resource_reqs[deleting.id]}
                    </li>
                  ))}
              </ul>
            </>
          ) : (
            <p>此资源当前未被活动引用。删除进入项目草稿，不修改其他资源。</p>
          )}
        </ConfirmDelete>
      )}
      {editing && (
        <Modal
          title={`${editing === "new" ? "新增" : "编辑"}${resourceLabels[editKind]}`}
          subtitle="保存后进入当前项目草稿，统一提交后更新资源主数据"
          onClose={() => setEditing(null)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const refs =
                editing === "new"
                  ? []
                  : s.activities.filter(
                      (a) => (a.resource_reqs[editing.id] ?? 0) > capacity,
                    );
              if (refs.length) {
                setError(
                  `容量低于活动需求：${refs.map((a) => a.name).join("、")}`,
                );
                return;
              }
              stage([
                {
                  operation:
                    editing === "new" ? "create_resource" : "update_resource",
                  ...(editing === "new"
                    ? { client_ref: draftId() }
                    : { object_id: editing.id }),
                  payload: {
                    name: name.trim(),
                    capacity,
                    ...(editing === "new" ? { kind: editKind, is_active: true } : {}),
                  },
                },
              ]);
              setEditing(null);
            }}
          >
            <div className="form-body form-grid">
              <label>
                名称
                <input
                  required
                  maxLength={128}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
              <label>
                容量
                <input
                  required
                  type="number"
                  step={1}
                  min={1}
                  value={capacity}
                  onChange={(e) => setCapacity(Number(e.target.value))}
                />
              </label>
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
              <button type="submit" className="primary-button">
                保存到草稿
              </button>
            </footer>
          </form>
        </Modal>
      )}
    </>
  );
}
