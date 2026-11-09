import { useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  GitBranch,
  FileCog,
  Save,
  ChevronDown,
} from "lucide-react";
import type { Activity, Operation, Scenario } from "../domain/model";
import { draftId, stateName } from "../domain/model";
import { Modal } from "./Fields";
import RelationEditor, { type Relation } from "./RelationEditor";
import ResourceInputs from "./ResourceInputs";
import CrewRequirements from "./CrewRequirements";
const risks = [
  "高处作业",
  "动火作业",
  "有限空间作业",
  "临时用电",
  "吊装作业",
  "有毒有害作业",
];
export default function ActivityEditor({
  s,
  activity: a,
  onClose,
  onSave,
  initialPackage,
}: {
  s: Scenario;
  activity?: Activity;
  onClose: () => void;
  onSave: (o: Operation[]) => void;
  initialPackage?: string;
}) {
  const [step, setStep] = useState(1),
    [name, setName] = useState(a?.name ?? ""),
    [duration, setDuration] = useState(a?.duration ?? 20),
    [output, setOutput] = useState(a ? stateName(s, a.output_state_id) : ""),
    [active, setActive] = useState(a?.is_active ?? true);
  const [relations, setRelations] = useState<Relation[]>(() => [
    ...(a?.preconditions ?? []).map((p) => ({
      key: crypto.randomUUID(),
      kind: p.relation_role,
      state: p.state_id,
    })),
    ...(a?.delete_effect_state_ids ?? []).map((state) => ({
      key: crypto.randomUUID(),
      kind: "delete" as const,
      state,
    })),
  ]);
  const [reqs, setReqs] = useState(a?.resource_reqs ?? {}),
    [metadata, setMetadata] = useState<Record<string, unknown>>(
      a?.metadata ?? { activity_type: "机械集成" },
    ),
    [packages, setPackages] = useState(
      initialPackage
        ? [initialPackage]
        : s.activity_package_memberships
            .filter((m) => m.activity_id === a?.id)
            .map((m) => m.package_id),
    );
  const [error, setError] = useState("");
  const riskValue = Array.isArray(metadata.risk_jobs)
    ? metadata.risk_jobs.map(String)
    : String(metadata.risk_jobs ?? "")
        .split(/[,，、]/)
        .filter(Boolean);
  const [lifting, setLifting] = useState(() =>
    Object.keys(a?.resource_reqs ?? {}).some(
      (id) => s.resources.find((r) => r.id === id)?.kind === "crane",
    ),
  );
  function changeLifting(enabled: boolean) {
    setLifting(enabled);
    if (!enabled) {
      setReqs(
        Object.fromEntries(
          Object.entries(reqs).filter(
            ([id]) => s.resources.find((r) => r.id === id)?.kind !== "crane",
          ),
        ),
      );
      setMetadata({ ...metadata, precision_fragile: false });
    }
  }
  function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    if (!name.trim()) {
      setError("请输入活动名称");
      return;
    }
    if (!a && step === 1) {
      setStep(2);
      return;
    }
    if (
      relations.some((r) => !r.state) ||
      new Set(relations.map((r) => r.state)).size !== relations.length
    ) {
      setError("请选择每条关系的状态；同一状态不可重复配置冲突关系。");
      return;
    }
    if (
      lifting &&
      !Object.entries(reqs).some(
        ([id, n]) =>
          n > 0 && s.resources.find((r) => r.id === id)?.kind === "crane",
      )
    ) {
      setError(
        "请选择行吊资源并填写需求数量；尚无行吊时请先在资源管理中配置。",
      );
      return;
    }
    const id = a?.id ?? draftId();
    const payload = {
      name: name.trim(),
      duration,
      output_state_name: output.trim() || `${name.trim()}完成`,
      // New activities inherit the system's execution bound. Preserve explicit
      // limits on existing activities when editing unrelated business fields.
      max_instances: a?.max_instances ?? null,
      is_active: active,
      metadata,
      preconditions: relations
        .filter((r) => r.kind !== "delete")
        .map((r) => ({ state_id: r.state, relation_role: r.kind })),
      delete_effect_state_ids: relations
        .filter((r) => r.kind === "delete")
        .map((r) => r.state),
      resource_reqs: reqs,
    };
    const ops: Operation[] = [
      a
        ? { operation: "update_activity", object_id: id, payload }
        : { operation: "create_activity", client_ref: id, payload },
    ];
    if (!a)
      for (const p of packages)
        ops.push({
          operation: "add_membership",
          client_ref: draftId(),
          payload: { activity_id: id, package_id: p },
        });
    onSave(ops);
  }
  const path = (id: string) => {
    const p = s.activity_packages.find((p) => p.id === id)!;
    return [s.activity_packages.find((x) => x.id === p.parent_id)?.name, p.name]
      .filter(Boolean)
      .join(" / ");
  };
  const packageFields = (
    <fieldset className="package-choice-section">
      <legend>
        所属活动包 <small>可选 · 可引用多个包</small>
      </legend>
      <div className="package-checkboxes wizard-packages">
        {s.activity_packages
          .filter((p) => p.level === 2)
          .map((p) => (
            <label
              key={p.id}
              className={packages.includes(p.id) ? "checked" : ""}
            >
              <input
                type="checkbox"
                checked={packages.includes(p.id)}
                onChange={(e) =>
                  setPackages(
                    e.target.checked
                      ? [...packages, p.id]
                      : packages.filter((id) => id !== p.id),
                  )
                }
              />
              <span>
                <strong>{p.name}</strong>
                <small>{path(p.id)}</small>
              </span>
              {packages.includes(p.id) && <Check size={14} />}
            </label>
          ))}
      </div>
      {!s.activity_packages.some((p) => p.level === 2) && (
        <p className="form-help">暂无二级活动包，可在活动包页创建后再引用。</p>
      )}
    </fieldset>
  );
  const resourceFields = (
    <div className="form-grid resource-field-grid">
      <CrewRequirements s={s} value={reqs} onChange={setReqs} />
      <label>
        是否吊装
        <select
          aria-label="是否吊装"
          value={lifting ? "yes" : "no"}
          onChange={(e) => changeLifting(e.target.value === "yes")}
        >
          <option value="no">否</option>
          <option value="yes">是</option>
        </select>
      </label>
      {lifting && (
        <label className="precision-checkbox conditional-field">
          <input
            type="checkbox"
            checked={Boolean(metadata.precision_fragile)}
            onChange={(e) =>
              setMetadata({ ...metadata, precision_fragile: e.target.checked })
            }
          />
          <span>是否精密易损</span>
        </label>
      )}
      {lifting && (
        <div className="span-2 conditional-field">
          <ResourceInputs
            s={s}
            kind="crane"
            label="行吊"
            value={reqs}
            onChange={setReqs}
          />
        </div>
      )}
      <div className="span-2 tool-resource-field">
        <ResourceInputs
          s={s}
          kind="tool"
          label="工装工具"
          value={reqs}
          onChange={setReqs}
        />
      </div>
      <div className="span-2">
        <ResourceInputs
          s={s}
          kind="workspace"
          label="作业空间"
          value={reqs}
          onChange={setReqs}
        />
      </div>
      {s.resources.some((r) => r.kind === "material") && (
        <div className="span-2">
          <ResourceInputs s={s} kind="material" label="周转物料" value={reqs} onChange={setReqs} />
        </div>
      )}
      {s.resources.some((r) => !r.kind || r.kind === "unclassified") && (
        <div className="span-2">
          <ResourceInputs
            s={s}
            kind="unclassified"
            label="未分类资源"
            value={reqs}
            onChange={setReqs}
          />
        </div>
      )}
    </div>
  );
  const relationFields = (
    <RelationEditor
      s={s}
      value={relations}
      onChange={setRelations}
      name={name}
      output={output}
      onOutput={setOutput}
      own={a ? [a.output_state_id, ...a.additional_output_state_ids] : []}
      detailed={!a}
    />
  );
  return (
    <Modal
      title={a ? "编辑活动定义" : initialPackage ? "新建原子活动" : "新建活动"}
      subtitle={
        a
          ? undefined
          : initialPackage
            ? `创建后引用到“${path(initialPackage)}”，并自动建立目标状态`
            : "创建活动本体时自动建立目标状态"
      }
      drawer={!!a}
      wide={!a}
      onClose={onClose}
    >
      {a ? (
        <div className="drawer-impact">
          <AlertTriangle size={15} />
          <span>
            共享定义修改会影响{" "}
            {
              s.activity_package_memberships.filter(
                (m) => m.activity_id === a.id,
              ).length
            }{" "}
            个包引用；保存后先进入草稿。
          </span>
        </div>
      ) : (
        <div className="wizard-steps two-steps">
          {["定义与目标", "关系与归属"].map((label, i) => (
            <div
              key={label}
              className={`${step === i + 1 ? "active" : ""} ${step > i + 1 ? "done" : ""}`}
            >
              <span>{step > i + 1 ? <Check size={12} /> : i + 1}</span>
              <strong>{label}</strong>
            </div>
          ))}
        </div>
      )}
      <form onSubmit={save} className="fidelity-activity-form">
        <div className={`form-body ${a ? "drawer-body" : "wizard-body"}`}>
          {(a || step === 1) && (
            <section className="form-section">
              <h3>
                {a && <span>01</span>}
                {a ? "基本信息" : "活动本体"}
              </h3>
              <div className="form-grid">
                <label className="span-2">
                  活动名称
                  <input
                    autoFocus
                    required
                    maxLength={128}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="例如：液压系统自检"
                  />
                </label>
                {a && (
                  <label>
                    活动时长（分钟）
                    <input
                      type="number"
                      required
                      min={1}
                      step={1}
                      value={duration}
                      onChange={(e) => setDuration(Number(e.target.value))}
                    />
                  </label>
                )}
                {a && (
                  <fieldset className="activity-type-field span-2">
                    <legend>活动类型标签</legend>
                    <div className="activity-type-options">
                      {["机械集成", "功能调测"].map((type) => (
                        <button
                          type="button"
                          key={type}
                          aria-pressed={
                            (metadata.activity_type ?? "机械集成") === type
                          }
                          className={
                            (metadata.activity_type ?? "机械集成") === type
                              ? "selected"
                              : ""
                          }
                          onClick={() =>
                            setMetadata({ ...metadata, activity_type: type })
                          }
                        >
                          {(metadata.activity_type ?? "机械集成") === type && (
                            <Check size={13} />
                          )}{" "}
                          {type}
                        </button>
                      ))}
                    </div>
                  </fieldset>
                )}
              </div>
            </section>
          )}
          {!a && step === 1 && (
            <section className="auto-target-panel">
              <GitBranch size={19} />
              <div>
                <span>目标状态 · 自动创建</span>
                <strong>
                  {name.trim()
                    ? `${name.trim()}完成`
                    : "填写活动名称后自动生成"}
                </strong>
                <code>状态 ID 由系统生成并绑定当前活动</code>
                <small>原子状态 · 实现效果</small>
              </div>
              <CheckCircle2 size={17} />
            </section>
          )}
          {a && (
            <>
              <section className="form-section">
                <h3>
                  <span>02</span>作业条件
                </h3>
                <div className="form-grid">
                  <details className="risk-dropdown">
                    <summary>
                      <span>涉及风险作业</span>
                      <span className="risk-selection">
                        {riskValue.join("、") || "请选择风险作业（可多选）"}
                        <ChevronDown size={14} />
                      </span>
                    </summary>
                    <div className="risk-menu">
                      {[...new Set([...risks, ...riskValue])].map((r) => (
                        <label key={r}>
                          <input
                            type="checkbox"
                            checked={riskValue.includes(r)}
                            onChange={(e) =>
                              setMetadata({
                                ...metadata,
                                risk_jobs: e.target.checked
                                  ? [...riskValue, r]
                                  : riskValue.filter((x) => x !== r),
                              })
                            }
                          />
                          {r}
                        </label>
                      ))}
                    </div>
                  </details>
                </div>
                {resourceFields}
                <p className="form-help">
                  {lifting ? "已配置吊装需求" : "未配置吊装需求"}
                  。人数、行吊、空间和工具使用资源容量；风险、类型和精密易损仅作为业务信息。
                </p>
              </section>
              <section className="form-section">
                <h3>
                  <span>03</span>活动描述
                </h3>
                <label>
                  <span className="sr-only">说明</span>
                  <textarea
                    value={String(metadata.description ?? "")}
                    onChange={(e) =>
                      setMetadata({ ...metadata, description: e.target.value })
                    }
                    placeholder="说明作业内容、完成标准和注意事项"
                  />
                </label>
              </section>
              <section className="form-section">
                <h3>
                  <span>04</span>依赖关系
                </h3>
                {relationFields}
              </section>
              <section className="form-section">
                <h3>
                  <span>05</span>执行配置
                </h3>
                <div className="form-grid">
                  <label className="precision-checkbox">
                    <input
                      type="checkbox"
                      checked={active}
                      onChange={(e) => setActive(e.target.checked)}
                    />
                    启用活动
                  </label>
                </div>
              </section>
            </>
          )}
          {!a && step === 2 && (
            <>
              {relationFields}
              <section className="form-section">
                <div className="form-grid">
                  <label>
                    参考时长（分钟）
                    <input
                      aria-label="活动时长（分钟）"
                      required
                      type="number"
                      min={1}
                      step={1}
                      value={duration}
                      onChange={(e) => setDuration(Number(e.target.value))}
                    />
                  </label>
                </div>
                {resourceFields}
              </section>
              {packageFields}
              <div className="creation-summary">
                <FileCog size={18} />
                <div>
                  <strong>将创建：{name} ＋ 1 个目标状态</strong>
                  <span>
                    {relations.length + 1} 条关系 · {duration} 分钟 ·{" "}
                    {packages.length} 个包引用
                  </span>
                </div>
              </div>
            </>
          )}
          {error && (
            <div className="error-box" role="alert">
              {error}
            </div>
          )}
        </div>
        <footer className="modal-footer">
          <button
            type="button"
            onClick={() => (!a && step === 2 ? setStep(1) : onClose())}
          >
            {!a && step === 2 ? (
              <>
                <ArrowLeft size={14} />
                上一步
              </>
            ) : (
              "取消"
            )}
          </button>
          {!a && <span>步骤 {step} / 2</span>}
          <button type="submit" className="primary-button">
            {!a && step === 1 ? (
              <>
                下一步
                <ArrowRight size={14} />
              </>
            ) : (
              <>
                <Save size={14} />
                {a ? "保存到草稿" : "创建并保存草稿"}
              </>
            )}
          </button>
        </footer>
      </form>
    </Modal>
  );
}
