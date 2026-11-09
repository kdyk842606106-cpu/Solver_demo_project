import { useEffect, useMemo, useState } from "react";
import {
  SlidersHorizontal,
  Settings,
  Database,
  Boxes,
  Users,
  Workflow,
  Save,
  Plus,
  RefreshCw,
  CheckCircle2,
  Info,
} from "lucide-react";
import { api, ApiError } from "./api/client";
import { applyOperations } from "./domain/model";
import type { Operation, Scenario, Summary } from "./domain/model";
import Activities from "./pages/Activities";
import Packages from "./pages/Packages";
import Resources from "./pages/Resources";
import Solver from "./pages/Solver";
import ProjectSwitcher from "./components/ProjectSwitcher";
import { Empty, Modal } from "./components/Fields";
type View = "activities" | "packages" | "resources" | "solver";
const views = [
  { id: "activities", name: "活动全集", icon: Database },
  { id: "packages", name: "活动包", icon: Boxes },
  { id: "resources", name: "资源管理", icon: Users },
  { id: "solver", name: "联合求解", icon: Workflow },
] as const;
export default function App() {
  const [projects, setProjects] = useState<Summary[]>([]),
    [base, setBase] = useState<Scenario | null>(null),
    [operations, setOperations] = useState<Operation[]>([]),
    [view, setView] = useState<View>("activities"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [conflict, setConflict] = useState(false),
    [newProject, setNewProject] = useState(false),
    [name, setName] = useState(""),
    [switchTo, setSwitchTo] = useState<string | null>(null);
  const [reviewDrafts, setReviewDrafts] = useState(false);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 3500);
    return () => clearTimeout(timer);
  }, [notice]);
  const scenario = useMemo(
    () => (base ? applyOperations(base, operations) : null),
    [base, operations],
  );
  async function load(id: string) {
    const record = await api.project(id);
    setBase({ ...record.scenario, revision: record.revision });
    setOperations([]);
    setError("");
    setConflict(false);
    localStorage.setItem("planner-project", id);
  }
  useEffect(() => {
    let alive = true;
    async function initialize() {
      try {
        const list = await api.projects();
        if (!alive) return;
        setProjects(list);
        const saved = localStorage.getItem("planner-project"),
          id = list.find((p) => p.id === saved)?.id ?? list[0]?.id;
        if (id) {
          const record = await api.project(id);
          if (alive) setBase({ ...record.scenario, revision: record.revision });
        }
      } catch (e) {
        if (alive) setError(String(e));
      }
    }
    void initialize();
    return () => {
      alive = false;
    };
  }, []);
  useEffect(() => {
    if (!operations.length) return;
    const leave = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", leave);
    return () => window.removeEventListener("beforeunload", leave);
  }, [operations.length]);
  function stage(ops: Operation[]) {
    setOperations((previous) => [...previous, ...ops]);
    setError("");
    setNotice(`已加入 ${ops.length} 项草稿变更，提交后生效`);
  }
  async function commit() {
    if (!base) return false;
    setBusy(true);
    setError("");
    try {
      const result = await api.commit(base.id, base.revision, operations);
      setBase({ ...result.scenario, revision: result.revision });
      setOperations([]);
      setConflict(false);
      setProjects(await api.projects());
      setNotice(`已提交，当前版本 V${result.revision}${result.warnings?.length ? "；项目默认起始状态暂不能到达目标，请在求解页核对当前状态，或将选择设为项目初始状态。" : ""}`);
      return true;
    } catch (e) {
      setError(String(e));
      setConflict(e instanceof ApiError && e.status === 409);
      return false;
    } finally {
      setBusy(false);
    }
  }
  async function guardedLoad(id: string) {
    setBusy(true);
    try {
      await load(id);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="workbench reference-workbench" data-view={view}>
      <header className="app-header">
        <button
          className={`resource-settings ${view === "resources" ? "active" : ""}`}
          aria-label="资源管理"
          title="资源配置"
          onClick={() => setView("resources")}
        >
          <Settings size={16} />
        </button>
        <div className="brand">
          <SlidersHorizontal size={19} />
          <strong>Solver Workbench</strong>
          <span>集成计划配置系统</span>
        </div>
        <nav>
          {views
            .filter((v) => v.id !== "resources")
            .map((v) => (
              <button
                key={v.id}
                aria-label={v.name}
                className={view === v.id ? "active" : ""}
                onClick={() => setView(v.id)}
              >
                <v.icon size={16} />
                {v.id === "solver" ? "求解" : v.name}
                <small aria-hidden="true">
                  {v.id === "activities"
                    ? scenario?.activities.length
                    : v.id === "packages"
                      ? scenario?.activity_packages.length
                      : null}
                </small>
              </button>
            ))}
        </nav>
        <ProjectSwitcher
          projects={projects}
          currentId={base?.id}
          revision={base?.revision}
          busy={busy}
          onCreate={() => setNewProject(true)}
          onSelect={(id) =>
            operations.length ? setSwitchTo(id) : void guardedLoad(id)
          }
        />

        <button
          className="icon-button reload-workspace"
          title="重新加载已保存版本"
          aria-label="重新加载"
          disabled={!base || busy}
          onClick={() => {
            if (
              base &&
              (!operations.length ||
                window.confirm("重新加载将放弃当前草稿，继续？"))
            )
              void guardedLoad(base.id);
          }}
        >
          <RefreshCw size={14} />
        </button>
      </header>
      <div className="workspace-heading">
        <div className="breadcrumb">
          {view === "solver" ? "计划求解" : "主数据配置"} <span>›</span>{" "}
          {view === "solver"
            ? "求解配置"
            : views.find((v) => v.id === view)?.name}
        </div>
      </div>
      {error && (
        <div role="alert" className="error-box global-error">
          <strong>
            {conflict
              ? "数据已被其他会话修改。草稿已保留，请核对后重新加载。"
              : "操作未完成"}
          </strong>
          <pre>{error}</pre>
        </div>
      )}
      <main aria-busy={busy}>
        {scenario ? (
          <div key={scenario.id} className={busy ? "busy-surface" : ""}>
            {view === "activities" && <Activities s={scenario} stage={stage} />}{" "}
            {view === "packages" && <Packages s={scenario} stage={stage} />}{" "}
            {view === "resources" && <Resources s={scenario} stage={stage} />}{" "}
            {view === "solver" && (
              <Solver
                key={scenario.id}
                s={scenario}
                dirty={operations.length > 0}
                stage={stage}
                initialPresetPending={operations.some(o => o.operation === "update_scenario" && "initial_state_ids" in o.payload)}
                onSaveInitialPreset={ids => {
                  stage([{operation: "update_scenario", payload: {initial_state_ids: ids}}]);
                  setReviewDrafts(true);
                }}
                onReviewDrafts={() => setReviewDrafts(true)}
              />
            )}
          </div>
        ) : (
          <Empty>
            <Database size={36} />
            <h2>建立你的第一个计划项目</h2>
            <p>活动、状态、资源和求解记录均保存在数据库中。</p>
            <button
              className="primary-button"
              onClick={() => setNewProject(true)}
            >
              新建项目
            </button>
          </Empty>
        )}
      </main>
      <footer className="status-bar">
        <span>
          <i />
          配置工作区{busy ? "处理中" : "就绪"}
        </span>
        <span>{scenario?.activities.length ?? 0} 个活动本体</span>
        <span>{scenario?.states.length ?? 0} 个原子状态</span>
        <span>
          {scenario?.activity_package_memberships.length ?? 0} 个包引用
        </span>
        <span>联合 CP-SAT · 容量资源</span>
        <button
          aria-label="提交草稿"
          title="查看并提交项目草稿"
          className="status-drafts commit-workspace"
          disabled={!operations.length || busy || conflict}
          onClick={() => setReviewDrafts(true)}
        >
          <Save size={12} />
          草稿 {operations.length}
        </button>
        <span className="status-right">
          {operations.length ? "有未提交草稿" : "已保存版本"} · 服务端持久化
        </span>
      </footer>
      {notice && (
        <div className="fidelity-toast" role="status">
          <CheckCircle2 size={16} />
          {notice}
        </div>
      )}
      {reviewDrafts && (
        <Modal
          title="统一提交草稿"
          subtitle="初始状态、活动、资源及活动包的全部草稿变更将一起保存到当前项目"
          onClose={() => !busy && setReviewDrafts(false)}
        >
          <div className="form-body">
            <div className="commit-count">
              <CheckCircle2 size={21} />
              <div>
                <strong>{operations.length} 项草稿变更已准备就绪</strong>
                <span>
                  {base?.name} · V{base?.revision} → V
                  {(base?.revision ?? 0) + 1}
                </span>
              </div>
            </div>
            <div className="commit-list">
              {operations.map((o, i) => {
                const labels: Record<string, string> = {
                  create_activity: "新建活动",
                  update_activity: "更新活动",
                  delete_activity: "删除活动",
                  create_resource: "新建资源",
                  update_resource: "更新资源",
                  delete_resource: "删除资源",
                  create_package: "新建活动包",
                  update_package: "更新活动包",
                  delete_package: "删除活动包",
                  add_membership: "添加包引用",
                  remove_membership: "移除包引用",
                  create_seed_state: "新增已知状态",
                  update_scenario: "initial_state_ids" in o.payload ? "更新项目初始状态" : "更新项目配置",
                };
                const objects = [
                  ...(scenario?.activities ?? []),
                  ...(scenario?.resources ?? []),
                  ...(scenario?.activity_packages ?? []),
                  ...(base?.activities ?? []),
                  ...(base?.resources ?? []),
                  ...(base?.activity_packages ?? []),
                ];
                const obj = objects.find(
                  (x) => x.id === (o.object_id ?? o.client_ref),
                );
                const target = String(
                  o.payload.name ??
                    obj?.name ??
                    (o.payload.activity_id
                      ? objects.find((x) => x.id === o.payload.activity_id)
                          ?.name
                      : "") ??
                    "",
                );
                return (
                  <div key={i}>
                    <span>
                      <strong>{target || `变更 ${i + 1}`}</strong>
                      <code>{labels[o.operation] ?? "配置变更"}</code>
                      {o.operation === "update_scenario" && Array.isArray(o.payload.initial_state_ids) && (
                        <small>初始状态：{o.payload.initial_state_ids.length
                          ? o.payload.initial_state_ids.map(id => scenario?.states.find(s => s.id === id)?.name ?? String(id)).join("、")
                          : "空（未选择任何状态）"}</small>
                      )}
                    </span>
                  </div>
                );
              })}
            </div>
            <div className="commit-note">
              <Info size={15} />
              提交时检查版本与引用。若发生冲突，草稿会保留供核对。
            </div>
          </div>
          <footer className="modal-footer">
            <button disabled={busy} onClick={() => setReviewDrafts(false)}>
              继续编辑
            </button>
            <button
              className="primary-button"
              disabled={!operations.length || busy || conflict}
              onClick={async () => {
                await commit();
                setReviewDrafts(false);
              }}
            >
              <CheckCircle2 size={14} />
              {busy ? "提交中…" : "确认正式提交"}
            </button>
          </footer>
        </Modal>
      )}
      {newProject && (
        <Modal title="新建项目" onClose={() => setNewProject(false)}>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try {
                const record = await api.createProject(name.trim());
                setProjects(await api.projects());
                setNewProject(false);
                setName("");
                if (operations.length) setSwitchTo(record.id);
                else await load(record.id);
              } catch (e) {
                setError(String(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            <div className="form-body">
              <label>
                项目名称
                <input
                  required
                  maxLength={128}
                  autoFocus
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
              <p className="muted">
                默认并行执行，60 秒求解预算。创建后添加活动和资源。
              </p>
            </div>
            <footer className="modal-footer">
              <button type="submit" className="primary-button" disabled={busy}>
                创建项目
              </button>
            </footer>
          </form>
        </Modal>
      )}
      {switchTo && (
        <Modal title="当前项目有未提交草稿" onClose={() => setSwitchTo(null)}>
          <div className="form-body">
            <p>请选择如何处理当前项目的 {operations.length} 项变更。</p>
          </div>
          <footer className="modal-footer">
            <button disabled={busy} onClick={() => setSwitchTo(null)}>
              取消切换
            </button>
            <button
              disabled={busy}
              onClick={() => {
                const id = switchTo;
                setSwitchTo(null);
                void guardedLoad(id);
              }}
            >
              放弃并切换
            </button>
            <button
              className="primary-button"
              disabled={busy || conflict}
              onClick={async () => {
                if (await commit()) {
                  const id = switchTo;
                  setSwitchTo(null);
                  await guardedLoad(id);
                }
              }}
            >
              提交并切换
            </button>
          </footer>
        </Modal>
      )}
    </div>
  );
}
