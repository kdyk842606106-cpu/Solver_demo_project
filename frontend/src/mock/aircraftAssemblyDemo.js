const DAY_MINUTES = 480
const now = () => new Date().toISOString()
const toMin = (day) => (day - 1) * DAY_MINUTES

export const AIRCRAFT_DEMO_MACHINE_ID = 8801
export const AIRCRAFT_DEMO_CURRENT_STATE_ID = 880101
export const AIRCRAFT_DEMO_TARGET_STATE_ID = 880102

export const AIRCRAFT_DEMO_MACHINES = [
  {
    id: AIRCRAFT_DEMO_MACHINE_ID,
    machine_type_id: 88,
    code: 'AFA-DEMO-01',
    name: '飞机总装站位 Mock',
    location: '总装厂房 A 线',
    created_at: now(),
  },
]

export const AIRCRAFT_DEMO_STATES = {
  machine_id: AIRCRAFT_DEMO_MACHINE_ID,
  machine_code: 'AFA-DEMO-01',
  states: [
    {
      state_id: AIRCRAFT_DEMO_CURRENT_STATE_ID,
      state_type: 'current',
      label: '总装待排产',
      features: {
        fuselage_joined: 'false',
        wing_joined: 'false',
        engine_mounted: 'false',
        avionics_ready: 'false',
        power_check: 'false',
        delivery_ready: 'false',
      },
    },
    {
      state_id: AIRCRAFT_DEMO_TARGET_STATE_ID,
      state_type: 'target',
      label: '总装交付就绪',
      features: {
        fuselage_joined: 'true',
        wing_joined: 'true',
        engine_mounted: 'true',
        avionics_ready: 'true',
        power_check: 'true',
        delivery_ready: 'true',
      },
    },
  ],
}

export const AIRCRAFT_DEMO_RESOURCES = [
  { id: 1, code: 'BODY-TEAM-01', name: '机体总装班组', resource_type: 'ASSEMBLY_TEAM', capacity: 1, is_available: true },
  { id: 2, code: 'AVIONICS-01', name: '航电班组', resource_type: 'AVIONICS_TEAM', capacity: 1, is_available: true },
  { id: 3, code: 'HYD-01', name: '液压班组', resource_type: 'HYDRAULIC_TEAM', capacity: 1, is_available: true },
  { id: 4, code: 'POWER-01', name: '动力装配班组', resource_type: 'POWER_TEAM', capacity: 1, is_available: true },
  { id: 5, code: 'CRANE-01', name: '吊装设备', resource_type: 'CRANE', capacity: 1, is_available: true },
  { id: 6, code: 'QA-01', name: '总装检验员', resource_type: 'QA', capacity: 1, is_available: true },
  { id: 7, code: 'SPACE-BODY-JOIN', name: '机身对接空间', resource_type: 'SPACE', capacity: 1, is_available: true },
  { id: 8, code: 'SPACE-WING-ROOT', name: '翼身对接空间', resource_type: 'SPACE', capacity: 1, is_available: true },
  { id: 9, code: 'SPACE-AVIONICS-BAY', name: '前机身电子舱空间', resource_type: 'SPACE', capacity: 1, is_available: true },
  { id: 10, code: 'SPACE-ENGINE-PYLON', name: '发动机吊装空间', resource_type: 'SPACE', capacity: 1, is_available: true },
  { id: 11, code: 'SPACE-HYD-BAY', name: '液压管路作业空间', resource_type: 'SPACE', capacity: 1, is_available: true },
  { id: 12, code: 'SPACE-FINAL-TEST', name: '全机测试空间', resource_type: 'SPACE', capacity: 1, is_available: true },
]

const resource = (code) => {
  const item = AIRCRAFT_DEMO_RESOURCES.find((r) => r.code === code)
  return {
    resource_code: item.code,
    resource_name: item.name,
    resource_type: item.resource_type,
  }
}

const task = ({
  step_order,
  step_id,
  op_rule_id,
  op_rule_code,
  op_rule_name,
  start_day,
  end_day,
  predecessors = [],
  resources = [],
  not_before = null,
  step_role = 'normal',
}) => ({
  step_order,
  step_id,
  op_rule_id,
  op_rule_code,
  op_rule_name,
  start_min: toMin(start_day),
  end_min: toMin(end_day + 1),
  duration_min: (end_day - start_day + 1) * DAY_MINUTES,
  predecessors,
  resources: resources.map(resource),
  not_before: not_before == null ? null : toMin(not_before),
  step_role,
})

const baseTasks = [
  task({ step_order: 1, step_id: 7101, op_rule_id: 101, op_rule_code: 'A_PREP', op_rule_name: '机身段对接准备', start_day: 1, end_day: 1, resources: ['BODY-TEAM-01', 'SPACE-BODY-JOIN'] }),
  task({ step_order: 2, step_id: 7102, op_rule_id: 102, op_rule_code: 'B_JOIN_FUSELAGE', op_rule_name: '前中后机身对接', start_day: 2, end_day: 4, predecessors: [1], resources: ['BODY-TEAM-01', 'SPACE-BODY-JOIN'] }),
  task({ step_order: 3, step_id: 7103, op_rule_id: 103, op_rule_code: 'C_WING_QA', op_rule_name: '机翼到位验收', start_day: 2, end_day: 3, predecessors: [1], resources: ['QA-01'] }),
  task({ step_order: 4, step_id: 7104, op_rule_id: 104, op_rule_code: 'D_JOIN_WING', op_rule_name: '机翼对接', start_day: 5, end_day: 7, predecessors: [2, 3], resources: ['BODY-TEAM-01', 'CRANE-01', 'SPACE-WING-ROOT'] }),
  task({ step_order: 5, step_id: 7105, op_rule_id: 105, op_rule_code: 'E_ENGINE_MOUNT', op_rule_name: '发动机吊装', start_day: 8, end_day: 9, predecessors: [4], resources: ['POWER-01', 'CRANE-01', 'SPACE-ENGINE-PYLON'] }),
  task({ step_order: 6, step_id: 7106, op_rule_id: 106, op_rule_code: 'F_AVIONICS_RACK', op_rule_name: '航电机架安装', start_day: 8, end_day: 9, predecessors: [4], resources: ['BODY-TEAM-01', 'SPACE-AVIONICS-BAY'] }),
  task({ step_order: 7, step_id: 7107, op_rule_id: 107, op_rule_code: 'G_HYD_PIPE', op_rule_name: '液压管路铺设', start_day: 8, end_day: 10, predecessors: [4], resources: ['HYD-01', 'SPACE-HYD-BAY'] }),
  task({ step_order: 8, step_id: 7108, op_rule_id: 108, op_rule_code: 'H_AVIONICS_LOAD', op_rule_name: '航电设备上架', start_day: 10, end_day: 12, predecessors: [6], resources: ['AVIONICS-01', 'SPACE-AVIONICS-BAY'] }),
  task({ step_order: 9, step_id: 7109, op_rule_id: 109, op_rule_code: 'I_ENGINE_LINES', op_rule_name: '发动机管线连接', start_day: 11, end_day: 12, predecessors: [5, 7], resources: ['POWER-01', 'SPACE-ENGINE-PYLON'] }),
  task({ step_order: 10, step_id: 7110, op_rule_id: 110, op_rule_code: 'J_POWER_CHECK', op_rule_name: '全机通电检查', start_day: 13, end_day: 14, predecessors: [8, 9], resources: ['AVIONICS-01', 'QA-01', 'SPACE-FINAL-TEST'] }),
  task({ step_order: 11, step_id: 7111, op_rule_id: 111, op_rule_code: 'K_GROUND_TEST', op_rule_name: '地面功能试验', start_day: 15, end_day: 16, predecessors: [10], resources: ['AVIONICS-01', 'HYD-01', 'SPACE-FINAL-TEST'] }),
  task({ step_order: 12, step_id: 7112, op_rule_id: 112, op_rule_code: 'L_DELIVERY_QA', op_rule_name: '总装交付检查', start_day: 17, end_day: 17, predecessors: [11], resources: ['QA-01', 'SPACE-FINAL-TEST'] }),
]

const mechanicalTasks = [
  ...baseTasks.slice(0, 4),
  task({ step_order: 5, step_id: 7205, op_rule_id: 113, op_rule_code: 'X_SEAL_REWORK', op_rule_name: '机身密封返修', start_day: 8, end_day: 9, predecessors: [4], resources: ['BODY-TEAM-01', 'QA-01', 'SPACE-AVIONICS-BAY'], step_role: 'repair' }),
  task({ step_order: 6, step_id: 7206, op_rule_id: 105, op_rule_code: 'E_ENGINE_MOUNT', op_rule_name: '发动机吊装', start_day: 11, end_day: 12, predecessors: [4], resources: ['POWER-01', 'CRANE-01', 'SPACE-ENGINE-PYLON'], not_before: 11, step_role: 'delayed' }),
  task({ step_order: 7, step_id: 7207, op_rule_id: 107, op_rule_code: 'G_HYD_PIPE', op_rule_name: '液压管路铺设', start_day: 8, end_day: 10, predecessors: [4], resources: ['HYD-01', 'SPACE-HYD-BAY'] }),
  task({ step_order: 8, step_id: 7208, op_rule_id: 106, op_rule_code: 'F_AVIONICS_RACK', op_rule_name: '航电机架安装', start_day: 13, end_day: 14, predecessors: [4], resources: ['BODY-TEAM-01', 'SPACE-AVIONICS-BAY'], step_role: 'delayed' }),
  task({ step_order: 9, step_id: 7209, op_rule_id: 109, op_rule_code: 'I_ENGINE_LINES', op_rule_name: '发动机管线连接', start_day: 13, end_day: 14, predecessors: [6, 7], resources: ['POWER-01', 'SPACE-ENGINE-PYLON'] }),
  task({ step_order: 10, step_id: 7210, op_rule_id: 108, op_rule_code: 'H_AVIONICS_LOAD', op_rule_name: '航电设备上架', start_day: 15, end_day: 17, predecessors: [8], resources: ['AVIONICS-01', 'SPACE-AVIONICS-BAY'], step_role: 'delayed' }),
  task({ step_order: 11, step_id: 7211, op_rule_id: 110, op_rule_code: 'J_POWER_CHECK', op_rule_name: '全机通电检查', start_day: 18, end_day: 19, predecessors: [9, 10], resources: ['AVIONICS-01', 'QA-01', 'SPACE-FINAL-TEST'], step_role: 'delayed' }),
  task({ step_order: 12, step_id: 7212, op_rule_id: 111, op_rule_code: 'K_GROUND_TEST', op_rule_name: '地面功能试验', start_day: 20, end_day: 21, predecessors: [11], resources: ['AVIONICS-01', 'HYD-01', 'SPACE-FINAL-TEST'], step_role: 'delayed' }),
  task({ step_order: 13, step_id: 7213, op_rule_id: 112, op_rule_code: 'L_DELIVERY_QA', op_rule_name: '总装交付检查', start_day: 22, end_day: 22, predecessors: [12], resources: ['QA-01', 'SPACE-FINAL-TEST'], step_role: 'delayed' }),
]

const optimizedTasks = [
  ...baseTasks.slice(0, 4),
  task({ step_order: 5, step_id: 7305, op_rule_id: 106, op_rule_code: 'F_AVIONICS_RACK', op_rule_name: '航电机架安装', start_day: 8, end_day: 9, predecessors: [4], resources: ['BODY-TEAM-01', 'SPACE-AVIONICS-BAY'], step_role: 'pulled_forward' }),
  task({ step_order: 6, step_id: 7306, op_rule_id: 107, op_rule_code: 'G_HYD_PIPE', op_rule_name: '液压管路铺设', start_day: 8, end_day: 10, predecessors: [4], resources: ['HYD-01', 'SPACE-HYD-BAY'] }),
  task({ step_order: 7, step_id: 7307, op_rule_id: 113, op_rule_code: 'X_SEAL_REWORK', op_rule_name: '机身密封返修', start_day: 10, end_day: 11, predecessors: [4], resources: ['BODY-TEAM-01', 'QA-01', 'SPACE-AVIONICS-BAY'], step_role: 'repair' }),
  task({ step_order: 8, step_id: 7308, op_rule_id: 105, op_rule_code: 'E_ENGINE_MOUNT', op_rule_name: '发动机吊装', start_day: 11, end_day: 12, predecessors: [4], resources: ['POWER-01', 'CRANE-01', 'SPACE-ENGINE-PYLON'], not_before: 11, step_role: 'delayed' }),
  task({ step_order: 9, step_id: 7309, op_rule_id: 108, op_rule_code: 'H_AVIONICS_LOAD', op_rule_name: '航电设备上架', start_day: 12, end_day: 14, predecessors: [5], resources: ['AVIONICS-01', 'SPACE-AVIONICS-BAY'], step_role: 'pulled_forward' }),
  task({ step_order: 10, step_id: 7310, op_rule_id: 109, op_rule_code: 'I_ENGINE_LINES', op_rule_name: '发动机管线连接', start_day: 13, end_day: 14, predecessors: [6, 8], resources: ['POWER-01', 'SPACE-ENGINE-PYLON'] }),
  task({ step_order: 11, step_id: 7311, op_rule_id: 110, op_rule_code: 'J_POWER_CHECK', op_rule_name: '全机通电检查', start_day: 15, end_day: 16, predecessors: [7, 9, 10], resources: ['AVIONICS-01', 'QA-01', 'SPACE-FINAL-TEST'] }),
  task({ step_order: 12, step_id: 7312, op_rule_id: 111, op_rule_code: 'K_GROUND_TEST', op_rule_name: '地面功能试验', start_day: 17, end_day: 18, predecessors: [11], resources: ['AVIONICS-01', 'HYD-01', 'SPACE-FINAL-TEST'] }),
  task({ step_order: 13, step_id: 7313, op_rule_id: 112, op_rule_code: 'L_DELIVERY_QA', op_rule_name: '总装交付检查', start_day: 19, end_day: 19, predecessors: [12], resources: ['QA-01', 'SPACE-FINAL-TEST'] }),
]

const schedule = (id, candidate_plan_id, tasks, makespanDays, solver_status = 'optimal') => ({
  id,
  solve_request_id: id,
  candidate_plan_id,
  makespan: makespanDays * DAY_MINUTES,
  solver_status,
  tasks,
  parallel_groups: [
    ['E_ENGINE_MOUNT', 'F_AVIONICS_RACK', 'G_HYD_PIPE'],
    ['H_AVIONICS_LOAD', 'I_ENGINE_LINES'],
  ],
  created_at: now(),
})

const stateDelta = [
  { feature_key: 'wing_joined', from_value: 'false', to_value: 'true' },
  { feature_key: 'engine_mounted', from_value: 'false', to_value: 'true' },
  { feature_key: 'avionics_ready', from_value: 'false', to_value: 'true' },
  { feature_key: 'power_check', from_value: 'false', to_value: 'true' },
  { feature_key: 'delivery_ready', from_value: 'false', to_value: 'true' },
]

export const AIRCRAFT_DEMO_RESPONSES = {
  initial: {
    solve_request_id: 9101,
    status: 'done',
    candidate_plan_id: 8101,
    state_delta: stateDelta,
    critical_path: ['A_PREP', 'B_JOIN_FUSELAGE', 'D_JOIN_WING', 'F_AVIONICS_RACK', 'H_AVIONICS_LOAD', 'J_POWER_CHECK', 'K_GROUND_TEST', 'L_DELIVERY_QA'],
    schedule: schedule(9101, 8101, baseTasks, 17),
  },
  mechanical: {
    solve_request_id: 9102,
    status: 'done',
    candidate_plan_id: 8102,
    state_delta: stateDelta,
    critical_path: ['A_PREP', 'B_JOIN_FUSELAGE', 'D_JOIN_WING', 'F_AVIONICS_RACK', 'H_AVIONICS_LOAD', 'J_POWER_CHECK', 'K_GROUND_TEST', 'L_DELIVERY_QA'],
    schedule: schedule(9102, 8102, mechanicalTasks, 22, 'reference'),
  },
  optimized: {
    solve_request_id: 9103,
    status: 'done',
    candidate_plan_id: 8103,
    state_delta: stateDelta,
    critical_path: ['A_PREP', 'B_JOIN_FUSELAGE', 'D_JOIN_WING', 'F_AVIONICS_RACK', 'H_AVIONICS_LOAD', 'J_POWER_CHECK', 'K_GROUND_TEST', 'L_DELIVERY_QA'],
    schedule: schedule(9103, 8103, optimizedTasks, 19),
  },
}

export const AIRCRAFT_DEMO_VERSIONS = [
  { id: 8101, version: 1, replan_reason: 'initial', parent_plan_id: null, status: 'scheduled', total_steps: 12, created_at: now() },
  { id: 8103, version: 2, replan_reason: 'blockage_strategy_ab', parent_plan_id: 8101, status: 'scheduled', total_steps: 13, created_at: now() },
]

const tasksByKey = (tasks) =>
  new Map(tasks.map((item) => [`${item.op_rule_code}:${item.op_rule_id}`, item]))

export function buildAircraftDemoDiff(basePlanId = 8101, newPlanId = 8103) {
  const baseTasksByKey = tasksByKey(AIRCRAFT_DEMO_RESPONSES.initial.schedule.tasks)
  const newTasksByKey = tasksByKey(AIRCRAFT_DEMO_RESPONSES.optimized.schedule.tasks)
  const keys = [...new Set([...baseTasksByKey.keys(), ...newTasksByKey.keys()])]

  const steps = keys.map((key) => {
    const base = baseTasksByKey.get(key)
    const next = newTasksByKey.get(key)
    return {
      op_code: next?.op_rule_code ?? base?.op_rule_code,
      op_name: next?.op_rule_name ?? base?.op_rule_name,
      step_order: next?.step_order ?? base?.step_order,
      base_start: base?.start_min ?? null,
      base_end: base?.end_min ?? null,
      new_start: next?.start_min ?? null,
      new_end: next?.end_min ?? null,
      step_role: next?.step_role ?? 'normal',
      not_before: next?.not_before ?? null,
    }
  })

  steps.sort((a, b) => (a.new_start ?? 999999) - (b.new_start ?? 999999) || a.op_code.localeCompare(b.op_code))

  return {
    base_plan_id: basePlanId,
    new_plan_id: newPlanId,
    base_makespan: AIRCRAFT_DEMO_RESPONSES.initial.schedule.makespan,
    new_makespan: AIRCRAFT_DEMO_RESPONSES.optimized.schedule.makespan,
    steps,
  }
}

export function getAircraftDemoMachines() {
  return Promise.resolve(AIRCRAFT_DEMO_MACHINES)
}

export function getAircraftDemoStates() {
  return Promise.resolve(AIRCRAFT_DEMO_STATES)
}

export function postAircraftDemoSolve(payload = {}) {
  const hasReplan = payload.parent_plan_id || payload.blockage_constraints
  return Promise.resolve(hasReplan ? AIRCRAFT_DEMO_RESPONSES.optimized : AIRCRAFT_DEMO_RESPONSES.initial)
}

export function getAircraftDemoPlanVersions() {
  return Promise.resolve(AIRCRAFT_DEMO_VERSIONS)
}

export function getAircraftDemoPlanDiff(basePlanId, newPlanId) {
  return Promise.resolve(buildAircraftDemoDiff(basePlanId, newPlanId))
}

export { DAY_MINUTES }
