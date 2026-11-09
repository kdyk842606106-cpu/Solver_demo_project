import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Plus,
  Link,
  Trash2,
  X,
  Pencil,
  PackagePlus,
  CheckCircle2,
  Link2,
} from "lucide-react";
import { draftId, packageActivities, stateName } from "../domain/model";
import type { Operation, Scenario, Package, Activity } from "../domain/model";
import { Modal, Empty, ConfirmDelete } from "../components/Fields";
import ActivityEditor from "../components/ActivityEditor";
export default function Packages({
  s,
  stage,
}: {
  s: Scenario;
  stage: (o: Operation[]) => void;
}) {
  const [deleting, setDeleting] = useState<Package | null>(null),
    [creatingIn, setCreatingIn] = useState<string | null>(null),
    [editingActivity, setEditingActivity] = useState<Activity | null>(null);
  const [collapsed, setCollapsed] = useState<string[]>([]),
    [parent, setParent] = useState<string | null | undefined>(undefined),
    [name, setName] = useState(""),
    [link, setLink] = useState<string | null>(null),
    [selected, setSelected] = useState<string[]>([]),
    [selectedPackage, setSelectedPackage] = useState<string | null>(null),
    [rename, setRename] = useState<Package | null>(null);
  const currentPackage =
    s.activity_packages.find((p) => p.id === selectedPackage) ??
    s.activity_packages.find((p) => p.level === 2);
  const owners = (ids: string[]) =>
    [
      ...new Set(
        s.activities
          .filter((a) => ids.includes(a.id))
          .flatMap((a) =>
            Object.keys(a.resource_reqs)
              .filter(
                (id) => s.resources.find((r) => r.id === id)?.kind === "crew",
              )
              .map((id) => s.resources.find((r) => r.id === id)?.name),
          ),
      ),
    ].join("、") || "—";
  function remove(p: Package) {
    setDeleting(p);
  }
  function row(p: Package) {
    const closed = collapsed.includes(p.id);
    const members = s.activity_package_memberships.filter(
      (m) => m.package_id === p.id,
    );
    return (
      <tbody key={p.id}>
        <tr
          className={`package-row level-${p.level} ${currentPackage?.id === p.id ? "selected" : ""}`}
          onClick={() => setSelectedPackage(p.id)}
        >
          <td>
            <button
              className="tree-toggle"
              aria-label={`${closed ? "展开" : "收起"}活动包${p.name}`}
              aria-expanded={!closed}
              onClick={() =>
                setCollapsed(
                  closed
                    ? collapsed.filter((x) => x !== p.id)
                    : [...collapsed, p.id],
                )
              }
            >
              {closed ? <ChevronRight size={15} /> : <ChevronDown size={15} />}
            </button>
            <button
              className="name-button"
              onClick={() => setSelectedPackage(p.id)}
            >
              {p.name}
            </button>
          </td>
          <td>
            <span className="type-tag">
              {p.level === 1 ? "一级活动包" : "二级活动包"}
            </span>
          </td>
          <td>{packageActivities(s, p.id).length} 个活动</td>
          <td>—</td>
          <td>{owners(packageActivities(s, p.id))}</td>
          <td>
            <div className="row-actions">
              {p.level === 1 ? (
                <button
                  className="icon-button"
                  aria-label={`在${p.name}下添加二级包`}
                  onClick={() => {
                    setParent(p.id);
                    setName("");
                  }}
                >
                  <Plus size={16} />
                </button>
              ) : (
                <>
                  <button
                    className="icon-button"
                    title="新建原子活动"
                    aria-label={`在${p.name}中新建原子活动`}
                    onClick={() => setCreatingIn(p.id)}
                  >
                    <Plus size={15} />
                  </button>
                  <button
                    className="icon-button"
                    aria-label={`引用到${p.name}`}
                    onClick={() => {
                      setLink(p.id);
                      setSelected([]);
                    }}
                  >
                    <Link size={16} />
                  </button>
                </>
              )}
              <button
                className="icon-button"
                title="重命名活动包"
                aria-label={`重命名${p.name}`}
                onClick={() => {
                  setRename(p);
                  setName(p.name);
                }}
              >
                <Pencil size={13} />
              </button>
              <button
                className="icon-button"
                aria-label={`删除包${p.name}`}
                onClick={() => remove(p)}
              >
                <Trash2 size={15} />
              </button>
            </div>
          </td>
        </tr>
        {!closed &&
          p.level === 2 &&
          members.map((m) => {
            const a = s.activities.find((x) => x.id === m.activity_id)!;
            return (
              <tr key={m.id}>
                <td className="activity-indent">
                  <button
                    className="activity-name-link"
                    aria-label={`编辑${a.name}`}
                    onClick={() => setEditingActivity(a)}
                  >
                    {a.name}
                  </button>
                </td>
                <td>
                  <span className="state-tag">原子活动</span>
                </td>
                <td>
                  {a.preconditions
                    .map((x) => stateName(s, x.state_id))
                    .join(" 且 ") || "无前置"}{" "}
                  → {stateName(s, a.output_state_id)}
                </td>
                <td>{a.duration} 分钟</td>
                <td>{owners([a.id])}</td>
                <td>
                  <button
                    className="icon-button"
                    aria-label={`移出${a.name}`}
                    onClick={() =>
                      stage([
                        {
                          operation: "remove_membership",
                          object_id: m.id,
                          payload: {},
                        },
                      ])
                    }
                  >
                    <X size={16} />
                  </button>
                </td>
              </tr>
            );
          })}
      </tbody>
    );
  }
  return (
    <>
      <div className="page-toolbar package-create-toolbar">
        <button
          className="primary-button"
          onClick={() => {
            setParent(null);
            setName("");
          }}
        >
          <Plus size={16} />
          增加一级活动包
        </button>
      </div>
      <div className="section-bar">
        活动包层级
        <span>
          一级包 → 二级包 → 原子活动；新建、引用、删除和移出统一在操作列完成
        </span>
      </div>
      <div className="package-selection-note">
        ⓘ 当前选中活动包：
        <strong>{currentPackage?.name ?? "未选择活动包"}</strong>
        <span>“移出”仅删除当前包引用，不删除活动定义。</span>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>活动包 / 原子活动</th>
              <th>类型</th>
              <th>状态关系 / 活动数量</th>
              <th>活动时长</th>
              <th>责任组</th>
              <th>操作</th>
            </tr>
          </thead>
          {s.activity_packages
            .filter((p) => p.level === 1)
            .flatMap((p) => [
              row(p),
              ...(!collapsed.includes(p.id)
                ? s.activity_packages
                    .filter((c) => c.parent_id === p.id)
                    .map(row)
                : []),
            ])}
        </table>
        {!s.activity_packages.length && (
          <Empty>暂无活动包。创建一级包，再添加二级包和活动引用。</Empty>
        )}
      </div>
      {deleting && (
        <ConfirmDelete
          title={deleting.level === 1 ? "删除一级活动包" : "删除二级活动包"}
          name={deleting.name}
          onClose={() => setDeleting(null)}
          onConfirm={() => {
            stage(
              [
                ...s.activity_packages.filter(
                  (p) => p.parent_id === deleting.id,
                ),
                deleting,
              ].map((p) => ({
                operation: "delete_package",
                object_id: p.id,
                payload: {},
              })),
            );
            setDeleting(null);
          }}
        >
          <p>
            将删除{" "}
            {
              s.activity_packages.filter((p) => p.parent_id === deleting.id)
                .length
            }{" "}
            个下级活动包，并移除相关引用。原子活动本体仍保留在活动全集。
          </p>
        </ConfirmDelete>
      )}
      {(creatingIn || editingActivity) && (
        <ActivityEditor
          s={s}
          initialPackage={creatingIn ?? undefined}
          activity={editingActivity ?? undefined}
          onClose={() => {
            setCreatingIn(null);
            setEditingActivity(null);
          }}
          onSave={(ops) => {
            stage(ops);
            setCreatingIn(null);
            setEditingActivity(null);
          }}
        />
      )}
      {(parent !== undefined || rename) && (
        <Modal
          title={
            rename
              ? "重命名活动包"
              : parent
                ? "增加二级活动包"
                : "增加一级活动包"
          }
          subtitle={
            rename
              ? "更新共享活动包名称"
              : parent
                ? `所属一级活动包：${s.activity_packages.find((p) => p.id === parent)?.name}`
                : "创建后可在操作列继续新建二级活动包"
          }
          onClose={() => {
            setParent(undefined);
            setRename(null);
          }}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              stage([
                rename
                  ? {
                      operation: "update_package",
                      object_id: rename.id,
                      payload: { name: name.trim() },
                    }
                  : {
                      operation: "create_package",
                      client_ref: draftId(),
                      payload: { name: name.trim(), parent_id: parent },
                    },
              ]);
              setParent(undefined);
              setRename(null);
            }}
          >
            <div className="form-body">
              <label>
                包名称
                <input
                  required
                  autoFocus
                  maxLength={128}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
            </div>
            <footer className="modal-footer">
              <button
                type="button"
                onClick={() => {
                  setParent(undefined);
                  setRename(null);
                }}
              >
                取消
              </button>
              <button type="submit" className="primary-button">
                加入草稿
              </button>
            </footer>
          </form>
        </Modal>
      )}
      {link && (
        <Modal
          title={`引用活动到“${s.activity_packages.find((p) => p.id === link)?.name}”`}
          subtitle="只创建包内引用，不复制活动定义"
          wide
          onClose={() => setLink(null)}
        >
          <div className="form-body reference-body">
            <div className="member-help">
              <Link2 size={14} />
              已在此包中的活动不会重复出现；同一活动仍可被其他包引用。
            </div>
            <div className="reference-list">
              {s.activities
                .filter(
                  (a) =>
                    !s.activity_package_memberships.some(
                      (m) => m.package_id === link && m.activity_id === a.id,
                    ),
                )
                .map((a) => (
                  <label
                    key={a.id}
                    className={selected.includes(a.id) ? "selected" : ""}
                  >
                    <input
                      type="checkbox"
                      checked={selected.includes(a.id)}
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? [...selected, a.id]
                            : selected.filter((x) => x !== a.id),
                        )
                      }
                    />
                    <span>
                      <strong>{a.name}</strong>

                      <small>
                        {a.preconditions
                          .map((p) => stateName(s, p.state_id))
                          .join(" 且 ") || "无前置依赖"}{" "}
                        → {stateName(s, a.output_state_id)}
                      </small>
                    </span>
                  </label>
                ))}
            </div>
            {s.activities.every((a) =>
              s.activity_package_memberships.some(
                (m) => m.package_id === link && m.activity_id === a.id,
              ),
            ) && (
              <Empty>
                <CheckCircle2 size={22} />
                活动全集中的所有活动均已加入当前包
              </Empty>
            )}
          </div>
          <footer className="modal-footer">
            <button onClick={() => setLink(null)}>取消</button>
            <span>已选择 {selected.length} 项</span>
            <button
              className="primary-button"
              disabled={!selected.length}
              onClick={() => {
                stage(
                  selected.map((activity_id) => ({
                    operation: "add_membership",
                    client_ref: draftId(),
                    payload: { package_id: link, activity_id },
                  })),
                );
                setLink(null);
              }}
            >
              添加 {selected.length} 个引用
            </button>
          </footer>
        </Modal>
      )}
    </>
  );
}
