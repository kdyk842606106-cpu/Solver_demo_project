export type ResourceKind =
  "crew" | "crane" | "workspace" | "tool" | "material" | "unclassified";
export const resourceLabels: Record<ResourceKind, string> = {
  crew: "作业人数",
  crane: "行吊",
  workspace: "作业空间",
  tool: "工装工具",
  material: "周转物料",
  unclassified: "未分类",
};
export interface Resource {
  id: string;
  name: string;
  capacity: number;
  kind?: ResourceKind;
  is_active?: boolean;
}
export interface State {
  id: string;
  name: string;
  state_kind?: string;
  source_activity_id?: string;
}
export interface Activity {
  id: string;
  display_code?: string;
  name: string;
  duration: number;
  output_state_id: string;
  output_state_name?: string;
  preconditions: {
    state_id: string;
    relation_role: "required" | "transition";
  }[];
  delete_effect_state_ids: string[];
  additional_output_state_ids: string[];
  resource_reqs: Record<string, number>;
  max_instances: number | null;
  is_active: boolean;
  metadata?: Record<string, unknown>;
}
export interface Package {
  id: string;
  name: string;
  parent_id: string | null;
  level: number;
  is_active: boolean;
}
export interface Membership {
  id: string;
  package_id: string;
  activity_id: string;
}
export interface Scenario {
  activity_package_scope_ids?: string[];
  time_windows?: { id: string; activity_id: string; earliest_start: number; latest_finish: number }[];
  night_lift_rule?: { enabled: boolean; night_start: string; night_end: string } | null;
  exclusive_rules?: { crane: boolean; commissioning: boolean } | null;
  work_calendars?: WorkCalendar[];
  work_calendar_id?: string | null;
  working_intervals?: [number, number][];
  id: string;
  name: string;
  revision: number;
  execution_mode: "serial" | "parallel";
  start_time: number;
  max_steps: number;
  default_budget: Record<string, number>;
  activities: Activity[];
  states: State[];
  resources: Resource[];
  activity_packages: Package[];
  activity_package_memberships: Membership[];
  initial_state_ids: string[];
  goal_state_ids: string[];
  forbidden_state_ids: string[];
  [key: string]: unknown;
}
export interface WorkCalendar {
  id: string;
  name: string;
  weekdays: number[];
  periods: WorkPeriod[];
  exceptions: {date: string; periods: WorkPeriod[]}[];
}
export interface WorkPeriod {start: string; end: string}
export interface ScenarioRecord {
  id: string;
  name: string;
  revision: number;
  scenario: Scenario;
}
export interface Summary {
  id: string;
  name: string;
  revision: number;
}
export interface Operation {
  operation: string;
  client_ref?: string;
  object_id?: string;
  payload: Record<string, unknown>;
}
export interface Execution {
  activity_id: string;
  ordinal: number;
  start_time: number;
  end_time: number;
  [key: string]: unknown;
}
export interface Candidate {
  validator_status: string;
  executions: Execution[];
  metrics: { makespan: number; execution_count: number };
}
export interface EngineResult {
  status: string;
  paths: Candidate[];
  stats?: { tie_breaker?: string; makespan_proven_optimal?: boolean; execution_count_proven_optimal?: boolean };
  proven_optimal?: boolean;
  proven_infeasible?: boolean;
  lower_bound?: number;
  elapsed_seconds?: number;
  first_solution_seconds?: number;
  error?: string;
}
export interface RunProgress {
  run_id: string;
  scenario_id: string;
  job_status: string;
  status: string;
  started_at?: string;
  error_message?: string;
  progress_version: number;
  plan_version: number;
  candidate?: Candidate | null;
  metrics?: {
    phase: string; branches?: number; conflicts?: number; candidate_count: number;
    branches_per_second?: number | null; sampled_at?: string; last_improved_at?: string;
    worker_threads?: number; search_counter_scope?: string;
    best_makespan?: number; best_execution_count?: number; lower_bound?: number;
  } | null;
}
export interface ActivityTimeWindow {
  activity_id: string;
  earliest_start_at: string | null;
  latest_finish_at: string | null;
}
export interface Run {
  id: string;
  scenario_id: string;
  job_status?: string;
  status: string;
  created_at: string;
  started_at?: string;
  finished_at?: string;
  error_message?: string;
  request: {
      budget_allocation?: { mode: "auto"; policy: string; time_limit_seconds: number };
    execution_bound?: {
      mode: "auto";
      value: number;
      policy: string;
      heuristic: boolean;
    };
    effective_scenario_snapshot?: Scenario;
    activity_time_windows?: ActivityTimeWindow[];
    display_start_at?: string;
    display_timezone?: string;
    [key: string]: unknown;
  };
  result?: { results: Record<string, EngineResult> };
}
export const draftId = () => `draft:${crypto.randomUUID()}`;
// Presentation defaults only: never write these into historical snapshots.
export function normalizeScenario(source: Scenario): Scenario {
  const s = structuredClone(source);
  s.activities = (s.activities ?? []).map((a) => ({
    ...a,
    preconditions: a.preconditions ?? [],
    delete_effect_state_ids: a.delete_effect_state_ids ?? [],
    additional_output_state_ids: a.additional_output_state_ids ?? [],
    resource_reqs: a.resource_reqs ?? {},
    is_active: a.is_active ?? true,
    max_instances: a.max_instances ?? null,
    metadata: a.metadata ?? {},
  }));
  s.resources = (s.resources ?? []).map((r) => ({
    ...r,
    kind: r.kind && r.kind in resourceLabels ? r.kind : "unclassified",
  }));
  s.states ??= [];
  s.activity_packages ??= [];
  s.activity_package_memberships ??= [];
  s.initial_state_ids ??= [];
  s.goal_state_ids ??= [];
  s.forbidden_state_ids ??= [];
  return s;
}
export const stateName = (s: Scenario, id: string) =>
  s.states.find((x) => x.id === id)?.name ?? id;
export function packageActivities(s: Scenario, id: string): string[] {
  const ids = new Set([id]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const p of s.activity_packages)
      if (p.parent_id && ids.has(p.parent_id) && !ids.has(p.id)) {
        ids.add(p.id);
        changed = true;
      }
  }
  return [
    ...new Set(
      s.activity_package_memberships
        .filter((m) => ids.has(m.package_id))
        .map((m) => m.activity_id),
    ),
  ];
}

export function applyOperations(
  base: Scenario,
  operations: Operation[],
): Scenario {
  const s = structuredClone(base);
  for (const op of operations) {
    const p = structuredClone(op.payload),
      id = op.object_id,
      created = op.client_ref!;
    switch (op.operation) {
      case "create_activity": {
        const a = {
          name: String(p.name),
          duration: Number(p.duration),
          preconditions: [],
          delete_effect_state_ids: [],
          additional_output_state_ids: [],
          resource_reqs: {},
          max_instances: null,
          is_active: true,
          ...p,
          id: created,
          output_state_id: `${created}:output`,
        } as Activity;
        s.activities.push(a);
        s.states.push({
          id: a.output_state_id,
          name: a.output_state_name || `${a.name}完成`,
          source_activity_id: created,
          state_kind: "activity_output",
        });
        break;
      }
      case "update_activity": {
        const a = s.activities.find((x) => x.id === id);
        if (a) {
          Object.assign(a, p);
          const state = s.states.find((x) => x.id === a.output_state_id);
          if (state && p.output_state_name)
            state.name = String(p.output_state_name);
        }
        break;
      }
      case "delete_activity": {
        const a = s.activities.find((x) => x.id === id);
        s.activities = s.activities.filter((x) => x.id !== id);
        s.states = s.states.filter((x) => x.id !== a?.output_state_id);
        s.activity_package_memberships = s.activity_package_memberships.filter(
          (x) => x.activity_id !== id,
        );
        break;
      }
      case "create_package":
        s.activity_packages.push({
          ...p,
          id: created,
          level: p.parent_id ? 2 : 1,
          is_active: true,
        } as Package);
        break;
      case "update_package":
        Object.assign(
          s.activity_packages.find((x) => x.id === id)!,
          p,
        );
        break;
      case "delete_package":
        s.activity_packages = s.activity_packages.filter((x) => x.id !== id);
        s.activity_package_memberships = s.activity_package_memberships.filter(
          (x) => x.package_id !== id,
        );
        break;
      case "add_membership":
        s.activity_package_memberships.push({
          ...p,
          id: created,
        } as Membership);
        break;
      case "remove_membership":
        s.activity_package_memberships = s.activity_package_memberships.filter(
          (x) => x.id !== id,
        );
        break;
      case "create_resource":
        s.resources.push({ ...p, id: created, is_active: true } as Resource);
        break;
      case "update_resource":
        Object.assign(
          s.resources.find((x) => x.id === id)!,
          p,
        );
        break;
      case "delete_resource":
        s.resources = s.resources.filter((x) => x.id !== id);
        break;
      case "create_seed_state":
        s.states.push({
          id: created,
          name: String(p.name),
          state_kind: "seed",
        });
        break;
      case "update_scenario":
        Object.assign(s, p);
        break;
    }
  }
  return s;
}
