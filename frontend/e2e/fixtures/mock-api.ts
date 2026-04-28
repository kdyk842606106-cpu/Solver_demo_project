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
  makespan_min: 45,
  status: 'optimal',
  created_at: new Date().toISOString(),
  tasks: [
    {
      task_id: 1,
      op_rule_id: 1,
      op_rule_code: 'OP_WARMUP',
      op_rule_name: 'Warm Up Machine',
      start_min: 0,
      end_min: 30,
      duration_min: 30,
      assigned_resource_ids: [1],
      assigned_resource_codes: ['TECH-01'],
      state_before: { temperature_level: 'cold', clean_level: 'dirty', calibration: 'off' },
      state_after: { temperature_level: 'hot', clean_level: 'dirty', calibration: 'off' },
      predecessor_ids: [],
      is_parallel: false,
      is_blocked: false,
      is_delayed: false,
    },
    {
      task_id: 2,
      op_rule_id: 3,
      op_rule_code: 'OP_CALIBRATE',
      op_rule_name: 'Calibrate Machine',
      start_min: 30,
      end_min: 45,
      duration_min: 15,
      assigned_resource_ids: [1],
      assigned_resource_codes: ['TECH-01'],
      state_before: { temperature_level: 'hot', clean_level: 'dirty', calibration: 'off' },
      state_after: { temperature_level: 'hot', clean_level: 'dirty', calibration: 'on' },
      predecessor_ids: [1],
      is_parallel: false,
      is_blocked: false,
      is_delayed: false,
    },
  ],
}

export const DELAYED_SCHEDULE = {
  ...BASE_SCHEDULE,
  tasks: [
    {
      ...BASE_SCHEDULE.tasks[0],
      start_min: 25,
      end_min: 55,
      is_delayed: true,
      delay_reason: '策略 A：延后执行',
    },
    {
      ...BASE_SCHEDULE.tasks[1],
      start_min: 55,
      end_min: 70,
      predecessor_ids: [1],
    },
  ],
}

export const REPAIR_SCHEDULE = {
  ...BASE_SCHEDULE,
  tasks: [
    {
      task_id: 1,
      op_rule_id: 50,
      op_rule_code: 'OP_REPAIR_WORN',
      op_rule_name: 'Repair Worn Parts',
      start_min: 0,
      end_min: 40,
      duration_min: 40,
      assigned_resource_ids: [1],
      assigned_resource_codes: ['TECH-01'],
      predecessor_ids: [],
      is_blocked: false,
      is_delayed: false,
    },
    {
      task_id: 2,
      op_rule_id: 1,
      op_rule_code: 'OP_WARMUP',
      op_rule_name: 'Warm Up Machine',
      start_min: 40,
      end_min: 70,
      duration_min: 30,
      assigned_resource_ids: [1],
      assigned_resource_codes: ['TECH-01'],
      predecessor_ids: [1],
      is_blocked: false,
      is_delayed: false,
    },
    {
      task_id: 3,
      op_rule_id: 3,
      op_rule_code: 'OP_CALIBRATE',
      op_rule_name: 'Calibrate Machine',
      start_min: 70,
      end_min: 85,
      duration_min: 15,
      assigned_resource_ids: [1],
      assigned_resource_codes: ['TECH-01'],
      predecessor_ids: [2],
      is_blocked: false,
      is_delayed: false,
    },
  ],
}

export function createMockRouteHandler(schedule: typeof BASE_SCHEDULE) {
  return async (route: any, request: any) => {
    const url = request.url()
    const method = request.method()

    if (url.endsWith('/health')) {
      await route.fulfill({ status: 200, body: JSON.stringify({ status: 'ok' }) })
      return
    }

    if (url.includes('/api/v1/machines')) {
      await route.fulfill({ status: 200, body: JSON.stringify(MOCK_MACHINES) })
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

    if (url.includes('/api/v1/states')) {
      const machineId = new URL(url).searchParams.get('machine_id')
      const states = MOCK_STATES.filter(s => s.state_id === Number(machineId))
      await route.fulfill({ status: 200, body: JSON.stringify(states) })
      return
    }

    if (url.includes('/api/v1/solve') && method === 'POST') {
      await route.fulfill({ status: 200, body: JSON.stringify(schedule) })
      return
    }

    if (url.includes('/api/v1/solve/') && method === 'PATCH') {
      await route.fulfill({ status: 200, body: JSON.stringify(schedule) })
      return
    }

    await route.continue()
  }
}
