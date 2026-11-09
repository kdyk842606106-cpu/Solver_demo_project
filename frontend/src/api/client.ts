import type {
  Operation,
  Run,
  Scenario,
  ScenarioRecord,
  Summary,
} from "../domain/model";
import { normalizeScenario } from "../domain/model";
const messages: Record<string, string> = {
  SCENARIO_REVISION_CONFLICT: "项目版本已更新，请核对草稿后重新加载。",
  RESOURCE_CAPACITY_EXCEEDED: "活动资源需求超出可用容量。",
  UNKNOWN_RESOURCE: "活动引用的资源不存在，请重新选择。",
  UNKNOWN_STATE: "引用的状态不存在，请重新选择。",
  BODY_IN_USE: "该活动或状态仍被其他活动引用，不能删除。",
  RESOURCE_IN_USE: "资源仍被活动引用，不能删除、停用或降低容量。",
  DRAFT_VALIDATION_FAILED: "草稿未通过校验，请检查状态关系和资源需求。",
  SCENARIO_INVALID: "当前状态与目标状态未通过求解预检。",
  REQUEST_ID_CONFLICT: "此次提交标识已被其他请求使用，请重新提交。",
};
function describeError(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(describeError).join('\n');
  if (!detail || typeof detail !== "object") return "请求未完成，请稍后重试。";
  const d = detail as Record<string, unknown>;
  if (d.error_message && typeof d.error_message === "object")
    return describeError(d.error_message);
  const message =
    messages[String(d.error_code ?? d.code)] ??
    String(d.error_message ?? d.message ?? d.msg ?? "数据校验失败");
  const issues = Array.isArray(d.issues)
    ? d.issues.map(describeError).join("\n")
    : "";
  const refs = (
    d.details as { references?: { name: string }[] } | undefined
  )?.references
    ?.map((r) => r.name)
    .join("、");
  const details = d.details as {
    confirmation_groups?: { reason: string; states?: { name: string }[] }[];
    blocked_activities?: { name: string; missing_preconditions?: { name: string }[] }[];
  } | undefined;
  const groups = details?.confirmation_groups ?? [];
  const missing = [...new Set(groups.filter((g) => g.reason === "missing_initial_fact")
    .flatMap((g) => (g.states ?? []).map((state) => state.name)))];
  const cycles = groups.filter((g) => g.reason === "dependency_cycle").length;
  const blocked = details?.blocked_activities?.[0];
  const explanation = [
    missing.length ? `需确认的起始事实（${missing.length} 项）：${missing.slice(0, 8).join("、")}${missing.length > 8 ? "……" : ""}` : "",
    cycles ? `另有 ${cycles} 组循环依赖缺少已知起点，请核对实际成立的状态。` : "",
    !groups.length && blocked ? `活动“${blocked.name}”缺少前置：${(blocked.missing_preconditions ?? []).map((state) => state.name).join("、")}` : "",
    groups.length ? "可用“恢复项目初始状态”加载项目预设，再按实际情况确认；不要将所有活动完成状态当作当前状态。" : "",
  ].filter(Boolean).join("\n");
  return [message, issues, refs ? `引用活动：${refs}` : "", explanation]
    .filter(Boolean)
    .join("\n");
}
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(describeError(detail));
  }
}
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const body = response.status === 204 ? null : await response.json();
  if (!response.ok) throw new ApiError(response.status, body.detail ?? body);
  return body as T;
}
const post = <T>(path: string, payload: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(payload) });
export const api = {
  projects: () => request<Summary[]>("/planner-scenarios"),
  project: (id: string) =>
    request<ScenarioRecord>(
      `/planner-scenarios/${encodeURIComponent(id)}`,
    ).then((r) => ({ ...r, scenario: normalizeScenario(r.scenario) })),
  createProject: (name: string) =>
    post<ScenarioRecord>("/planner-scenarios", {
      name,
      execution_mode: "parallel",
    }),
  commit: (id: string, revision: number, operations: Operation[]) =>
    post<{ scenario: Scenario; revision: number; warnings?: {code: string; message?: string}[] }>(
      `/planner-scenarios/${encodeURIComponent(id)}/draft-commit`,
      { expected_revision: revision, operations },
    ).then((r) => ({ ...r, scenario: normalizeScenario(r.scenario) })),
  runs: (id: string, signal?: AbortSignal) =>
    request<Run[]>(`/planner-runs?scenario_id=${encodeURIComponent(id)}`, { signal }),
  run: (id: string, signal?: AbortSignal) => request<Run>(`/planner-runs/${encodeURIComponent(id)}`, { signal }),
  progress: (id: string, version: number, signal: AbortSignal) =>
    request<import("../domain/model").RunProgress>(
      `/planner-runs/${encodeURIComponent(id)}/progress?known_plan_version=${version}`, { signal }),
  solve: (payload: unknown) => post<Run>("/planner-runs/async", payload),
  checkInitialStates: (id: string, payload: unknown, signal?: AbortSignal) =>
    request<import('../components/InitialStateCheck').InitialDiagnosis>(
      `/planner-scenarios/${encodeURIComponent(id)}/initial-state-check`,
      { method: 'POST', body: JSON.stringify(payload), signal }),
  capabilities: () =>
    request<{ planner_available: boolean; async_runs_supported: boolean;
      joint_cp_sat?: { run_activity_time_windows_supported?: boolean } }>(
      "/planner-runs/capabilities",
    ),
};
