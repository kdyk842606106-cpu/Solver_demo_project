// frontend/e2e/fixtures/mock-api.ts
// Shared API mocks for Playwright E2E tests

export const MOCK_MACHINES = [
  { id: 1, code: 'M-001', name: 'Main CNC Lathe', location: 'Workshop A', machine_type_id: 1 },
]

export const MOCK_MACHINE_TYPES = [
  { id: 1, code: 'LATHE', name: 'CNC Lathe', description: 'Standard lathe' },
]

export const MOCK_RESOURCES = [
  { id: 1, code: 'TECH-01', name: 'Technician Alice', resource_type: 'human' },
  { id: 2, code: 'TECH-02', name: 'Technician Bob', resource_type: 'human' },
  { id: 3, code: 'CLEAN-01', name: 'Cleaning Robot', resource_type: 'machine' },
]

export const MOCK_STATE_NODES = [
  {
    id: 10,
    machine_type_id: 1,
    parent_id: null,
    level: 1,
    code: 'PKG_MECH_DONE',
    name: '机械集成完成',
    feature_key: null,
    operator: 'eq',
    target_value: null,
    state_kind: 'aggregate',
    sort_order: 1,
    is_active: true,
    metadata_json: null,
    created_at: new Date().toISOString(),
  },
  {
    id: 11,
    machine_type_id: 1,
    parent_id: 10,
    level: 2,
    code: 'STATE_MODULE_A_DONE',
    name: '模块A已安装',
    feature_key: 'module_dim_installed__module_a',
    operator: 'eq',
    target_value: '已安装',
    state_kind: 'atomic',
    sort_order: 1,
    is_active: true,
    metadata_json: {
      dimension_template_key: 'module_dim_installed',
      state_object_name: '模块A',
    },
    created_at: new Date().toISOString(),
  },
  {
    id: 12,
    machine_type_id: 1,
    parent_id: null,
    level: 1,
    code: 'REF_MODULE_B_DONE',
    name: '模块B已安装',
    feature_key: 'module_dim_installed__module_b',
    operator: 'eq',
    target_value: '已安装',
    state_kind: 'atomic',
    sort_order: 2,
    is_active: true,
    metadata_json: {
      dimension_template_key: 'module_dim_installed',
      state_object_name: '模块B',
    },
    created_at: new Date().toISOString(),
  },
]

export const MOCK_STATE_NODE_REFERENCES = [
  {
    id: 900,
    state_node_id: 12,
    parent_state_node_id: 10,
    sort_order: 2,
    is_active: true,
    metadata_json: null,
    state_node_code: 'REF_MODULE_B_DONE',
    state_node_name: '模块B已安装',
    parent_state_node_code: 'PKG_MECH_DONE',
    parent_state_node_name: '机械集成完成',
    created_at: new Date().toISOString(),
  },
]

export const MOCK_ACTIVITY_NODES = [
  {
    id: 20,
    machine_type_id: 1,
    parent_id: null,
    level: 1,
    code: 'ACT_MECH',
    name: '机械活动',
    description: '',
    activity_category: 'normal',
    sort_order: 1,
    is_active: true,
    metadata_json: null,
    created_at: new Date().toISOString(),
  },
]

export const MOCK_STATES = [
  {
    state_id: 1,
    state_type: 'current',
    label: 'Cold Dirty Standby',
    features: { temperature_level: 'cold', clean_level: 'dirty', calibration: 'off' },
  },
  {
    state_id: 2,
    state_type: 'target',
    label: 'Hot Clean Calibrated',
    features: { temperature_level: 'hot', clean_level: 'clean', calibration: 'on' },
  },
  {
    state_id: 3,
    state_type: 'current',
    label: 'Cold Standby with Blockage',
    features: { temperature_level: 'cold', clean_level: 'dirty', calibration: 'off', blockage_reason: 'mechanical_wear' },
  },
  {
    state_id: 4,
    state_type: 'target',
    label: 'Ready for Production with Blockage',
    features: { temperature_level: 'hot', clean_level: 'clean', calibration: 'on', blockage_reason: '' },
  },
  {
    state_id: 5,
    state_type: 'current',
    label: 'Cold Standby',
    features: { temperature_level: 'cold', clean_level: 'dirty', calibration: 'off' },
  },
  {
    state_id: 6,
    state_type: 'target',
    label: 'Hot Calibrated',
    features: { temperature_level: 'hot', clean_level: 'dirty', calibration: 'on' },
  },
]

export const BASE_SCHEDULE = {
  schedule_id: 101,
  machine_id: 1,
  current_state_id: 1,
  target_state_id: 2,
  total_duration_min: 45,
  makespan: 45,
  status: 'optimal',
  created_at: new Date().toISOString(),
  tasks: [
    {
      task_id: 1,
      step_order: 1,
      op_rule_id: 1,
      op_rule_code: 'OP_WARMUP',
      op_rule_name: 'Warm Up Machine',
      start_min: 0,
      end_min: 30,
      duration_min: 30,
      assigned_resource_ids: [1],
      assigned_resource_codes: ['TECH-01'],
      resources: [{ resource_code: 'TECH-01', resource_name: 'Technician Alice' }],
      state_before: { temperature_level: 'cold', clean_level: 'dirty', calibration: 'off' },
      state_after: { temperature_level: 'hot', clean_level: 'dirty', calibration: 'off' },
      predecessor_ids: [],
      is_parallel: false,
      is_blocked: false,
      is_delayed: false,
      step_role: 'normal',
    },
    {
      task_id: 2,
      step_order: 2,
      op_rule_id: 3,
      op_rule_code: 'OP_CALIBRATE',
      op_rule_name: 'Calibrate Machine',
      start_min: 30,
      end_min: 45,
      duration_min: 15,
      assigned_resource_ids: [1],
      assigned_resource_codes: ['TECH-01'],
      resources: [{ resource_code: 'TECH-01', resource_name: 'Technician Alice' }],
      state_before: { temperature_level: 'hot', clean_level: 'dirty', calibration: 'off' },
      state_after: { temperature_level: 'hot', clean_level: 'dirty', calibration: 'on' },
      predecessor_ids: [1],
      is_parallel: false,
      is_blocked: false,
      is_delayed: false,
      step_role: 'normal',
    },
  ],
}

export const STATE_LANE_SCHEDULE = {
  ...BASE_SCHEDULE,
  schedule_id: 202,
  makespan: 55,
  tasks: [
    {
      ...BASE_SCHEDULE.tasks[0],
      task_id: 11,
      step_order: 1,
      op_rule_id: 11,
      op_rule_code: 'OP_STRUCTURE_BASE',
      op_rule_name: 'Install Structure Base',
      start_min: 0,
      end_min: 20,
      duration_min: 20,
      activity_group_id: 301,
      activity_group_code: 'MECH_ASSEMBLY',
      activity_group_name: 'Mechanical Assembly',
      state_continuity_groups: [
        {
          state_group_id: 6101,
          state_group_code: 'MECH_INTEGRATION_COMPLETE',
          state_group_name: 'Mechanical Integration Complete',
          state_group_level: 1,
          parent_state_group_id: null,
        },
        {
          state_group_id: 6102,
          state_group_code: 'STRUCTURE_ASSEMBLY_COMPLETE',
          state_group_name: 'Structure Assembly Complete',
          state_group_level: 2,
          parent_state_group_id: 6101,
        },
      ],
    },
    {
      ...BASE_SCHEDULE.tasks[1],
      task_id: 12,
      step_order: 2,
      op_rule_id: 12,
      op_rule_code: 'OP_TRANSFER_READY',
      op_rule_name: 'Prepare Transfer Mechanism',
      start_min: 20,
      end_min: 40,
      duration_min: 20,
      activity_group_id: 302,
      activity_group_code: 'TRANSFER_READY',
      activity_group_name: 'Transfer Mechanism',
      state_continuity_groups: [
        {
          state_group_id: 6101,
          state_group_code: 'MECH_INTEGRATION_COMPLETE',
          state_group_name: 'Mechanical Integration Complete',
          state_group_level: 1,
          parent_state_group_id: null,
        },
        {
          state_group_id: 6103,
          state_group_code: 'TRANSFER_MECHANISM_READY',
          state_group_name: 'Transfer Mechanism Ready',
          state_group_level: 2,
          parent_state_group_id: 6101,
        },
      ],
    },
    {
      task_id: 13,
      step_order: 3,
      op_rule_id: 13,
      op_rule_code: 'OP_DOCUMENT_CHECK',
      op_rule_name: 'Document Check',
      start_min: 40,
      end_min: 55,
      duration_min: 15,
      assigned_resource_ids: [2],
      assigned_resource_codes: ['TECH-02'],
      resources: [{ resource_code: 'TECH-02', resource_name: 'Technician Bob' }],
      predecessor_ids: [2],
      is_parallel: false,
      is_blocked: false,
      is_delayed: false,
      step_role: 'normal',
      activity_group_id: 303,
      activity_group_code: 'QUALITY_CHECK',
      activity_group_name: 'Quality Check',
      state_continuity_groups: [],
    },
  ],
}

export const STATE_LANE_RESULT_EXTRAS = {
  layered: {
    preflight_health: { status: 'ok', checks: [] },
    state_tree: [],
    activity_tree: [],
    activity_selection: [],
    state_replay: { status: 'ok', goal_results: [] },
  },
  diagnostics: {
    schedule: {
      state_group_continuity: {
        group_count: 2,
        objective_weights: {},
        groups: [
          {
            state_group_id: 6102,
            state_group_code: 'STRUCTURE_ASSEMBLY_COMPLETE',
            state_group_name: 'Structure Assembly Complete',
            parent_state_group_id: 6101,
            scheduled_task_count: 1,
            task_step_orders: [1],
            window_start_min: 0,
            window_end_min: 20,
            internal_gap_min: 0,
            interruption_count: 0,
            is_compact: true,
          },
          {
            state_group_id: 6103,
            state_group_code: 'TRANSFER_MECHANISM_READY',
            state_group_name: 'Transfer Mechanism Ready',
            parent_state_group_id: 6101,
            scheduled_task_count: 1,
            task_step_orders: [2],
            window_start_min: 20,
            window_end_min: 40,
            internal_gap_min: 0,
            interruption_count: 0,
            is_compact: true,
          },
        ],
      },
    },
  },
}

export const DELAYED_SCHEDULE = {
  ...BASE_SCHEDULE,
  makespan: 70,
  tasks: [
    {
      ...BASE_SCHEDULE.tasks[0],
      step_order: 1,
      step_role: 'delayed',
      start_min: 25,
      end_min: 55,
      is_delayed: true,
      delay_reason: '策略 A：延后执行',
      resources: [{ resource_code: 'TECH-01', resource_name: 'Technician Alice' }],
    },
    {
      ...BASE_SCHEDULE.tasks[1],
      step_order: 2,
      start_min: 55,
      end_min: 70,
      predecessor_ids: [1],
      resources: [{ resource_code: 'TECH-01', resource_name: 'Technician Alice' }],
    },
  ],
}

export const REPAIR_SCHEDULE = {
  ...BASE_SCHEDULE,
  makespan: 85,
  tasks: [
    {
      task_id: 1,
      step_order: 1,
      op_rule_id: 50,
      op_rule_code: 'OP_REPAIR_WORN',
      op_rule_name: 'Repair Worn Parts',
      start_min: 0,
      end_min: 40,
      duration_min: 40,
      assigned_resource_ids: [1],
      assigned_resource_codes: ['TECH-01'],
      resources: [{ resource_code: 'TECH-01', resource_name: 'Technician Alice' }],
      predecessor_ids: [],
      is_blocked: false,
      is_delayed: false,
      step_role: 'repair',
    },
    {
      task_id: 2,
      step_order: 2,
      op_rule_id: 1,
      op_rule_code: 'OP_WARMUP',
      op_rule_name: 'Warm Up Machine',
      start_min: 40,
      end_min: 70,
      duration_min: 30,
      assigned_resource_ids: [1],
      assigned_resource_codes: ['TECH-01'],
      resources: [{ resource_code: 'TECH-01', resource_name: 'Technician Alice' }],
      predecessor_ids: [1],
      is_blocked: false,
      is_delayed: false,
      step_role: 'normal',
    },
    {
      task_id: 3,
      step_order: 3,
      op_rule_id: 3,
      op_rule_code: 'OP_CALIBRATE',
      op_rule_name: 'Calibrate Machine',
      start_min: 70,
      end_min: 85,
      duration_min: 15,
      assigned_resource_ids: [1],
      assigned_resource_codes: ['TECH-01'],
      resources: [{ resource_code: 'TECH-01', resource_name: 'Technician Alice' }],
      predecessor_ids: [2],
      is_blocked: false,
      is_delayed: false,
      step_role: 'normal',
    },
  ],
}

export function createMockRouteHandler(schedule: any, resultExtras: Record<string, any> = {}) {
  return async (route: any, request: any) => {
    const url = request.url()
    const method = request.method()

    if (url.endsWith('/health')) {
      await route.fulfill({ status: 200, body: JSON.stringify({ status: 'ok' }) })
      return
    }

    // States must be checked BEFORE machines because the endpoint is
    // /api/v1/machines/:id/states and would otherwise match the machines branch.
    if (url.includes('/states')) {
      // Return all mock states (single-machine test fixtures)
      await route.fulfill({ status: 200, body: JSON.stringify({ states: MOCK_STATES }) })
      return
    }

    if (url.includes('/api/v1/machines')) {
      await route.fulfill({ status: 200, body: JSON.stringify(MOCK_MACHINES) })
      return
    }

    if (url.includes('/api/v1/machine-types/') && url.includes('/state-node-references')) {
      await route.fulfill({ status: 200, body: JSON.stringify(MOCK_STATE_NODE_REFERENCES) })
      return
    }

    if (url.includes('/api/v1/machine-types/') && url.includes('/state-nodes')) {
      await route.fulfill({ status: 200, body: JSON.stringify(MOCK_STATE_NODES) })
      return
    }

    if (url.includes('/api/v1/machine-types/') && url.includes('/activity-nodes')) {
      await route.fulfill({ status: 200, body: JSON.stringify(MOCK_ACTIVITY_NODES) })
      return
    }

    if (url.includes('/api/v1/machine-types/') && url.includes('/maintenance-intent-templates')) {
      await route.fulfill({ status: 200, body: JSON.stringify([]) })
      return
    }

    if (url.includes('/api/v1/machine-types')) {
      await route.fulfill({ status: 200, body: JSON.stringify(MOCK_MACHINE_TYPES) })
      return
    }

    if (url.includes('/api/v1/resources')) {
      await route.fulfill({ status: 200, body: JSON.stringify(MOCK_RESOURCES) })
      return
    }

    if (url.includes('/features')) {
      await route.fulfill({
        status: 200,
        body: JSON.stringify([
          {
            feature_key: 'blockage_reason',
            display_name: '阻塞原因',
            value_type: 'enum',
            allowed_values: ['mechanical_wear', 'electrical_fault', 'coolant_leak', 'tool_breakage'],
          },
        ]),
      })
      return
    }

    if (url.includes('/api/v1/solve') && method === 'POST') {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          status: 'done',
          schedule: schedule,
          candidate_plan_id: schedule.schedule_id,
          state_delta: [],
          critical_path: [],
          ...resultExtras,
        })
      })
      return
    }

    if (url.includes('/api/v1/solve/') && method === 'PATCH') {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          status: 'done',
          schedule: schedule,
          candidate_plan_id: schedule.schedule_id,
          state_delta: [],
          critical_path: [],
          ...resultExtras,
        })
      })
      return
    }

    // Plan versions & diff (called by applyResult after solve)
    if (url.includes('/plans/') && url.includes('/versions')) {
      const id = url.match(/\/plans\/(\d+)\/versions/)?.[1]
      await route.fulfill({
        status: 200,
        body: JSON.stringify([
          { id: Number(id), version: 1, created_at: new Date().toISOString() },
        ]),
      })
      return
    }

    if (url.includes('/plans/') && url.includes('/diff/')) {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({ steps: [] }),
      })
      return
    }

    await route.continue()
  }
}
