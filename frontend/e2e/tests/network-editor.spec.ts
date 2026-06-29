import { test, expect } from '@playwright/test'

const impactDebounceBufferMs = 260

const machineTypes = [
  { id: 1, code: 'LATHE', name: 'CNC Lathe', description: 'Network editor fixture' },
]

const stateFeatureDefs = [
  'ready_flag',
  'draft_nested_state',
  'draft_atomic_option',
  'referenced_package_draft_state',
  ...Array.from({ length: 6 }, (_, index) => `input_${index + 1}`),
].map((featureKey, index) => ({
  id: 1000 + index,
  machine_type_id: 1,
  feature_key: featureKey,
  feature_name: featureKey,
  value_type: 'enum',
  allowed_values: ['false', 'true'],
}))

const extraAtomicInputStates = Array.from({ length: 6 }, (_, index) => {
  const id = 5 + index
  return {
    id,
    machine_type_id: 1,
    parent_id: null,
    level: 3,
    code: `INPUT_${index + 1}`,
    name: `额外输入状态${index + 1}`,
    state_kind: 'atomic',
    feature_key: `input_${index + 1}`,
    operator: 'eq',
    target_value: 'true',
    sort_order: 10 + index,
    is_active: true,
    metadata_json: { _network_editor_layout: { x: 110, y: 480 + index * 72 } },
  }
})

const stateNodes = [
  {
    id: 1,
    machine_type_id: 1,
    parent_id: null,
    level: 1,
    code: 'PKG_READY',
    name: '准备状态包',
    state_kind: 'aggregate',
    feature_key: null,
    operator: 'eq',
    target_value: null,
    sort_order: 1,
    is_active: true,
    metadata_json: { _network_editor_layout: { x: 80, y: 80 } },
  },
  {
    id: 3,
    machine_type_id: 1,
    parent_id: 1,
    level: 2,
    code: 'STATE_IN_READY',
    name: '包内原子状态',
    state_kind: 'atomic',
    feature_key: 'ready_flag',
    operator: 'eq',
    target_value: 'true',
    sort_order: 1,
    is_active: true,
    metadata_json: { _network_editor_layout: { x: 125, y: 230 } },
  },
  {
    id: 4,
    machine_type_id: 1,
    parent_id: null,
    level: 1,
    code: 'STATE_DONE',
    name: '跨层级目标状态',
    state_kind: 'aggregate',
    feature_key: null,
    operator: 'eq',
    target_value: null,
    sort_order: 2,
    is_active: true,
    metadata_json: { _network_editor_layout: { x: 80, y: 390 } },
  },
  ...extraAtomicInputStates,
]

const activityNodes = [
  {
    id: 10,
    machine_type_id: 1,
    parent_id: null,
    level: 2,
    code: 'VA_PREP',
    name: '准备虚拟活动',
    description: '',
    activity_category: 'operation',
    sort_order: 1,
    is_active: true,
    metadata_json: { _network_editor_layout: { x: 520, y: 100 } },
  },
]

const atomicActivities = [
  {
    id: 20,
    machine_type_id: 1,
    code: 'AA_FINISH',
    name: '完成原子活动',
    description: '',
    activity_category: 'operation',
    sort_order: 1,
    is_active: true,
    metadata_json: { _network_editor_layout: { x: 520, y: 260 } },
  },
]

const extraAtomicInputBindings = extraAtomicInputStates.map((state, index) => ({
  id: 200 + index,
  machine_type_id: 1,
  activity_node_id: null,
  atomic_activity_id: 20,
  op_rule_id: 900,
  state_node_id: state.id,
  binding_role: 'input',
  binding_type: 'direct',
  coverage_policy: 'explicit',
  covered_leaf_state_ids: [state.id],
  coverage_status: 'complete',
  is_inherited: false,
  is_active: true,
  metadata_json: null,
}))

const bindings = [
  {
    id: 100,
    machine_type_id: 1,
    activity_node_id: 10,
    atomic_activity_id: null,
    op_rule_id: null,
    state_node_id: 1,
    binding_role: 'context_input',
    binding_type: 'state_package',
    coverage_policy: 'all_active_leaves',
    covered_leaf_state_ids: [3],
    coverage_status: 'complete',
    is_inherited: false,
    is_active: true,
    metadata_json: null,
  },
  {
    id: 101,
    machine_type_id: 1,
    activity_node_id: null,
    atomic_activity_id: 20,
    op_rule_id: 900,
    state_node_id: 4,
    binding_role: 'output',
    binding_type: 'direct',
    coverage_policy: 'explicit',
    covered_leaf_state_ids: [4],
    coverage_status: 'complete',
    is_inherited: false,
    is_active: true,
    metadata_json: null,
  },
  {
    id: 102,
    machine_type_id: 1,
    activity_node_id: 10,
    atomic_activity_id: null,
    op_rule_id: null,
    state_node_id: 4,
    binding_role: 'declared_output',
    binding_type: 'direct',
    coverage_policy: 'explicit',
    covered_leaf_state_ids: [4],
    coverage_status: 'complete',
    is_inherited: false,
    is_active: true,
    metadata_json: null,
  },
  ...extraAtomicInputBindings,
]

const graphResponse = {
  machine_type_id: 1,
  revision: 'network-editor-e2e-revision',
  view_mode: 'outline',
  state_nodes: [
    {
      id: 'state_node:1',
      state_node_id: 1,
      parent_id: null,
      primary_parent_graph_id: null,
      reference_parent_ids: [],
      reference_ids: [],
      child_ids: [3],
      level: 1,
      code: 'PKG_READY',
      name: '准备状态包',
      state_kind: 'aggregate',
      feature_key: null,
      operator: 'eq',
      target_value: null,
      is_active: true,
      is_leaf: false,
      leaf_state_ids: [3],
      leaf_count: 1,
      path_ids: [1],
      metadata_json: { _network_editor_layout: { x: 80, y: 80 } },
      reference_id: null,
      is_reference_instance: false,
    },
    {
      id: 'state_node:3',
      state_node_id: 3,
      parent_id: 1,
      primary_parent_graph_id: 'state_node:1',
      reference_parent_ids: [],
      reference_ids: [],
      child_ids: [],
      level: 2,
      code: 'STATE_IN_READY',
      name: '包内原子状态',
      state_kind: 'atomic',
      feature_key: 'ready_flag',
      operator: 'eq',
      target_value: 'true',
      is_active: true,
      is_leaf: true,
      leaf_state_ids: [3],
      leaf_count: 1,
      path_ids: [1, 3],
      metadata_json: { _network_editor_layout: { x: 125, y: 230 } },
      reference_id: null,
      is_reference_instance: false,
    },
    {
      id: 'state_node:4',
      state_node_id: 4,
      parent_id: null,
      primary_parent_graph_id: null,
      reference_parent_ids: [],
      reference_ids: [],
      child_ids: [],
      level: 1,
      code: 'STATE_DONE',
      name: '跨层级目标状态',
      state_kind: 'aggregate',
      feature_key: null,
      operator: 'eq',
      target_value: null,
      is_active: true,
      is_leaf: false,
      leaf_state_ids: [4],
      leaf_count: 1,
      path_ids: [4],
      metadata_json: { _network_editor_layout: { x: 80, y: 390 } },
      reference_id: null,
      is_reference_instance: false,
    },
    ...extraAtomicInputStates.map((state) => ({
      id: `state_node:${state.id}`,
      state_node_id: state.id,
      parent_id: null,
      primary_parent_graph_id: null,
      reference_parent_ids: [],
      reference_ids: [],
      child_ids: [],
      level: state.level,
      code: state.code,
      name: state.name,
      state_kind: state.state_kind,
      feature_key: state.feature_key,
      operator: state.operator,
      target_value: state.target_value,
      is_active: true,
      is_leaf: true,
      leaf_state_ids: [state.id],
      leaf_count: 1,
      path_ids: [state.id],
      metadata_json: state.metadata_json,
      reference_id: null,
      is_reference_instance: false,
    })),
  ],
  activity_nodes: [
    {
      id: 'activity_node:10',
      activity_node_id: 10,
      atomic_activity_id: null,
      parent_id: null,
      parent_graph_id: null,
      child_activity_node_ids: [],
      level: 2,
      code: 'VA_PREP',
      name: '准备虚拟活动',
      description: '',
      activity_type: 'virtual',
      activity_category: 'operation',
      solver_participation: false,
      is_active: true,
      path_ids: [10],
      metadata_json: { _network_editor_layout: { x: 520, y: 100 } },
    },
    {
      id: 'atomic_activity:20',
      activity_node_id: null,
      atomic_activity_id: 20,
      parent_id: null,
      parent_graph_id: null,
      parent_activity_node_ids: [10],
      level: 3,
      code: 'AA_FINISH',
      name: '完成原子活动',
      description: '',
      activity_type: 'executable',
      activity_category: 'operation',
      solver_participation: true,
      is_active: true,
      path_ids: [[10, 20]],
      metadata_json: { _network_editor_layout: { x: 520, y: 260 } },
    },
  ],
  bindings,
  edges: [
    {
      id: 'binding:100:STATE_TO_ACTIVITY',
      source_id: 'state_node:1',
      target_id: 'activity_node:10',
      type: 'STATE_TO_ACTIVITY',
      binding_id: 100,
      binding_role: 'context_input',
      source_kind: 'activity_state_binding',
      coverage_status: 'complete',
    },
    {
      id: 'binding:101:ACTIVITY_TO_STATE',
      source_id: 'atomic_activity:20',
      target_id: 'state_node:4',
      type: 'ACTIVITY_TO_STATE',
      binding_id: 101,
      binding_role: 'output',
      source_kind: 'activity_state_binding',
      coverage_status: 'complete',
    },
    {
      id: 'binding:102:ACTIVITY_TO_STATE',
      source_id: 'activity_node:10',
      target_id: 'state_node:4',
      type: 'ACTIVITY_TO_STATE',
      binding_id: 102,
      binding_role: 'declared_output',
      source_kind: 'activity_state_binding',
      coverage_status: 'complete',
    },
    ...extraAtomicInputBindings.map((binding) => ({
      id: `binding:${binding.id}:STATE_TO_ACTIVITY`,
      source_id: `state_node:${binding.state_node_id}`,
      target_id: 'atomic_activity:20',
      type: 'STATE_TO_ACTIVITY',
      binding_id: binding.id,
      binding_role: 'input',
      source_kind: 'activity_state_binding',
      coverage_status: 'complete',
    })),
  ],
  summary: {
    state_node_count: 9,
    state_instance_count: 9,
    state_reference_instance_count: 0,
    state_package_count: 2,
    atomic_state_count: 7,
    activity_node_count: 2,
    virtual_activity_count: 1,
    executable_activity_count: 1,
    edge_count: 9,
    coverage_gap_count: 0,
    partial_virtual_activity_count: 0,
    cross_level_binding_count: 2,
    blocking_count: 0,
  },
  validation_summary: {
    blocking_count: 0,
    warning_count: 0,
    issue_count: 0,
  },
}

function graphResponseForRequest(request: any) {
  const body = JSON.parse(request.postData() || '{}')
  if ((body.state_root_ids || []).some((id: any) => Number(id) === 4)) {
    return referencedStatePackageGraphResponse()
  }
  return graphResponse
}

function independentStateRootsGraphResponseForRequest(request: any) {
  const body = JSON.parse(request.postData() || '{}')
  const roots = new Set((body.state_root_ids || []).map((id: any) => Number(id)))
  if (roots.has(1) && roots.has(4)) return twoExpandedStateRootsGraphResponse()
  if (roots.has(4)) return stateDoneExpandedGraphResponse()
  return graphResponse
}

function stateDoneExpandedGraphResponse() {
  const state4 = graphResponse.state_nodes.find((node: any) => node.state_node_id === 4)
  return {
    ...graphResponse,
    state_nodes: [
      {
        ...state4,
        child_ids: [40],
        leaf_state_ids: [40],
        leaf_count: 1,
        metadata_json: { _network_editor_layout: { x: 80, y: 360 } },
      },
      {
        id: 'state_node:40',
        state_node_id: 40,
        parent_id: 4,
        primary_parent_graph_id: 'state_node:4',
        reference_parent_ids: [],
        reference_ids: [],
        child_ids: [],
        level: 2,
        code: 'STATE_DONE_LEAF',
        name: '完成子状态',
        state_kind: 'atomic',
        feature_key: 'done_flag',
        operator: 'eq',
        target_value: 'true',
        is_active: true,
        is_leaf: true,
        leaf_state_ids: [40],
        leaf_count: 1,
        path_ids: [4, 40],
        metadata_json: { _network_editor_layout: { x: 126, y: 500 } },
        reference_id: null,
        is_reference_instance: false,
      },
    ],
    summary: {
      ...graphResponse.summary,
      state_instance_count: 2,
    },
  }
}

function twoExpandedStateRootsGraphResponse() {
  const state1 = graphResponse.state_nodes.find((node: any) => node.state_node_id === 1)
  const state3 = graphResponse.state_nodes.find((node: any) => node.state_node_id === 3)
  const doneGraph = stateDoneExpandedGraphResponse()
  return {
    ...graphResponse,
    state_nodes: [
      state1,
      state3,
      ...doneGraph.state_nodes,
    ],
    summary: {
      ...graphResponse.summary,
      state_instance_count: 4,
    },
  }
}

function referencedStatePackageGraphResponse() {
  const state4 = graphResponse.state_nodes.find((node: any) => node.state_node_id === 4)
  const state1 = graphResponse.state_nodes.find((node: any) => node.state_node_id === 1)
  const state3 = graphResponse.state_nodes.find((node: any) => node.state_node_id === 3)
  return {
    ...graphResponse,
    state_nodes: [
      {
        ...state4,
        child_ids: [1],
        leaf_state_ids: [3],
        leaf_count: 1,
        metadata_json: { _network_editor_layout: { x: 80, y: 80 } },
      },
      {
        ...state1,
        id: 'state_node:1:ref:900',
        parent_id: 4,
        primary_parent_graph_id: 'state_node:4',
        reference_parent_ids: [4],
        reference_ids: [900],
        path_ids: [4, 1],
        metadata_json: { _network_editor_layout: { x: 126, y: 220 } },
        reference_id: 900,
        is_reference_instance: true,
        reference_parent_id: 4,
      },
      {
        ...state3,
        path_ids: [1, 3],
        metadata_json: { _network_editor_layout: { x: 164, y: 360 } },
      },
    ],
    summary: {
      ...graphResponse.summary,
      state_instance_count: 3,
      state_reference_instance_count: 1,
    },
  }
}

async function routeNetworkEditorFixture(page: any, options: {
  graphResponse?: any | ((request: any) => any)
  stateReferences?: any[]
} = {}) {
  await page.route(/\/(health|api\/v1\/)/, async (route: any, request: any) => {
    const url = request.url()
    const method = request.method()

    if (url.endsWith('/health')) {
      await route.fulfill({ status: 200, body: JSON.stringify({ status: 'ok', version: 'test' }) })
      return
    }

    if (url.endsWith('/api/v1/machine-types')) {
      await route.fulfill({ status: 200, body: JSON.stringify(machineTypes) })
      return
    }

    if (url.endsWith('/api/v1/machines')) {
      await route.fulfill({ status: 200, body: JSON.stringify([]) })
      return
    }

    if (url.includes('/api/v1/resources')) {
      await route.fulfill({ status: 200, body: JSON.stringify([]) })
      return
    }

    if (url.endsWith('/api/v1/features')) {
      await route.fulfill({ status: 200, body: JSON.stringify([]) })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/feature-defs')) {
      await route.fulfill({ status: 200, body: JSON.stringify(stateFeatureDefs) })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/state-nodes')) {
      await route.fulfill({ status: 200, body: JSON.stringify(stateNodes) })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/activity-nodes')) {
      await route.fulfill({ status: 200, body: JSON.stringify(activityNodes) })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/atomic-activities')) {
      await route.fulfill({ status: 200, body: JSON.stringify(atomicActivities) })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/state-node-references')) {
      await route.fulfill({ status: 200, body: JSON.stringify(options.stateReferences || []) })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/activity-state-bindings')) {
      await route.fulfill({ status: 200, body: JSON.stringify(bindings) })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/op-rules')) {
      await route.fulfill({
        status: 200,
        body: JSON.stringify([
          {
            id: 900,
            machine_type_id: 1,
            atomic_activity_id: 20,
            activity_node_id: null,
            code: 'RULE_FINISH',
            name: '完成规则',
            duration_min: 30,
            is_active: true,
            is_repair: false,
          },
        ]),
      })
      return
    }

    if (url.endsWith('/api/v1/activity-nodes/10/atomic-activity-refs')) {
      await route.fulfill({
        status: 200,
        body: JSON.stringify([
          {
            id: 700,
            activity_node_id: 10,
            atomic_activity_id: 20,
            sort_order: 1,
            is_active: true,
            metadata_json: null,
          },
        ]),
      })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/network-editor/graph') && method === 'POST') {
      const response = typeof options.graphResponse === 'function'
        ? options.graphResponse(request)
        : (options.graphResponse || graphResponseForRequest(request))
      await route.fulfill({ status: 200, body: JSON.stringify(response) })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/network-editor/validate') && method === 'POST') {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          status: 'blocked',
          summary: {
            modeling_issue_count: 0,
            solver_ready_issue_count: 1,
            blocking_count: 1,
            warning_count: 0,
            issue_count: 1,
          },
          modeling_issues: [],
          solver_ready_issues: [
            {
              id: 'solver:BROKEN_CHAIN:atomic-detail-only',
              code: 'BROKEN_CHAIN',
              severity: 'error',
              category: 'layered_health',
              message: 'Missing provider chain',
              related_state_ids: [],
              related_activity_ids: [],
              details: {
                node_type: 'atomic_activity',
                node_id: 20,
                feature_key: 'ready_flag',
                operator: 'eq',
                target_value: 'true',
              },
              suggested_action: 'Fix provider chain',
            },
          ],
        }),
      })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/network-editor/impact') && method === 'POST') {
      await route.fulfill({
        status: 404,
        body: JSON.stringify({
          code: 'HTTP_404',
          detail: '操作失败（HTTP_404）',
        }),
      })
      return
    }

    await route.fulfill({ status: 200, body: JSON.stringify({}) })
  })
}

async function openNetworkEditorFixture(page: any, options: {
  graphResponse?: any | ((request: any) => any)
  stateReferences?: any[]
} | null = null) {
  if (options) {
    await page.unroute(/\/(health|api\/v1\/)/)
    await routeNetworkEditorFixture(page, options)
  }
  await page.getByTestId('network-editor-machine-type-select').locator('.el-select__wrapper').click()
  await page.locator('.el-select-dropdown:visible .el-select-dropdown__item', { hasText: 'CNC Lathe (LATHE)' }).click()
  await expect(page.getByTestId('network-editor-canvas')).toBeVisible()
  await expect(page.getByTestId('network-editor-x6-canvas')).toBeVisible()
  await expect(page.locator('.state-column')).toHaveCount(0)
  await expect(page.locator('.activity-column')).toHaveCount(0)
  await expect(page.getByTestId('network-editor-state-node-1')).toBeVisible()
  await expect(page.getByTestId('network-editor-state-node-3')).toBeVisible()
  await expect(page.getByTestId('network-editor-activity-node-activity_node:10')).toBeVisible()
}

async function dragLocatorBy(page: any, locator: any, dx: number, dy: number) {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      await expect(locator).toBeVisible()
      await locator.scrollIntoViewIfNeeded()
      const testId = await locator.getAttribute('data-testid')
      const isContainerMove = String(testId || '').includes('container-move')
      const className = await locator.evaluate((element: HTMLElement) => element.className || '')
      const isLayoutHandle = String(className).includes('layout-handle')
      const dragTarget = (isContainerMove || isLayoutHandle) ? locator.locator('xpath=ancestor::*[@data-cell-id][1]') : locator
      const box = await dragTarget.boundingBox() || await locatorClientRect(dragTarget, { preferOwnRect: true })
      const startX = box.x + box.width / 2
      const startY = box.y + box.height / 2
      await dragTarget.hover({ position: { x: box.width / 2, y: box.height / 2 } })
      await page.waitForTimeout(30)
      await page.mouse.down({ button: 'left' })
      await page.waitForTimeout(30)
      await page.mouse.move(startX + dx, startY + dy, { steps: 10 })
      await page.mouse.up({ button: 'left' })
      return
    } catch (error: any) {
      if (attempt === 2 || !String(error?.message || '').includes('not attached')) throw error
      await page.waitForTimeout(100)
    }
  }
}

async function dragRightPortToLeftPort(page: any, sourceLocator: any, targetLocator: any) {
  const sourcePort = sourceLocator.locator('.semantic-port.port-right')
  const targetPort = targetLocator.locator('.semantic-port.port-left')
  await targetPort.scrollIntoViewIfNeeded()
  await sourcePort.scrollIntoViewIfNeeded()
  const sourceBox = await locatorClientRect(sourcePort, { preferOwnRect: true })
  const targetBox = await locatorClientRect(targetPort, { preferOwnRect: true })
  const startX = sourceBox.x + sourceBox.width / 2
  const startY = sourceBox.y + sourceBox.height / 2
  const endX = targetBox.x + targetBox.width / 2
  const endY = targetBox.y + targetBox.height / 2
  await page.mouse.move(startX, startY)
  await page.waitForTimeout(30)
  await page.mouse.down({ button: 'left' })
  await page.waitForTimeout(30)
  await page.mouse.move(endX, endY, { steps: 12 })
  await page.mouse.up({ button: 'left' })
}

async function readCanvasPosition(locator: any) {
  const box = await locatorClientRect(locator)
  const canvasBox = await locatorClientRect(locator.page().getByTestId('network-editor-x6-canvas'))
  return {
    x: box.x - canvasBox.x,
    y: box.y - canvasBox.y,
  }
}

async function locatorClientRect(locator: any, options: { preferOwnRect?: boolean } = {}) {
  await expect(locator).toBeVisible()
  let box = { x: 0, y: 0, width: 0, height: 0 }
  for (let attempt = 0; attempt < 10; attempt += 1) {
    box = await locator.evaluate((element: HTMLElement, preferOwnRect: boolean) => {
      const ownRect = element.getBoundingClientRect()
      const target = preferOwnRect && ownRect.width > 0 && ownRect.height > 0
        ? element
        : element.closest('[data-cell-id]') || element.closest('.x6-node') || element
      const rect = target.getBoundingClientRect()
      return {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
      }
    }, !!options.preferOwnRect)
    if (box.width > 0 && box.height > 0) break
    await locator.page().waitForTimeout(50)
  }
  expect(box.width).toBeGreaterThan(0)
  expect(box.height).toBeGreaterThan(0)
  return box
}

async function clickAndWaitForGraphReload(page: any, action: () => Promise<void>) {
  await Promise.all([
    page.waitForResponse((response: any) =>
      response.url().includes('/api/v1/machine-types/1/network-editor/graph') &&
      response.request().method() === 'POST',
    ),
    action(),
  ])
}

async function chooseStateKind(drawer: any, kind: 'aggregate' | 'atomic') {
  const index = kind === 'aggregate' ? 0 : 1
  await drawer.getByTestId('network-editor-state-kind-segmented').locator('.el-segmented__item').nth(index).click()
}

async function fillAtomicStateFact(page: any, drawer: any, featureKey: string, targetValue = 'true') {
  await chooseElSelectOption(page, drawer.getByTestId('network-editor-state-feature'), featureKey)
  await chooseElSelectOption(page, drawer.getByTestId('network-editor-state-target-value'), targetValue)
}

async function chooseElSelectOption(page: any, selectRoot: any, text: string) {
  const input = selectRoot.locator('input').last()
  await input.click({ force: true })
  await input.fill(text)
  const listboxId = await input.getAttribute('aria-controls')
  const option = listboxId
    ? page.locator(`#${listboxId} .el-select-dropdown__item`, { hasText: text }).last()
    : page.locator('.el-select-dropdown:visible .el-select-dropdown__item', { hasText: text }).last()
  await expect(option).toBeVisible()
  await option.click({ force: true })
  await expect(selectRoot).toContainText(text)
  await page.keyboard.press('Escape')
}

async function expectElSelectHasOption(page: any, selectRoot: any, text: string) {
  const input = selectRoot.locator('input').last()
  await input.click({ force: true })
  const listboxId = await input.getAttribute('aria-controls')
  const option = listboxId
    ? page.locator(`#${listboxId} .el-select-dropdown__item`, { hasText: text }).last()
    : page.locator('.el-select-dropdown:visible .el-select-dropdown__item', { hasText: text }).last()
  await expect(option).toBeVisible()
  await page.keyboard.press('Escape')
}

test.describe('Network Editor — edit session and semantic labels', () => {
  test.beforeEach(async ({ page }) => {
    await routeNetworkEditorFixture(page)
    await page.goto('/')
    await page.waitForSelector('.el-header', { timeout: 10000 })
    await page.locator('.el-tabs__item:has-text("网络编辑器")').click()
    await expect(page.getByTestId('network-editor')).toBeVisible()
  })

  test('keeps preview read-only until entering edit and renders semantic edge labels', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await expect(page.getByTestId('network-editor-toolbar').getByText('预览模式', { exact: true })).toBeVisible()
    await expect(page.getByTestId('network-editor-create-state')).toBeDisabled()
    await expect(page.getByTestId('network-editor-state-node-1').getByText('添加状态', { exact: true })).toBeHidden()
    await expect(page.getByTestId('network-editor-zoom-reset')).toContainText('100%')
    await page.getByTestId('network-editor-zoom-in').click()
    await expect(page.getByTestId('network-editor-zoom-reset')).toContainText('110%')
    await page.getByTestId('network-editor-zoom-reset').click()
    await expect(page.getByTestId('network-editor-zoom-reset')).toContainText('100%')

    const x6Canvas = page.getByTestId('network-editor-x6-canvas')
    await expect(x6Canvas.getByText('状态包上下文 / 跨层级')).toBeVisible()
    await expect(x6Canvas.getByText('产出 / 跨层级')).toBeVisible()
    const aggregateInputLabel = x6Canvas.getByText('6 个输入')
    await expect(aggregateInputLabel).toBeVisible()

    await page.getByTestId('network-editor-enter-edit').click()
    await expect(page.getByTestId('network-editor-toolbar').getByText('编辑模式', { exact: true })).toBeVisible()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeVisible()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeDisabled()
    await expect(page.getByTestId('network-editor-create-state')).toBeEnabled()
    await expect(page.getByTestId('network-editor-state-node-1').getByText('添加状态', { exact: true })).toBeVisible()
  })

  test('keeps a pending edge after drag prefill and turns it into a draft edge from the form', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeVisible()

    const sourceState = page.getByTestId('network-editor-state-node-3')
    const targetActivity = page.getByTestId('network-editor-activity-node-activity_node:10')
    await expect(sourceState.locator('.semantic-port.port-left')).toHaveText('输入')
    await expect(sourceState.locator('.semantic-port.port-right')).toHaveText('产出')

    await dragRightPortToLeftPort(page, sourceState, targetActivity)
    const dialog = page.locator('.el-message-box')
    await expect(dialog).toBeVisible()
    await expect(page.locator('[data-cell-id^="pending-binding-preview"]')).toHaveCount(1)
    await dialog.locator('.el-button').first().click()
    await expect(dialog).toBeHidden()

    await expect(page.locator('[data-cell-id^="pending-binding-preview"]')).toHaveCount(1)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeDisabled()
    await expect(page.getByTestId('network-editor-create-binding')).toBeEnabled()

    await page.getByTestId('network-editor-create-binding').click()
    await expect(page.locator('[data-cell-id^="pending-binding-preview"]')).toHaveCount(0)
    await expect(page.locator('[data-cell-id^="draft-binding"]')).toHaveCount(1)

    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()
    await expect(page.locator('.draft-change-list')).toContainText('context_input')
  })

  test('keeps a draft edge after confirming a dropped binding', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeVisible()

    const sourceState = page.getByTestId('network-editor-state-node-3')
    const targetActivity = page.getByTestId('network-editor-activity-node-activity_node:10')
    await dragRightPortToLeftPort(page, sourceState, targetActivity)
    const dialog = page.locator('.el-message-box')
    await expect(dialog).toBeVisible()
    await expect(page.locator('[data-cell-id^="pending-binding-preview"]')).toHaveCount(1)
    await dialog.locator('.el-button--primary').click()
    await expect(dialog).toBeHidden()

    await expect(page.locator('[data-cell-id^="pending-binding-preview"]')).toHaveCount(0)
    await expect(page.locator('[data-cell-id^="draft-binding"]')).toHaveCount(1)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()
    await expect(page.locator('.draft-change-list')).toContainText('context_input')
  })

  test('allows preview expand and collapse without exposing state-package write actions', async ({ page }) => {
    await openNetworkEditorFixture(page)
    const stateNode = page.getByTestId('network-editor-state-node-1')
    const virtualActivity = page.getByTestId('network-editor-activity-node-activity_node:10')

    await expect(stateNode.getByText('添加状态', { exact: true })).toBeHidden()
    await expect(stateNode.getByText('展开', { exact: true })).toBeVisible()
    await stateNode.getByText('展开', { exact: true }).click()
    await expect(stateNode.getByText('折叠', { exact: true })).toBeVisible()
    const statePackageContainer = page.getByTestId('network-editor-state-package-container-1')
    await expect(statePackageContainer).toBeVisible()
    await expect(statePackageContainer).toContainText('准备状态包')
    await expect(statePackageContainer).toContainText('1 个状态')
    await expect(statePackageContainer).not.toContainText('完成原子活动')
    await expect(page.getByTestId('network-editor-toolbar').getByText('预览模式', { exact: true })).toBeVisible()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeHidden()

    await expect(virtualActivity.getByText('展开', { exact: true })).toBeVisible()
    await virtualActivity.getByText('展开', { exact: true }).click()
    await expect(virtualActivity.getByText('折叠', { exact: true })).toBeVisible()
    const virtualContainer = page.getByTestId('network-editor-virtual-activity-container-activity_node:10')
    await expect(virtualContainer).toBeVisible()
    await expect(virtualContainer).toContainText('准备虚拟活动')
    await expect(virtualContainer).not.toContainText('包内原子状态')
    await expect(virtualContainer).not.toContainText('跨层级目标状态')
  })

  test('preserves independent state root expansion while toggling another root', async ({ page }) => {
    await openNetworkEditorFixture(page, {
      graphResponse: independentStateRootsGraphResponseForRequest,
    })

    const stateOne = page.getByTestId('network-editor-state-node-1')
    const stateDone = page.getByTestId('network-editor-state-node-4')
    const stateOneContainer = page.getByTestId('network-editor-state-package-container-1')
    const stateDoneContainer = page.getByTestId('network-editor-state-package-container-4')

    await stateOne.locator('[data-action="toggle"]').click()
    await expect(stateOneContainer).toBeVisible()
    await expect(page.getByTestId('network-editor-state-node-3')).toBeVisible()

    await stateDone.locator('[data-action="toggle"]').click()
    await expect(stateOneContainer).toBeVisible()
    await expect(page.getByTestId('network-editor-state-node-3')).toBeVisible()
    await expect(stateDoneContainer).toBeVisible()
    await expect(page.getByTestId('network-editor-state-node-40')).toBeVisible()

    await stateDone.locator('[data-action="toggle"]').click()
    await expect(stateDoneContainer).toBeHidden()
    await expect(stateOneContainer).toBeVisible()
    await expect(page.getByTestId('network-editor-state-node-3')).toBeVisible()

    await stateDone.locator('[data-action="toggle"]').click()
    await expect(stateDoneContainer).toBeVisible()
    await stateOne.locator('[data-action="toggle"]').click()
    await expect(stateOneContainer).toBeHidden()
    await expect(stateDoneContainer).toBeVisible()
    await expect(page.getByTestId('network-editor-state-node-40')).toBeVisible()
  })

  test('opens virtual activity focus canvas in preview without creating drafts', async ({ page }) => {
    await openNetworkEditorFixture(page)
    const virtualActivity = page.getByTestId('network-editor-activity-node-activity_node:10')

    await expect(virtualActivity.getByText('专注', { exact: true })).toBeVisible()
    await virtualActivity.getByText('专注', { exact: true }).click()

    const focusStrip = page.getByTestId('network-editor-activity-focus-strip')
    await expect(focusStrip).toBeVisible()
    await expect(focusStrip).toContainText('专注画布')
    await expect(focusStrip).toContainText('准备虚拟活动')
    await expect(focusStrip).toContainText('上下文')
    await expect(focusStrip).toContainText('准备状态包')
    await expect(focusStrip).toContainText('输出')
    await expect(focusStrip).toContainText('跨层级目标状态')
    await expect(focusStrip).toContainText('实现 1/1')
    const focusedVirtualContainer = page.getByTestId('network-editor-virtual-activity-container-activity_node:10')
    await expect(focusedVirtualContainer).toBeVisible()
    await expect(focusedVirtualContainer).toContainText('准备虚拟活动')
    await expect(focusedVirtualContainer).not.toContainText('准备状态包')
    await expect(focusedVirtualContainer).not.toContainText('跨层级目标状态')
    await expect(page.getByTestId('network-editor-toolbar').getByText('预览模式', { exact: true })).toBeVisible()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeHidden()

    await focusStrip.getByText('退出', { exact: true }).click()
    await expect(focusStrip).toBeHidden()
    await expect(page.getByTestId('network-editor-toolbar').getByText('预览模式', { exact: true })).toBeVisible()
  })

  test('locates validation issues that only include detail node metadata', async ({ page }) => {
    await openNetworkEditorFixture(page)

    await Promise.all([
      page.waitForResponse((response: any) =>
        response.url().includes('/api/v1/machine-types/1/network-editor/validate') &&
        response.request().method() === 'POST',
      ),
      page.waitForResponse((response: any) =>
        response.url().includes('/api/v1/machine-types/1/network-editor/graph') &&
        response.request().method() === 'POST',
      ),
      page.getByTestId('network-editor-validate').click(),
    ])

    const solverIssueTable = page.getByTestId('network-editor-solver-issues-table')
    await expect(solverIssueTable).toContainText('求解链路断裂')
    await expect(solverIssueTable).toContainText('完成原子活动')
    await solverIssueTable.getByTestId('network-editor-solver-issue-locate').click()
    await expect(page.getByTestId('network-editor-activity-node-atomic_activity:20')).toHaveClass(/selected/)
  })

  test('cancels edit session and restores submitted layout without committing drafts', async ({ page }) => {
    await openNetworkEditorFixture(page)
    const stateNode = page.getByTestId('network-editor-state-node-1')
    const submittedPosition = await readCanvasPosition(stateNode)

    await page.getByTestId('network-editor-enter-edit').click()
    await expect(page.getByTestId('network-editor-toolbar').getByText('编辑模式', { exact: true })).toBeVisible()
    await dragLocatorBy(page, stateNode.locator('.layout-handle'), 48, 16)

    const draftedPosition = await readCanvasPosition(stateNode)
    expect(draftedPosition.x).toBeGreaterThan(submittedPosition.x + 20)
    expect(draftedPosition.y).toBeGreaterThan(submittedPosition.y + 8)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()
    await expect(page.locator('.draft-change-list')).toContainText('调整状态位置')

    await page.getByTestId('network-editor-cancel-edit').click()
    const dialog = page.locator('.el-message-box')
    await expect(dialog).toContainText('取消编辑会丢弃本次草稿')
    await clickAndWaitForGraphReload(page, () => dialog.getByRole('button', { name: '丢弃草稿' }).click())

    await expect(page.getByTestId('network-editor-toolbar').getByText('预览模式', { exact: true })).toBeVisible()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeHidden()
    const restoredPosition = await readCanvasPosition(stateNode)
    expect(Math.abs(restoredPosition.x - submittedPosition.x)).toBeLessThan(2)
    expect(Math.abs(restoredPosition.y - submittedPosition.y)).toBeLessThan(2)
  })

  test('queues drawer saves as drafts and commits only from unified submit', async ({ page }) => {
    const commitRequests: any[] = []
    page.on('request', (request) => {
      if (request.url().endsWith('/api/v1/machine-types/1/network-editor/commit')) {
        commitRequests.push(request)
      }
    })
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()
    await page.getByTestId('network-editor-create-state').click()

    const drawer = page.getByTestId('network-editor-state-drawer')
    await expect(drawer).toBeVisible()
    await chooseStateKind(drawer, 'aggregate')
    await drawer.locator('.el-form-item').nth(1).locator('input').fill('一次性提交状态')
    await drawer.getByTestId('network-editor-state-drawer-save').click()

    await expect(drawer).toBeHidden()
    await expect(page.locator('.draft-change-list')).toContainText('新建状态：一次性提交状态')
    const draftedStateNode = page.getByTestId('network-editor-state-node-draft-state:draft-1')
    await expect(draftedStateNode).toBeVisible()
    await page.getByTestId('network-editor-create-state').click()
    await expect(drawer).toBeVisible()
    await chooseStateKind(drawer, 'aggregate')
    await drawer.locator('.el-form-item').nth(1).locator('input').fill('Draft child state')
    await drawer.getByTestId('network-editor-state-drawer-save').click()

    await expect(drawer).toBeHidden()
    await expect(page.locator('.draft-change-list')).toContainText('Draft child state')
    const draftedChildStateNode = page.getByTestId('network-editor-state-node-draft-state:draft-2')
    await expect(draftedChildStateNode).toBeVisible()
    await expect(draftedChildStateNode).toContainText('Draft child state')
    await page.getByTestId('network-editor-create-state').click()
    await expect(drawer).toBeVisible()
    await drawer.locator('.el-form-item').nth(1).locator('input').fill('Draft nested state')
    await fillAtomicStateFact(page, drawer, 'draft_nested_state')
    await drawer.getByTestId('network-editor-state-drawer-save').click()

    await expect(drawer).toBeHidden()
    await expect(page.locator('.draft-change-list')).toContainText('Draft nested state')
    const draftedNestedStateNode = page.getByTestId('network-editor-state-node-draft-state:draft-3')
    await expect(draftedNestedStateNode).toBeVisible()
    await expect(draftedNestedStateNode).toContainText('Draft nested state')

    const draftedStateContainer = page.getByTestId('network-editor-state-package-container-draft-state:draft-1')
    await draftedStateNode.locator('[data-action="toggle"]').click()
    await page.waitForTimeout(100)
    if (await draftedStateContainer.count() === 0) {
      await draftedStateNode.locator('[data-action="toggle"]').click()
    }
    await expect(draftedStateContainer).toBeVisible()
    const parentBox = await locatorClientRect(draftedStateContainer)
    const childPackageBox = await locatorClientRect(draftedChildStateNode)
    const nestedBox = await locatorClientRect(draftedNestedStateNode)
    expect(childPackageBox.x).toBeGreaterThanOrEqual(parentBox.x - 2)
    expect(childPackageBox.y).toBeGreaterThanOrEqual(parentBox.y - 2)
    expect(childPackageBox.x + childPackageBox.width).toBeLessThanOrEqual(parentBox.x + parentBox.width + 2)
    expect(nestedBox.x).toBeGreaterThanOrEqual(parentBox.x - 2)
    expect(nestedBox.y).toBeGreaterThanOrEqual(parentBox.y - 2)
    expect(nestedBox.x + nestedBox.width).toBeLessThanOrEqual(parentBox.x + parentBox.width + 2)

    await page.getByTestId('network-editor-state-node-draft-state:draft-1').locator('[data-action="toggle"]').click()
    await expect(draftedStateContainer).toBeHidden()
    await expect(draftedStateNode).toContainText('一次性提交状态')
    await expect(draftedChildStateNode).toBeHidden()
    await expect(draftedNestedStateNode).toBeHidden()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()
    expect(commitRequests).toHaveLength(0)

    const [commitRequest] = await Promise.all([
      page.waitForRequest((request: any) =>
        request.url().endsWith('/api/v1/machine-types/1/network-editor/commit') &&
        request.method() === 'POST',
      ),
      page.getByTestId('network-editor-submit-draft').click(),
    ])
    const payload = JSON.parse(commitRequest.postData() || '{}')
    expect(payload.allow_warnings).toBe(false)
    expect(payload.changes).toHaveLength(3)
    expect(payload.changes[0]).toMatchObject({
      entity_type: 'state_node',
      operation: 'create',
      payload: { name: '一次性提交状态', state_kind: 'aggregate' },
    })
    expect(payload.changes[1]).toMatchObject({
      entity_type: 'state_node',
      operation: 'create',
      payload: {
        name: 'Draft child state',
        parent_id: { _draft_ref: 'draft-1' },
        state_kind: 'aggregate',
      },
    })
    expect(payload.changes[2]).toMatchObject({
      entity_type: 'state_node',
      operation: 'create',
      payload: {
        name: 'Draft nested state',
        parent_id: { _draft_ref: 'draft-2' },
        state_kind: 'atomic',
        feature_key: 'draft_nested_state',
        target_value: 'true',
      },
    })
    expect(commitRequests).toHaveLength(1)
    await expect(page.getByTestId('network-editor-toolbar').getByText('预览模式', { exact: true })).toBeVisible()
  })

  test('offers draft states to atomic activities and allows empty input/output states', async ({ page }) => {
    const impactPayloads: any[] = []
    page.on('request', (request) => {
      if (
        request.url().endsWith('/api/v1/machine-types/1/network-editor/impact') &&
        request.method() === 'POST'
      ) {
        impactPayloads.push(JSON.parse(request.postData() || '{}'))
      }
    })
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()

    await page.getByTestId('network-editor-create-state').click()
    const stateDrawer = page.getByTestId('network-editor-state-drawer')
    await expect(stateDrawer).toBeVisible()
    await stateDrawer.locator('.el-form-item').nth(1).locator('input').fill('Draft atomic option')
    await fillAtomicStateFact(page, stateDrawer, 'draft_atomic_option')
    await stateDrawer.getByTestId('network-editor-state-drawer-save').click()
    await expect(stateDrawer).toBeHidden()
    await expect(page.getByTestId('network-editor-state-node-draft-state:draft-1')).toContainText('Draft atomic option')

    await page.getByTestId('network-editor-create-atomic').click()
    const atomicDrawer = page.getByTestId('network-editor-atomic-drawer')
    await expect(atomicDrawer).toBeVisible()
    await expectElSelectHasOption(page, atomicDrawer.getByTestId('network-editor-atomic-input-states'), 'Draft atomic option')
    await expectElSelectHasOption(page, atomicDrawer.getByTestId('network-editor-atomic-output-states'), 'Draft atomic option')

    await atomicDrawer.locator('.el-form-item').nth(1).locator('input').fill('Atomic without boundary states')
    await atomicDrawer.getByTestId('network-editor-atomic-drawer-save').click()
    await expect(atomicDrawer).toBeHidden()
    await expect(page.locator('.draft-change-list')).toContainText('Atomic without boundary states')
    const draftAtomicActivity = page.getByTestId('network-editor-activity-node-atomic_activity:draft-atomic-activity:draft-2')
    await expect(draftAtomicActivity).toBeVisible()
    await dragRightPortToLeftPort(page, draftAtomicActivity, page.getByTestId('network-editor-state-node-draft-state:draft-1'))
    await page.waitForTimeout(impactDebounceBufferMs)
    expect(JSON.stringify(impactPayloads)).not.toContain('draft-state:')
    expect(JSON.stringify(impactPayloads)).not.toContain('draft-atomic-activity:')

    await page.getByTestId('network-editor-create-atomic').click()
    await expect(atomicDrawer).toBeVisible()
    await atomicDrawer.locator('.el-form-item').nth(1).locator('input').fill('Atomic using draft states')
    await chooseElSelectOption(page, atomicDrawer.getByTestId('network-editor-atomic-input-states'), 'Draft atomic option')
    await chooseElSelectOption(page, atomicDrawer.getByTestId('network-editor-atomic-output-states'), 'Draft atomic option')
    await atomicDrawer.getByTestId('network-editor-atomic-drawer-save').click()
    await expect(atomicDrawer).toBeHidden()
    await expect(page.locator('.draft-change-list')).toContainText('Atomic using draft states')

    const [commitRequest] = await Promise.all([
      page.waitForRequest((request: any) =>
        request.url().endsWith('/api/v1/machine-types/1/network-editor/commit') &&
        request.method() === 'POST',
      ),
      page.getByTestId('network-editor-submit-draft').click(),
    ])
    const payload = JSON.parse(commitRequest.postData() || '{}')
    const bindingChanges = payload.changes.filter((change: any) => change.entity_type === 'activity_state_binding')
    expect(bindingChanges).toHaveLength(2)
    expect(bindingChanges.every((change: any) =>
      change.payload.state_node_id?._draft_ref === 'draft-1',
    )).toBe(true)
    expect(payload.changes.some((change: any) =>
      change.entity_type === 'atomic_activity' &&
      change.payload.name === 'Atomic without boundary states',
    )).toBe(true)
  })

  test('renders draft virtual activities and folds draft child activities locally', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()

    await page.getByTestId('network-editor-create-activity').click()
    const activityDrawer = page.getByTestId('network-editor-activity-drawer')
    await expect(activityDrawer).toBeVisible()
    await activityDrawer.locator('.el-form-item').nth(1).locator('input').fill('Draft activity parent')
    await activityDrawer.getByTestId('network-editor-activity-drawer-save').click()

    await expect(activityDrawer).toBeHidden()
    await expect(page.locator('.draft-change-list')).toContainText('Draft activity parent')
    const draftedParentActivity = page.getByTestId('network-editor-activity-node-activity_node:draft-activity:draft-1')
    await expect(draftedParentActivity).toBeVisible()
    await expect(draftedParentActivity).toContainText('Draft activity parent')

    await page.getByTestId('network-editor-create-activity').click()
    await expect(activityDrawer).toBeVisible()
    await expect(activityDrawer).toContainText('Draft activity parent')
    await activityDrawer.locator('.el-form-item').nth(1).locator('input').fill('Draft child activity')
    await activityDrawer.getByTestId('network-editor-activity-drawer-save').click()

    await expect(activityDrawer).toBeHidden()
    await expect(page.locator('.draft-change-list')).toContainText('Draft child activity')
    const draftedChildActivity = page.getByTestId('network-editor-activity-node-activity_node:draft-activity:draft-2')
    await expect(draftedChildActivity).toBeVisible()
    await expect(draftedChildActivity).toContainText('Draft child activity')

    await page.getByTestId('network-editor-create-atomic').click()
    const atomicDrawer = page.getByTestId('network-editor-atomic-drawer')
    await expect(atomicDrawer).toBeVisible()
    await atomicDrawer.locator('.el-form-item').nth(1).locator('input').fill('Draft child atomic')
    await atomicDrawer.getByTestId('network-editor-atomic-drawer-save').click()

    await expect(atomicDrawer).toBeHidden()
    await expect(page.locator('.draft-change-list')).toContainText('Draft child atomic')
    await expect(page.locator('.resource-section').nth(1)).toContainText('Draft child atomic')
    const draftedAtomicActivity = page.getByTestId('network-editor-activity-node-atomic_activity:draft-atomic-activity:draft-3')
    await expect(draftedAtomicActivity).toBeVisible()
    await expect(draftedAtomicActivity).toContainText('Draft child atomic')

    await draftedParentActivity.locator('[data-action="toggle"]').click()
    const draftedActivityContainer = page.getByTestId('network-editor-virtual-activity-container-activity_node:draft-activity:draft-1')
    const draftedChildActivityContainer = page.getByTestId('network-editor-virtual-activity-container-activity_node:draft-activity:draft-2')
    await expect(draftedActivityContainer).toBeVisible()
    await expect(draftedChildActivityContainer).toBeVisible()
    const parentBox = await locatorClientRect(draftedActivityContainer)
    const childContainerBox = await locatorClientRect(draftedChildActivityContainer)
    const childBox = await locatorClientRect(draftedChildActivity)
    const atomicBox = await locatorClientRect(draftedAtomicActivity)
    expect(childContainerBox.x).toBeGreaterThanOrEqual(parentBox.x - 2)
    expect(childContainerBox.y).toBeGreaterThanOrEqual(parentBox.y - 2)
    expect(childContainerBox.x + childContainerBox.width).toBeLessThanOrEqual(parentBox.x + parentBox.width + 2)
    expect(childBox.x).toBeGreaterThanOrEqual(parentBox.x - 2)
    expect(childBox.y).toBeGreaterThanOrEqual(parentBox.y - 2)
    expect(childBox.x + childBox.width).toBeLessThanOrEqual(parentBox.x + parentBox.width + 2)
    expect(atomicBox.x).toBeGreaterThanOrEqual(childContainerBox.x - 2)
    expect(atomicBox.y).toBeGreaterThanOrEqual(childContainerBox.y - 2)
    expect(atomicBox.x + atomicBox.width).toBeLessThanOrEqual(childContainerBox.x + childContainerBox.width + 2)

    await draftedChildActivity.locator('[data-action="toggle"]').click()
    await expect(draftedActivityContainer).toBeVisible()
    await expect(draftedChildActivity).toBeVisible()
    await expect(draftedChildActivityContainer).toBeHidden()
    await expect(draftedAtomicActivity).toBeHidden()

    await draftedChildActivity.locator('[data-action="toggle"]').click()
    await expect(draftedChildActivityContainer).toBeVisible()
    await expect(draftedAtomicActivity).toBeVisible()

    await draftedParentActivity.locator('[data-action="toggle"]').click()
    await expect(draftedActivityContainer).toBeHidden()
    await expect(draftedParentActivity).toBeVisible()
    await expect(draftedChildActivity).toBeHidden()
    await expect(draftedAtomicActivity).toBeHidden()

    const [commitRequest] = await Promise.all([
      page.waitForRequest((request: any) =>
        request.url().endsWith('/api/v1/machine-types/1/network-editor/commit') &&
        request.method() === 'POST',
      ),
      page.getByTestId('network-editor-submit-draft').click(),
    ])
    const payload = JSON.parse(commitRequest.postData() || '{}')
    expect(payload.changes).toHaveLength(3)
    expect(payload.changes[0]).toMatchObject({
      entity_type: 'activity_node',
      operation: 'create',
      payload: { name: 'Draft activity parent', parent_id: null },
    })
    expect(payload.changes[1]).toMatchObject({
      entity_type: 'activity_node',
      operation: 'create',
      payload: {
        name: 'Draft child activity',
        parent_id: { _draft_ref: 'draft-1' },
      },
    })
    expect(payload.changes[2]).toMatchObject({
      entity_type: 'atomic_activity',
      operation: 'create',
      payload: {
        name: 'Draft child atomic',
        package_id: { _draft_ref: 'draft-2' },
      },
    })
  })

  test('renders nested containers when adding a child under a referenced state package', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()

    const outerStateNode = page.getByTestId('network-editor-state-node-4')
    await outerStateNode.locator('[data-action="toggle"]').click()

    const outerContainer = page.getByTestId('network-editor-state-package-container-4')
    const referencedPackageContainer = page.getByTestId('network-editor-state-package-container-1')
    const referencedPackageNode = page.getByTestId('network-editor-state-node-1')
    await expect(outerContainer).toBeVisible()
    await expect(referencedPackageContainer).toBeVisible()
    await expect(referencedPackageNode).toContainText('准备状态包')

    await referencedPackageNode.locator('[data-action="create"]').click()
    const drawer = page.getByTestId('network-editor-state-drawer')
    await expect(drawer).toBeVisible()
    await drawer.locator('.el-form-item').nth(1).locator('input').fill('引用包内新增状态')
    await fillAtomicStateFact(page, drawer, 'referenced_package_draft_state')
    await drawer.getByTestId('network-editor-state-drawer-save').click()

    const draftedStateNode = page.getByTestId('network-editor-state-node-draft-state:draft-1')
    await expect(draftedStateNode).toBeVisible()
    await expect(draftedStateNode).toContainText('引用包内新增状态')

    const outerBox = await locatorClientRect(outerContainer)
    const innerBox = await locatorClientRect(referencedPackageContainer)
    const childBox = await locatorClientRect(draftedStateNode)
    expect(innerBox.x).toBeGreaterThanOrEqual(outerBox.x - 2)
    expect(innerBox.y).toBeGreaterThanOrEqual(outerBox.y - 2)
    expect(innerBox.x + innerBox.width).toBeLessThanOrEqual(outerBox.x + outerBox.width + 2)
    expect(childBox.x).toBeGreaterThanOrEqual(innerBox.x - 2)
    expect(childBox.y).toBeGreaterThanOrEqual(innerBox.y - 2)
    expect(childBox.x + childBox.width).toBeLessThanOrEqual(innerBox.x + innerBox.width + 2)

    await referencedPackageNode.locator('[data-action="toggle"]').click()
    await expect(outerContainer).toBeVisible()
    await expect(referencedPackageContainer).toBeHidden()
    await expect(referencedPackageNode).toBeVisible()
    await expect(draftedStateNode).toBeHidden()

    await referencedPackageNode.locator('[data-action="toggle"]').click()
    await expect(referencedPackageContainer).toBeVisible()
    await expect(draftedStateNode).toBeVisible()
  })

  test('moves internal nodes freely inside expanded containers', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()

    const statePackageRoot = page.getByTestId('network-editor-state-node-1')
    await clickAndWaitForGraphReload(page, () => statePackageRoot.getByText('展开', { exact: true }).click())
    const statePackageContainer = page.getByTestId('network-editor-state-package-container-1')
    await expect(statePackageContainer).toBeVisible()
    const statePackageRootBefore = await readCanvasPosition(statePackageContainer)

    const childState = page.getByTestId('network-editor-state-node-3')
    const childStateBefore = await readCanvasPosition(childState)
    await dragLocatorBy(page, childState.locator('.layout-handle'), 44, 18)
    const childStateAfter = await readCanvasPosition(childState)
    const statePackageRootAfter = await readCanvasPosition(statePackageContainer)
    expect(childStateAfter.x).toBeGreaterThan(childStateBefore.x + 20)
    expect(childStateAfter.y).toBeGreaterThan(childStateBefore.y + 8)
    expect(Math.abs(statePackageRootAfter.x - statePackageRootBefore.x)).toBeLessThan(2)
    expect(Math.abs(statePackageRootAfter.y - statePackageRootBefore.y)).toBeLessThan(2)

    const virtualActivityRoot = page.getByTestId('network-editor-activity-node-activity_node:10')
    await clickAndWaitForGraphReload(page, () => virtualActivityRoot.getByText('展开', { exact: true }).click())
    const virtualActivityContainer = page.getByTestId('network-editor-virtual-activity-container-activity_node:10')
    await expect(virtualActivityContainer).toBeVisible()
    const virtualActivityRootBefore = await readCanvasPosition(virtualActivityContainer)

    const atomicActivity = page.getByTestId('network-editor-activity-node-atomic_activity:20')
    const atomicBefore = await readCanvasPosition(atomicActivity)
    await dragLocatorBy(page, atomicActivity.locator('.layout-handle'), 46, 20)
    const atomicAfter = await readCanvasPosition(atomicActivity)
    const virtualActivityRootAfter = await readCanvasPosition(virtualActivityContainer)
    expect(atomicAfter.x).toBeGreaterThan(atomicBefore.x + 20)
    expect(atomicAfter.y).toBeGreaterThan(atomicBefore.y + 8)
    expect(Math.abs(virtualActivityRootAfter.x - virtualActivityRootBefore.x)).toBeLessThan(2)
    expect(Math.abs(virtualActivityRootAfter.y - virtualActivityRootBefore.y)).toBeLessThan(2)

    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()
    await expect(page.locator('.draft-change-list')).toContainText('调整状态位置')
    await expect(page.locator('.draft-change-list')).toContainText('调整原子活动位置')
  })

  test('moves expanded containers with their internal nodes as one draft batch', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()

    const stateNode = page.getByTestId('network-editor-state-node-1')
    await clickAndWaitForGraphReload(page, () => stateNode.getByText('展开', { exact: true }).click())
    await expect(stateNode.getByText('折叠', { exact: true })).toBeVisible()
    const statePackageContainer = page.getByTestId('network-editor-state-package-container-1')
    await expect(statePackageContainer).toBeVisible()
    const childState = page.getByTestId('network-editor-state-node-3')
    await expect(childState).toBeVisible()
    const childStateBefore = await readCanvasPosition(childState)
    await dragLocatorBy(page, page.getByTestId('network-editor-state-package-container-move-1'), 36, 22)
    const childStateAfter = await readCanvasPosition(childState)
    expect(childStateAfter.x).toBeGreaterThan(childStateBefore.x + 20)
    expect(childStateAfter.y).toBeGreaterThan(childStateBefore.y + 10)

    const virtualActivity = page.getByTestId('network-editor-activity-node-activity_node:10')
    await clickAndWaitForGraphReload(page, () => virtualActivity.getByText('展开', { exact: true }).click())
    await expect(virtualActivity.getByText('折叠', { exact: true })).toBeVisible()
    await expect(page.getByTestId('network-editor-virtual-activity-container-activity_node:10')).toBeVisible()
    const atomicActivity = page.getByTestId('network-editor-activity-node-atomic_activity:20')
    await expect(atomicActivity).toBeVisible()
    const atomicBefore = await readCanvasPosition(atomicActivity)
    await dragLocatorBy(page, page.getByTestId('network-editor-virtual-activity-container-move-activity_node:10'), 38, 24)
    const atomicAfter = await readCanvasPosition(atomicActivity)
    expect(atomicAfter.x).toBeGreaterThan(atomicBefore.x + 20)
    expect(atomicAfter.y).toBeGreaterThan(atomicBefore.y + 10)

    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()
    await expect(page.locator('.draft-change-list')).toContainText('调整状态位置')
    await expect(page.locator('.draft-change-list')).toContainText('调整原子活动位置')
  })
})
