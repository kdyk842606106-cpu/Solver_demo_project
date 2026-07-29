import { test, expect } from '@playwright/test'

const impactDebounceBufferMs = 260
const wrappedFlowRowTolerance = 34

const machineTypes = [
  { id: 1, code: 'LATHE', name: 'CNC Lathe', description: 'Network editor fixture' },
]

const stateFeatureDefs = [
  'ready_flag',
  'draft_nested_state',
  'draft_atomic_option',
  'referenced_package_draft_state',
  ...Array.from({ length: 6 }, (_, index) => `input_${index + 1}`),
].flatMap((featureKey, index) => {
  const templateKey = `${featureKey}_dim_state`
  return [
    {
      id: 1000 + index * 2,
      machine_type_id: 1,
      feature_key: templateKey,
      feature_name: `${featureKey} dimension`,
      value_type: 'enum',
      allowed_values: ['false', 'true'],
    },
    {
      id: 1001 + index * 2,
      machine_type_id: 1,
      feature_key: `${templateKey}__existing`,
      feature_name: `${featureKey} existing`,
      value_type: 'enum',
      allowed_values: ['false', 'true'],
    },
  ]
})

function templateFeatureKey(featureKey: string) {
  return `${featureKey}_dim_state`
}

function concreteFeatureKey(featureKey: string, objectName: string) {
  const parts: string[] = []
  let ascii = ''
  const flushAscii = () => {
    const trimmed = ascii.replace(/^_+|_+$/g, '')
    if (trimmed) parts.push(trimmed)
    ascii = ''
  }
  for (const rawChar of String(objectName || '').trim().toLowerCase()) {
    if (/^[a-z0-9]$/.test(rawChar)) {
      ascii += rawChar
      continue
    }
    if (rawChar === '_' || /^\s$/.test(rawChar) || /^[\p{P}\p{S}]$/u.test(rawChar)) {
      if (ascii && !ascii.endsWith('_')) ascii += '_'
      continue
    }
    flushAscii()
    parts.push(`u${rawChar.codePointAt(0)?.toString(16)}`)
  }
  flushAscii()
  const token = parts.join('_').replace(/_+/g, '_').replace(/^_+|_+$/g, '') || 'object'
  const prefix = `${templateFeatureKey(featureKey)}__`
  const maxObjectLength = Math.max(1, 64 - prefix.length)
  const objectToken = token.slice(0, maxObjectLength).replace(/^_+|_+$/g, '') || 'object'
  return `${prefix}${objectToken}`
}

function stateTemplateMetadata(featureKey: string, objectName: string, extra: Record<string, any> = {}) {
  return {
    ...extra,
    dimension_template_key: templateFeatureKey(featureKey),
    state_object_name: objectName,
  }
}

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
    feature_key: concreteFeatureKey(`input_${index + 1}`, `input ${index + 1}`),
    operator: 'eq',
    target_value: index === 0 ? 'false' : 'true',
    sort_order: 10 + index,
    is_active: true,
    metadata_json: stateTemplateMetadata(`input_${index + 1}`, `input ${index + 1}`, {
      _network_editor_layout: { x: 110, y: 480 + index * 72 },
    }),
  }
})

const reflexiveReadyFalseState = {
  id: 2,
  machine_type_id: 1,
  parent_id: null,
  level: 3,
  code: 'READY_FALSE',
  name: 'Ready flag false',
  state_kind: 'atomic',
  feature_key: concreteFeatureKey('ready_flag', '包内原子状态'),
  operator: 'eq',
  target_value: 'false',
  sort_order: 9,
  is_active: true,
  metadata_json: stateTemplateMetadata('ready_flag', '包内原子状态', {
    _network_editor_layout: { x: 110, y: 156 },
  }),
}

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
  reflexiveReadyFalseState,
  {
    id: 3,
    machine_type_id: 1,
    parent_id: 1,
    level: 2,
    code: 'STATE_IN_READY',
    name: '包内原子状态',
    state_kind: 'atomic',
    feature_key: concreteFeatureKey('ready_flag', '包内原子状态'),
    operator: 'eq',
    target_value: 'true',
    sort_order: 1,
    is_active: true,
    metadata_json: stateTemplateMetadata('ready_flag', '包内原子状态', {
      _network_editor_layout: { x: 125, y: 230 },
    }),
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
    code: 'PKG_PREP',
    name: '准备活动包',
    description: '',
    activity_category: 'operation',
    sort_order: 1,
    is_active: true,
    metadata_json: { _network_editor_layout: { x: 520, y: 100 } },
  },
]

const nestedActivityNodes = [
  {
    ...activityNodes[0],
    level: 1,
  },
  {
    ...activityNodes[0],
    id: 11,
    parent_id: 10,
    level: 2,
    code: 'VA_PACK',
    name: 'Nested activity package',
    sort_order: 2,
    metadata_json: { _network_editor_layout: { x: 532, y: 126 } },
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
  {
    id: 21,
    machine_type_id: 1,
    code: 'AA_ALT',
    name: '备用达成活动',
    description: '',
    activity_category: 'operation',
    sort_order: 2,
    is_active: true,
    metadata_json: { _network_editor_layout: { x: 520, y: 360 } },
  },
]

const activityPackageAtomicRefs = [
  {
    id: 700,
    activity_node_id: 10,
    atomic_activity_id: 20,
    sort_order: 1,
    is_active: true,
    metadata_json: { _network_editor_layout: { x: 520, y: 260 }, instance_note: 'package ref layout' },
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
  view_mode: 'state_transition',
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
      feature_key: concreteFeatureKey('ready_flag', '包内原子状态'),
      operator: 'eq',
      target_value: 'true',
      is_active: true,
      is_leaf: true,
      leaf_state_ids: [3],
      leaf_count: 1,
      path_ids: [1, 3],
      metadata_json: stateTemplateMetadata('ready_flag', '包内原子状态', {
        _network_editor_layout: { x: 125, y: 230 },
      }),
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
      code: 'PKG_PREP',
      name: '准备活动包',
      description: '',
      activity_type: 'activity_package',
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
      parent_graph_id: 'activity_node:10',
      parent_activity_node_ids: [10],
      package_ref_ids: [700],
      reference_id: 700,
      reference_ids: [700],
      level: 3,
      code: 'AA_FINISH',
      name: '完成原子活动',
      description: '',
      activity_type: 'executable',
      activity_category: 'operation',
      solver_participation: true,
      is_active: true,
      path_ids: [[10, 20]],
      metadata_json: activityPackageAtomicRefs[0].metadata_json,
      atomic_metadata_json: atomicActivities[0].metadata_json,
    },
    {
      id: 'atomic_activity:21',
      activity_node_id: null,
      atomic_activity_id: 21,
      parent_id: null,
      parent_graph_id: null,
      parent_activity_node_ids: [],
      package_ref_ids: [],
      reference_id: null,
      reference_ids: [],
      level: 3,
      code: 'AA_ALT',
      name: '备用达成活动',
      description: '',
      activity_type: 'executable',
      activity_category: 'operation',
      solver_participation: true,
      is_active: true,
      path_ids: [[21]],
      metadata_json: atomicActivities[1].metadata_json,
      atomic_metadata_json: atomicActivities[1].metadata_json,
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
    executable_activity_count: 1,
    edge_count: 9,
    coverage_gap_count: 0,
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

function graphNodeForStateFixture(state: any, overrides: any = {}) {
  const childIds = overrides.child_ids || []
  return {
    id: `state_node:${state.id}`,
    state_node_id: state.id,
    parent_id: state.parent_id,
    primary_parent_graph_id: state.parent_id ? `state_node:${state.parent_id}` : null,
    reference_parent_ids: [],
    reference_ids: [],
    child_ids: childIds,
    level: state.level,
    code: state.code,
    name: state.name,
    state_kind: state.state_kind,
    feature_key: state.feature_key,
    operator: state.operator,
    target_value: state.target_value,
    is_active: state.is_active !== false,
    is_leaf: !childIds.length,
    leaf_state_ids: childIds.length ? childIds : [state.id],
    leaf_count: childIds.length || 1,
    path_ids: state.parent_id ? [state.parent_id, state.id] : [state.id],
    metadata_json: state.metadata_json,
    reference_id: null,
    is_reference_instance: false,
    ...overrides,
  }
}

function graphRequestShowsChildren(body: any, depthField = 'state_depth') {
  const depth = Number(body?.[depthField])
  return depth === 0 || depth >= 2
}

function graphRequestIsFullProjection(body: any) {
  return Number(body?.state_depth) === 0 &&
    Number(body?.activity_depth) === 0 &&
    !(body?.state_root_ids || []).length &&
    !(body?.activity_scope_node_ids || []).length
}

function foldedParentsGraphResponseForRequest(request: any) {
  const body = JSON.parse(request.postData() || '{}')
  const stateRoots = new Set((body.state_root_ids || []).map((id: any) => Number(id)))
  const activityScopes = new Set((body.activity_scope_node_ids || []).map((id: any) => Number(id)))
  const fullProjection = graphRequestIsFullProjection(body)
  const stateExpanded = fullProjection || (stateRoots.has(1) && graphRequestShowsChildren(body))
  const activityDepth = Number(body.activity_depth)
  const activityExpanded = fullProjection || (activityScopes.has(10) && (activityDepth === 0 || activityDepth >= 2))
  const statePackage = graphResponse.state_nodes.find((node: any) => node.state_node_id === 1)
  const childState = graphResponse.state_nodes.find((node: any) => node.state_node_id === 3)
  const activityPackage = graphResponse.activity_nodes.find((node: any) => node.id === 'activity_node:10')
  const atomicActivity = graphResponse.activity_nodes.find((node: any) => node.id === 'atomic_activity:20')
  return {
    ...graphResponse,
    state_nodes: [
      statePackage,
      ...(stateExpanded ? [childState] : []),
    ].filter(Boolean),
    activity_nodes: [
      activityPackage,
      ...(activityExpanded ? [atomicActivity] : []),
    ].filter(Boolean),
  }
}

function independentStateRootsGraphResponseForRequest(request: any) {
  const body = JSON.parse(request.postData() || '{}')
  if (graphRequestIsFullProjection(body)) return twoExpandedStateRootsGraphResponse()
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

const wrappedFlowChildIds = [50, 51, 52, 53, 54]
const wrappedFlowStateNodes = wrappedFlowChildIds.map((id, index) => ({
  id,
  machine_type_id: 1,
  parent_id: 4,
  level: 2,
  code: `FLOW_STEP_${index + 1}`,
  name: `Flow step ${index + 1}`,
  state_kind: 'atomic',
  feature_key: `flow_step_${index + 1}`,
  operator: 'eq',
  target_value: 'true',
  sort_order: index + 1,
  is_active: true,
  metadata_json: { _network_editor_layout: { x: 126, y: 520 + index * 86 } },
}))
const wrappedFlowBindings = wrappedFlowChildIds.slice(0, -1).flatMap((id, index) => {
  const activityId = 900 + index
  const nextId = wrappedFlowChildIds[index + 1]
  return [
    {
      id: 500 + index * 2,
      machine_type_id: 1,
      activity_node_id: null,
      atomic_activity_id: activityId,
      op_rule_id: null,
      state_node_id: id,
      binding_role: 'input',
      binding_type: 'direct',
      coverage_policy: 'explicit',
      covered_leaf_state_ids: [id],
      coverage_status: 'complete',
      is_inherited: false,
      is_active: true,
      metadata_json: null,
    },
    {
      id: 501 + index * 2,
      machine_type_id: 1,
      activity_node_id: null,
      atomic_activity_id: activityId,
      op_rule_id: null,
      state_node_id: nextId,
      binding_role: 'output',
      binding_type: 'direct',
      coverage_policy: 'explicit',
      covered_leaf_state_ids: [nextId],
      coverage_status: 'complete',
      is_inherited: false,
      is_active: true,
      metadata_json: null,
    },
  ]
})

function wrappedFlowGraphResponseForRequest(request: any) {
  const body = JSON.parse(request.postData() || '{}')
  const stateRoots = new Set((body.state_root_ids || []).map((id: any) => Number(id)))
  const fullProjection = graphRequestIsFullProjection(body)
  const state4Expanded = fullProjection || (stateRoots.has(4) && graphRequestShowsChildren(body))
  const state1 = graphResponse.state_nodes.find((node: any) => node.state_node_id === 1)
  const state4 = graphResponse.state_nodes.find((node: any) => node.state_node_id === 4)
  const childIds = wrappedFlowChildIds
  const children = wrappedFlowStateNodes.map((state) => ({
    id: `state_node:${state.id}`,
    state_node_id: state.id,
    parent_id: 4,
    primary_parent_graph_id: 'state_node:4',
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
    path_ids: [4, state.id],
    metadata_json: state.metadata_json,
    reference_id: null,
    is_reference_instance: false,
  }))

  return {
    ...graphResponse,
    state_nodes: [
      state1,
      {
        ...state4,
        child_ids: childIds,
        leaf_state_ids: childIds,
        leaf_count: childIds.length,
        metadata_json: { _network_editor_layout: { x: 80, y: 390 } },
      },
      ...(state4Expanded ? children : []),
    ].filter(Boolean),
    activity_nodes: [],
    bindings: wrappedFlowBindings,
    edges: [],
    summary: {
      ...graphResponse.summary,
      state_node_count: state4Expanded ? 7 : 2,
      state_instance_count: state4Expanded ? 7 : 2,
      activity_node_count: 0,
      edge_count: state4Expanded ? wrappedFlowBindings.length : 0,
      binding_count: wrappedFlowBindings.length,
    },
  }
}

const forkJoinFlowStateNodes = [
  { id: 60, code: 'FRAME_READY', name: 'Frame ready', sort_order: 1, y: 520 },
  { id: 61, code: 'MODULE_A_INSTALLED', name: 'Module A installed', sort_order: 2, y: 606 },
  { id: 62, code: 'MODULE_B_INSTALLED', name: 'Module B installed', sort_order: 3, y: 692 },
  { id: 63, code: 'ALIGNMENT_DONE', name: 'Alignment done', sort_order: 4, y: 778 },
].map((state) => ({
  id: state.id,
  machine_type_id: 1,
  parent_id: 4,
  level: 2,
  code: state.code,
  name: state.name,
  state_kind: 'atomic',
  feature_key: state.code.toLowerCase(),
  operator: 'eq',
  target_value: 'true',
  sort_order: state.sort_order,
  is_active: true,
  metadata_json: { _network_editor_layout: { x: 126, y: state.y } },
}))

const nestedForkJoinPackageState = {
  id: 70,
  machine_type_id: 1,
  parent_id: 4,
  level: 2,
  code: 'ASSEMBLY_PHASE',
  name: 'Assembly phase',
  state_kind: 'aggregate',
  feature_key: null,
  operator: 'eq',
  target_value: null,
  sort_order: 10,
  is_active: true,
  metadata_json: { _network_editor_layout: { x: 118, y: 500 } },
}

const nestedForkJoinFlowStateNodes = forkJoinFlowStateNodes.map((state) => ({
  ...state,
  parent_id: 70,
  level: 3,
  metadata_json: { _network_editor_layout: { x: 160, y: state.metadata_json._network_editor_layout.y } },
}))

const forkJoinFlowBindings = [
  [60, 61, 920],
  [60, 62, 921],
  [61, 63, 922],
  [62, 63, 923],
].flatMap(([sourceStateId, targetStateId, activityId], index) => [
  {
    id: 620 + index * 2,
    machine_type_id: 1,
    activity_node_id: null,
    atomic_activity_id: activityId,
    op_rule_id: null,
    state_node_id: sourceStateId,
    binding_role: 'input',
    binding_type: 'direct',
    coverage_policy: 'explicit',
    covered_leaf_state_ids: [sourceStateId],
    coverage_status: 'complete',
    is_inherited: false,
    is_active: true,
    metadata_json: null,
  },
  {
    id: 621 + index * 2,
    machine_type_id: 1,
    activity_node_id: null,
    atomic_activity_id: activityId,
    op_rule_id: null,
    state_node_id: targetStateId,
    binding_role: 'output',
    binding_type: 'direct',
    coverage_policy: 'explicit',
    covered_leaf_state_ids: [targetStateId],
    coverage_status: 'complete',
    is_inherited: false,
    is_active: true,
    metadata_json: null,
  },
])

function forkJoinFlowGraphResponseForRequest(request: any) {
  const body = JSON.parse(request.postData() || '{}')
  const stateRoots = new Set((body.state_root_ids || []).map((id: any) => Number(id)))
  const fullProjection = graphRequestIsFullProjection(body)
  const state4Expanded = fullProjection || (stateRoots.has(4) && graphRequestShowsChildren(body))
  const state1 = graphResponse.state_nodes.find((node: any) => node.state_node_id === 1)
  const state4 = graphResponse.state_nodes.find((node: any) => node.state_node_id === 4)
  const childIds = forkJoinFlowStateNodes.map((state) => state.id)
  const children = forkJoinFlowStateNodes.map((state) => ({
    id: `state_node:${state.id}`,
    state_node_id: state.id,
    parent_id: 4,
    primary_parent_graph_id: 'state_node:4',
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
    path_ids: [4, state.id],
    metadata_json: state.metadata_json,
    reference_id: null,
    is_reference_instance: false,
  }))

  return {
    ...graphResponse,
    state_nodes: [
      state1,
      {
        ...state4,
        child_ids: childIds,
        leaf_state_ids: childIds,
        leaf_count: childIds.length,
        metadata_json: { _network_editor_layout: { x: 80, y: 390 } },
      },
      ...(state4Expanded ? children : []),
    ].filter(Boolean),
    activity_nodes: [],
    bindings: forkJoinFlowBindings,
    edges: [],
    summary: {
      ...graphResponse.summary,
      state_node_count: state4Expanded ? 6 : 2,
      state_instance_count: state4Expanded ? 6 : 2,
      activity_node_count: 0,
      edge_count: state4Expanded ? forkJoinFlowBindings.length : 0,
      binding_count: forkJoinFlowBindings.length,
    },
  }
}

function nestedForkJoinFlowGraphResponseForRequest(request: any) {
  const body = JSON.parse(request.postData() || '{}')
  const stateRoots = new Set((body.state_root_ids || []).map((id: any) => Number(id)))
  const fullProjection = graphRequestIsFullProjection(body)
  const state4Expanded = fullProjection || (stateRoots.has(4) && graphRequestShowsChildren(body))
  const state4FullyExpanded = fullProjection || (stateRoots.has(4) && Number(body.state_depth) === 0)
  const nestedPackageExpanded = stateRoots.has(70) && graphRequestShowsChildren(body)
  const state1 = graphResponse.state_nodes.find((node: any) => node.state_node_id === 1)
  const state4 = graphResponse.state_nodes.find((node: any) => node.state_node_id === 4)
  const childIds = nestedForkJoinFlowStateNodes.map((state) => state.id)
  const packageNode = {
    id: 'state_node:70',
    state_node_id: 70,
    parent_id: 4,
    primary_parent_graph_id: 'state_node:4',
    reference_parent_ids: [],
    reference_ids: [],
    child_ids: childIds,
    level: 2,
    code: nestedForkJoinPackageState.code,
    name: nestedForkJoinPackageState.name,
    state_kind: 'aggregate',
    feature_key: null,
    operator: 'eq',
    target_value: null,
    is_active: true,
    is_leaf: false,
    leaf_state_ids: childIds,
    leaf_count: childIds.length,
    path_ids: [4, 70],
    metadata_json: nestedForkJoinPackageState.metadata_json,
    reference_id: null,
    is_reference_instance: false,
  }
  const children = nestedForkJoinFlowStateNodes.map((state) => ({
    id: `state_node:${state.id}`,
    state_node_id: state.id,
    parent_id: 70,
    primary_parent_graph_id: 'state_node:70',
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
    path_ids: [4, 70, state.id],
    metadata_json: state.metadata_json,
    reference_id: null,
    is_reference_instance: false,
  }))

  return {
    ...graphResponse,
    state_nodes: [
      state1,
      {
        ...state4,
        child_ids: [70],
        leaf_state_ids: childIds,
        leaf_count: childIds.length,
        metadata_json: { _network_editor_layout: { x: 80, y: 390 } },
      },
      ...(state4Expanded ? [packageNode] : []),
      ...(state4FullyExpanded || nestedPackageExpanded ? children : []),
    ].filter(Boolean),
    activity_nodes: [],
    bindings: forkJoinFlowBindings,
    edges: [],
    summary: {
      ...graphResponse.summary,
      state_node_count: state4FullyExpanded || nestedPackageExpanded ? 7 : (state4Expanded ? 3 : 2),
      state_instance_count: state4FullyExpanded || nestedPackageExpanded ? 7 : (state4Expanded ? 3 : 2),
      activity_node_count: 0,
      edge_count: state4FullyExpanded || nestedPackageExpanded ? forkJoinFlowBindings.length : 0,
      binding_count: forkJoinFlowBindings.length,
    },
  }
}

const packageAggregationPackageIds = [110, 120, 130, 140, 150, 160]
const packageAggregationPairs = [
  [110, 120],
  [120, 130],
  [120, 140],
  [110, 140],
  [130, 140],
  [140, 150],
  [130, 150],
  [150, 160],
]
const packageAggregationRootState = {
  id: 100,
  machine_type_id: 1,
  parent_id: null,
  level: 1,
  code: 'HP_ROOT',
  name: '高并行完成',
  state_kind: 'aggregate',
  feature_key: null,
  operator: 'eq',
  target_value: null,
  sort_order: 1,
  is_active: true,
  metadata_json: { _network_editor_layout: { x: 70, y: 70 } },
}
const packageAggregationPeerRootState = {
  id: 170,
  machine_type_id: 1,
  parent_id: null,
  level: 1,
  code: 'HP_PEER_ROOT',
  name: 'Independent high-level state',
  state_kind: 'aggregate',
  feature_key: null,
  operator: 'eq',
  target_value: null,
  sort_order: 2,
  is_active: true,
  metadata_json: { _network_editor_layout: { x: 1120, y: 70 } },
}
const packageAggregationPackageStates = packageAggregationPackageIds.map((id, index) => ({
  id,
  machine_type_id: 1,
  parent_id: 100,
  level: 2,
  code: `HP_PACKAGE_${index + 1}`,
  name: `高并行状态包${index + 1}`,
  state_kind: 'aggregate',
  feature_key: null,
  operator: 'eq',
  target_value: null,
  sort_order: index + 1,
  is_active: true,
  metadata_json: { _network_editor_layout: { x: 110 + (index % 3) * 310, y: 180 + Math.floor(index / 3) * 160 } },
}))
const packageAggregationLeafStates = packageAggregationPackageIds.map((packageId, index) => ({
  id: packageId + 1,
  machine_type_id: 1,
  parent_id: packageId,
  level: 3,
  code: `HP_LEAF_${index + 1}`,
  name: `高并行原子状态${index + 1}`,
  state_kind: 'atomic',
  feature_key: `hp_leaf_${index + 1}`,
  operator: 'eq',
  target_value: 'true',
  sort_order: 1,
  is_active: true,
  metadata_json: { _network_editor_layout: { x: 140, y: 250 } },
}))
const packageAggregationWideChildLeafStates = Array.from({ length: 8 }, (_, index) => ({
  id: 122 + index,
  machine_type_id: 1,
  parent_id: 120,
  level: 3,
  code: `HP_WIDE_CHILD_${index + 2}`,
  name: `High-parallel child state ${index + 2}`,
  state_kind: 'atomic',
  feature_key: `hp_wide_child_${index + 2}`,
  operator: 'eq',
  target_value: 'true',
  sort_order: index + 2,
  is_active: true,
  metadata_json: { _network_editor_layout: { x: 140, y: 250 } },
}))
const packageAggregationWideChildAtomicActivities = packageAggregationWideChildLeafStates.map((state, index) => ({
  id: 1200 + index,
  machine_type_id: 1,
  code: `HP_WIDE_ACTIVITY_${index + 2}`,
  name: `High-parallel child realizer ${index + 2}`,
  description: '',
  activity_category: 'operation',
  sort_order: index + 1,
  is_active: true,
  metadata_json: {},
}))
const packageAggregationWideChildOpRules = packageAggregationWideChildAtomicActivities.map((activity, index) => ({
  id: 2200 + index,
  machine_type_id: 1,
  atomic_activity_id: activity.id,
  activity_node_id: null,
  code: `HP_WIDE_RULE_${index + 2}`,
  name: `High-parallel child rule ${index + 2}`,
  duration_min: 10,
  is_active: true,
  is_repair: false,
}))
const packageAggregationWideChildBindings = packageAggregationWideChildLeafStates.flatMap((state, index) => {
  const common = {
    machine_type_id: 1,
    activity_node_id: null,
    atomic_activity_id: packageAggregationWideChildAtomicActivities[index].id,
    op_rule_id: packageAggregationWideChildOpRules[index].id,
    binding_type: 'atomic_state',
    coverage_policy: 'snapshot',
    coverage_status: 'complete',
    is_inherited: false,
    is_active: true,
    metadata_json: null,
  }
  return [
    {
      ...common,
      id: 3400 + index * 2,
      state_node_id: 111,
      binding_role: 'input',
      covered_leaf_state_ids: [111],
    },
    {
      ...common,
      id: 3401 + index * 2,
      state_node_id: state.id,
      binding_role: 'output',
      covered_leaf_state_ids: [state.id],
    },
  ]
})
const packageAggregationAtomicActivities = packageAggregationPairs.map((_, index) => ({
  id: 1100 + index,
  machine_type_id: 1,
  code: `HP_ACTIVITY_${index + 1}`,
  name: `高并行达成活动${index + 1}`,
  description: '',
  activity_category: 'operation',
  sort_order: index + 1,
  is_active: true,
  metadata_json: {},
}))
const packageAggregationOpRules = packageAggregationAtomicActivities.map((activity, index) => ({
  id: 2100 + index,
  machine_type_id: 1,
  atomic_activity_id: activity.id,
  activity_node_id: null,
  code: `HP_RULE_${index + 1}`,
  name: `高并行规则${index + 1}`,
  duration_min: 10,
  is_active: true,
  is_repair: false,
}))
const packageAggregationBindings = packageAggregationPairs.flatMap(([sourcePackageId, targetPackageId], index) => {
  const activity = packageAggregationAtomicActivities[index]
  const rule = packageAggregationOpRules[index]
  return [
    {
      id: 3100 + index * 2,
      machine_type_id: 1,
      activity_node_id: null,
      atomic_activity_id: activity.id,
      op_rule_id: rule.id,
      state_node_id: sourcePackageId + 1,
      binding_role: 'input',
      binding_type: 'atomic_state',
      coverage_policy: 'snapshot',
      covered_leaf_state_ids: [sourcePackageId + 1],
      coverage_status: 'complete',
      is_inherited: false,
      is_active: true,
      metadata_json: null,
    },
    {
      id: 3101 + index * 2,
      machine_type_id: 1,
      activity_node_id: null,
      atomic_activity_id: activity.id,
      op_rule_id: rule.id,
      state_node_id: targetPackageId + 1,
      binding_role: 'output',
      binding_type: 'atomic_state',
      coverage_policy: 'snapshot',
      covered_leaf_state_ids: [targetPackageId + 1],
      coverage_status: 'complete',
      is_inherited: false,
      is_active: true,
      metadata_json: null,
    },
  ]
})

function packageAggregationGraphResponseForRequest(request: any) {
  const body = JSON.parse(request.postData() || '{}')
  const fullProjection = graphRequestIsFullProjection(body)
  const rootIds = new Set((body.state_root_ids || []).map((id: any) => Number(id)))
  const rootExpanded = rootIds.has(100) && graphRequestShowsChildren(body)
  const rootFullyExpanded = rootIds.has(100) && Number(body.state_depth) === 0
  const selectedPackageId = packageAggregationPackageIds.find((id) => rootIds.has(id)) || null
  const rootLeafIds = packageAggregationLeafStates.map((state) => state.id)
  const rootNode = graphNodeForStateFixture(packageAggregationRootState, {
    child_ids: packageAggregationPackageIds,
    leaf_state_ids: rootLeafIds,
    leaf_count: rootLeafIds.length,
  })
  const peerRootNode = graphNodeForStateFixture(packageAggregationPeerRootState, {
    child_ids: [],
    leaf_state_ids: [],
    leaf_count: 0,
  })
  const packageNodes = packageAggregationPackageStates.map((state, index) => graphNodeForStateFixture(state, {
    child_ids: [packageAggregationLeafStates[index].id],
    leaf_state_ids: [packageAggregationLeafStates[index].id],
    leaf_count: 1,
    path_ids: [100, state.id],
  }))
  const leafNodes = packageAggregationLeafStates.map((state) => graphNodeForStateFixture(state, {
    path_ids: [100, state.parent_id, state.id],
  }))
  const stateNodesForResponse = fullProjection
    ? [rootNode, peerRootNode, ...packageNodes, ...leafNodes]
    : selectedPackageId
      ? [
          packageNodes.find((node) => node.state_node_id === selectedPackageId),
          ...(graphRequestShowsChildren(body)
            ? leafNodes.filter((node) => node.parent_id === selectedPackageId)
            : []),
        ].filter(Boolean)
      : [
          rootNode,
          peerRootNode,
          ...(rootExpanded ? packageNodes : []),
          ...(rootFullyExpanded ? leafNodes : []),
        ]
  return {
    ...graphResponse,
    state_nodes: stateNodesForResponse,
    activity_nodes: [],
    bindings: packageAggregationBindings,
    edges: [],
    summary: {
      ...graphResponse.summary,
      state_node_count: stateNodesForResponse.length,
      state_instance_count: stateNodesForResponse.length,
      activity_node_count: 0,
      edge_count: 0,
      binding_count: packageAggregationBindings.length,
    },
  }
}

function packageAggregationWideChildGraphResponseForRequest(request: any) {
  const response = packageAggregationGraphResponseForRequest(request)
  const bindings = [...packageAggregationBindings, ...packageAggregationWideChildBindings]
  const body = JSON.parse(request.postData() || '{}')
  const packageVisible = response.state_nodes.some((node: any) => Number(node.state_node_id) === 120)
  if (!packageVisible || (!graphRequestIsFullProjection(body) && !graphRequestShowsChildren(body))) return response
  const extraNodes = packageAggregationWideChildLeafStates.map((state) => graphNodeForStateFixture(state, {
    path_ids: [100, 120, state.id],
  }))
  const childIds = [121, ...packageAggregationWideChildLeafStates.map((state) => state.id)]
  const stateNodes = response.state_nodes
    .map((node: any) => Number(node.state_node_id) === 120
      ? { ...node, child_ids: childIds, leaf_state_ids: childIds, leaf_count: childIds.length }
      : node)
    .concat(extraNodes)
  return {
    ...response,
    state_nodes: stateNodes,
    bindings,
    summary: {
      ...response.summary,
      state_node_count: stateNodes.length,
      state_instance_count: stateNodes.length,
      binding_count: bindings.length,
    },
  }
}

const statePackageBindingStates = [
  {
    id: 200,
    machine_type_id: 1,
    parent_id: null,
    level: 1,
    code: 'PACKAGE_BINDING_ROOT',
    name: '状态包绑定根',
    state_kind: 'aggregate',
    feature_key: null,
    operator: 'eq',
    target_value: null,
    sort_order: 1,
    is_active: true,
    metadata_json: { _network_editor_layout: { x: 70, y: 70 } },
  },
  {
    id: 210,
    machine_type_id: 1,
    parent_id: 200,
    level: 2,
    code: 'PACKAGE_PRECONDITION',
    name: '完整状态包前置',
    state_kind: 'aggregate',
    feature_key: null,
    operator: 'eq',
    target_value: null,
    sort_order: 1,
    is_active: true,
    metadata_json: { _network_editor_layout: { x: 110, y: 190 } },
  },
  {
    id: 220,
    machine_type_id: 1,
    parent_id: 200,
    level: 2,
    code: 'PACKAGE_TARGET',
    name: '调试目标状态包',
    state_kind: 'aggregate',
    feature_key: null,
    operator: 'eq',
    target_value: null,
    sort_order: 2,
    is_active: true,
    metadata_json: { _network_editor_layout: { x: 520, y: 190 } },
  },
  ...[211, 212, 213].map((id, index) => ({
    id,
    machine_type_id: 1,
    parent_id: 210,
    level: 3,
    code: `PACKAGE_PRECONDITION_LEAF_${index + 1}`,
    name: `状态包前置成员${index + 1}`,
    state_kind: 'atomic',
    feature_key: `package_precondition_${index + 1}`,
    operator: 'eq',
    target_value: 'true',
    sort_order: index + 1,
    is_active: true,
    metadata_json: { _network_editor_layout: { x: 140, y: 280 + index * 72 } },
  })),
  {
    id: 221,
    machine_type_id: 1,
    parent_id: 220,
    level: 3,
    code: 'PACKAGE_TARGET_LEAF',
    name: '具体调试状态',
    state_kind: 'atomic',
    feature_key: 'package_target_leaf',
    operator: 'eq',
    target_value: 'true',
    sort_order: 1,
    is_active: true,
    metadata_json: { _network_editor_layout: { x: 550, y: 280 } },
  },
]
const statePackageBindingActivity = {
  id: 1200,
  machine_type_id: 1,
  code: 'PACKAGE_REALIZER',
  name: '调试达成活动',
  description: '',
  activity_category: 'operation',
  sort_order: 1,
  is_active: true,
  metadata_json: {},
}
const statePackageBindingRule = {
  id: 2200,
  machine_type_id: 1,
  atomic_activity_id: 1200,
  activity_node_id: null,
  code: 'PACKAGE_REALIZER_RULE',
  name: '调试达成规则',
  duration_min: 15,
  is_active: true,
  is_repair: false,
}

function statePackageBindingRows(coverageStatus = 'complete') {
  return [
    {
      id: 3200,
      machine_type_id: 1,
      activity_node_id: null,
      atomic_activity_id: 1200,
      op_rule_id: 2200,
      state_node_id: 210,
      binding_role: 'input',
      binding_type: 'state_package',
      coverage_policy: 'snapshot',
      covered_leaf_state_ids: coverageStatus === 'complete' ? [211, 212, 213] : [211, 212],
      coverage_status: coverageStatus,
      is_inherited: false,
      is_active: true,
      metadata_json: null,
    },
    {
      id: 3201,
      machine_type_id: 1,
      activity_node_id: null,
      atomic_activity_id: 1200,
      op_rule_id: 2200,
      state_node_id: 221,
      binding_role: 'output',
      binding_type: 'atomic_state',
      coverage_policy: 'snapshot',
      covered_leaf_state_ids: [221],
      coverage_status: 'complete',
      is_inherited: false,
      is_active: true,
      metadata_json: null,
    },
  ]
}

function statePackageOutputBindingRows() {
  return [
    {
      id: 3210,
      machine_type_id: 1,
      activity_node_id: null,
      atomic_activity_id: 1200,
      op_rule_id: 2200,
      state_node_id: 211,
      binding_role: 'input',
      binding_type: 'atomic_state',
      coverage_policy: 'snapshot',
      covered_leaf_state_ids: [211],
      coverage_status: 'complete',
      is_inherited: false,
      is_active: true,
      metadata_json: null,
    },
    {
      id: 3211,
      machine_type_id: 1,
      activity_node_id: null,
      atomic_activity_id: 1200,
      op_rule_id: 2200,
      state_node_id: 220,
      binding_role: 'output',
      binding_type: 'state_package',
      coverage_policy: 'snapshot',
      covered_leaf_state_ids: [221],
      coverage_status: 'complete',
      is_inherited: false,
      is_active: true,
      metadata_json: null,
    },
  ]
}

function statePackageBindingGraphResponseForRequest(request: any, fixtureBindings = statePackageBindingRows()) {
  const body = JSON.parse(request.postData() || '{}')
  const fullProjection = graphRequestIsFullProjection(body)
  const rootIds = new Set((body.state_root_ids || []).map((id: any) => Number(id)))
  const rootExpanded = rootIds.has(200) && graphRequestShowsChildren(body)
  const rootFullyExpanded = rootIds.has(200) && Number(body.state_depth) === 0
  const childrenByParent = new Map<any, any[]>()
  for (const state of statePackageBindingStates) {
    if (!childrenByParent.has(state.parent_id)) childrenByParent.set(state.parent_id, [])
    childrenByParent.get(state.parent_id)?.push(state)
  }
  const graphNodes = statePackageBindingStates.map((state) => {
    const childIds = (childrenByParent.get(state.id) || []).map((child) => child.id)
    const leafIds = state.id === 200 ? [211, 212, 213, 221]
      : state.id === 210 ? [211, 212, 213]
        : state.id === 220 ? [221]
          : [state.id]
    const pathIds = state.parent_id === null ? [state.id]
      : state.level === 2 ? [200, state.id]
        : [200, state.parent_id, state.id]
    return graphNodeForStateFixture(state, {
      child_ids: childIds,
      leaf_state_ids: leafIds,
      leaf_count: leafIds.length,
      path_ids: pathIds,
    })
  })
  const rootNode = graphNodes.find((node) => node.state_node_id === 200)
  const packageNodes = graphNodes.filter((node) => [210, 220].includes(node.state_node_id))
  const leafNodes = graphNodes.filter((node) => node.level === 3)
  const selectedPackageId = [210, 220].find((id) => rootIds.has(id)) || null
  const stateNodesForResponse = fullProjection
    ? graphNodes
    : selectedPackageId
      ? [
          graphNodes.find((node) => node.state_node_id === selectedPackageId),
          ...(graphRequestShowsChildren(body) ? leafNodes.filter((node) => node.parent_id === selectedPackageId) : []),
        ].filter(Boolean)
      : [
          rootNode,
          ...(rootExpanded ? packageNodes : []),
          ...(rootFullyExpanded ? leafNodes : []),
        ].filter(Boolean)
  return {
    ...graphResponse,
    state_nodes: stateNodesForResponse,
    activity_nodes: [],
    bindings: fixtureBindings,
    edges: [],
    summary: {
      ...graphResponse.summary,
      state_node_count: stateNodesForResponse.length,
      state_instance_count: stateNodesForResponse.length,
      activity_node_count: 0,
      edge_count: 0,
      binding_count: fixtureBindings.length,
    },
  }
}

function collapsedProxyEdgeGraphResponseForRequest(request: any) {
  const body = JSON.parse(request.postData() || '{}')
  const activityScopeIds = new Set((body.activity_scope_node_ids || []).map((id: any) => Number(id)))
  const activityDepth = Number(body.activity_depth)
  const fullProjection = graphRequestIsFullProjection(body)
  const activityExpanded = fullProjection || (activityScopeIds.has(10) && (activityDepth === 0 || activityDepth >= 2))
  const expanded = stateDoneExpandedGraphResponse()
  const stateDoneParent = expanded.state_nodes.find((node: any) => node.state_node_id === 4)
  const childState = expanded.state_nodes.find((node: any) => node.state_node_id === 40)
  const activityPackage = graphResponse.activity_nodes.find((node: any) => node.id === 'activity_node:10')
  const atomicActivity = graphResponse.activity_nodes.find((node: any) => node.id === 'atomic_activity:20')
  return {
    ...expanded,
    state_nodes: [
      ...graphResponse.state_nodes.filter((node: any) => node.state_node_id !== 4),
      stateDoneParent,
      childState,
    ],
    activity_nodes: [
      {
        ...activityPackage,
        child_activity_node_ids: [20],
      },
      ...(activityExpanded ? [atomicActivity] : []),
    ],
    edges: [
      {
        id: 'binding:103:STATE_TO_ACTIVITY',
        source_id: 'state_node:40',
        target_id: 'atomic_activity:20',
        type: 'STATE_TO_ACTIVITY',
        binding_id: 103,
        binding_role: 'input',
        source_kind: 'activity_state_binding',
        coverage_status: 'complete',
      },
    ],
    summary: {
      ...graphResponse.summary,
      state_instance_count: graphResponse.summary.state_instance_count + 1,
      edge_count: 1,
    },
  }
}

function overlappingExpandedContainersGraphResponseForRequest(request: any) {
  const body = JSON.parse(request.postData() || '{}')
  const stateRoots = new Set((body.state_root_ids || []).map((id: any) => Number(id)))
  const activityScopes = new Set((body.activity_scope_node_ids || []).map((id: any) => Number(id)))
  const fullProjection = graphRequestIsFullProjection(body)
  const stateExpanded = graphRequestShowsChildren(body)
  const activityDepth = Number(body.activity_depth)
  const activityFullyExpanded = activityScopes.size > 0 && activityDepth === 0
  const showSecondLevelActivity = activityFullyExpanded || (activityScopes.has(10) && activityDepth >= 2)
  const showAtomicActivity = activityFullyExpanded || (activityScopes.has(11) && activityDepth >= 2)
  const state1 = graphResponse.state_nodes.find((node: any) => node.state_node_id === 1)
  const state3 = graphResponse.state_nodes.find((node: any) => node.state_node_id === 3)
  const state4 = graphResponse.state_nodes.find((node: any) => node.state_node_id === 4)
  const activityPackage10 = graphResponse.activity_nodes.find((node: any) => node.id === 'activity_node:10')
  const atomic20 = graphResponse.activity_nodes.find((node: any) => node.id === 'atomic_activity:20')
  const atomic21 = graphResponse.activity_nodes.find((node: any) => node.id === 'atomic_activity:21')
  const expandedState4 = {
    ...state4,
    child_ids: [40],
    leaf_state_ids: [40],
    leaf_count: 1,
    metadata_json: {
      _network_editor_layout: { x: 92, y: 118 },
      _network_editor_container: { width: 920, height: 760 },
    },
  }
  const child40 = {
    ...state3,
    id: 'state_node:40',
    state_node_id: 40,
    parent_id: 4,
    primary_parent_graph_id: 'state_node:4',
    code: 'STATE_DONE_LEAF',
    name: 'Done child state',
    feature_key: 'done_flag',
    path_ids: [4, 40],
    leaf_state_ids: [40],
    metadata_json: { _network_editor_layout: { x: 138, y: 238 } },
  }
  const activityPackage11 = {
    ...activityPackage10,
    id: 'activity_node:11',
    activity_node_id: 11,
    parent_id: 10,
    parent_graph_id: 'activity_node:10',
    child_activity_node_ids: [21],
    level: 2,
    code: 'VA_PACK',
    name: '鍖呰铏氭嫙娲诲姩',
    sort_order: 2,
    path_ids: [10, 11],
    metadata_json: { _network_editor_layout: { x: 532, y: 126 } },
  }
  const atomic21InPackage = {
    ...atomic21,
    parent_graph_id: 'activity_node:11',
    parent_activity_node_ids: [10, 11],
    package_ref_ids: [701],
    reference_id: 701,
    reference_ids: [701],
    path_ids: [[10, 11, 21]],
    metadata_json: { _network_editor_layout: { x: 532, y: 274 }, instance_note: 'overlap fixture ref layout' },
  }
  return {
    ...graphResponse,
    state_nodes: [
      {
        ...state1,
        metadata_json: { _network_editor_layout: { x: 80, y: 80 } },
      },
      ...(stateExpanded && (fullProjection || stateRoots.has(1)) ? [{
        ...state3,
        metadata_json: { _network_editor_layout: { x: 126, y: 214 } },
      }] : []),
      expandedState4,
      ...(stateExpanded && (fullProjection || stateRoots.has(4)) ? [child40] : []),
    ].filter(Boolean),
    activity_nodes: [
      {
        ...activityPackage10,
        child_activity_node_ids: [11],
        level: 1,
        metadata_json: { _network_editor_layout: { x: 520, y: 92 } },
      },
      ...(showSecondLevelActivity || showAtomicActivity ? [activityPackage11] : []),
      ...(showAtomicActivity ? [atomic21InPackage] : []),
    ].filter(Boolean),
    edges: [],
    summary: {
      ...graphResponse.summary,
      state_instance_count: stateExpanded ? 4 : 2,
      activity_node_count: 1 + (showSecondLevelActivity || showAtomicActivity ? 1 : 0) + (showAtomicActivity ? 1 : 0),
      edge_count: 0,
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

function statePackageResizeGraphResponse() {
  const state1 = graphResponse.state_nodes.find((node: any) => node.state_node_id === 1)
  const state3 = graphResponse.state_nodes.find((node: any) => node.state_node_id === 3)
  return {
    ...graphResponse,
    activity_nodes: [],
    edges: [],
    state_nodes: [
      {
        ...state1,
        metadata_json: {
          _network_editor_layout: { x: 80, y: 80 },
          _network_editor_container: { width: 520, height: 220 },
        },
      },
      {
        ...state3,
        metadata_json: { _network_editor_layout: { x: 430, y: 180 } },
      },
    ],
    summary: {
      ...graphResponse.summary,
      state_node_count: 2,
      state_instance_count: 2,
      activity_node_count: 0,
      executable_activity_count: 0,
      edge_count: 0,
    },
  }
}

function statePackageAutoArrangeGraphResponse() {
  const state1 = graphResponse.state_nodes.find((node: any) => node.state_node_id === 1)
  const baseChild = graphResponse.state_nodes.find((node: any) => node.state_node_id === 3)
  const childIds = [3, 5, 6, 7]
  return {
    ...graphResponse,
    activity_nodes: [],
    edges: [],
    state_nodes: [
      {
        ...state1,
        child_ids: childIds,
        leaf_state_ids: childIds,
        leaf_count: childIds.length,
        metadata_json: {
          _network_editor_layout: { x: 80, y: 80 },
          _network_editor_container: { width: 520, height: 170 },
        },
      },
      ...childIds.map((id, index) => ({
        ...baseChild,
        id: `state_node:${id}`,
        state_node_id: id,
        code: `STATE_WRAP_${index + 1}`,
        name: `换行状态${index + 1}`,
        sort_order: index + 1,
        leaf_state_ids: [id],
        path_ids: [1, id],
        metadata_json: { _network_editor_layout: { x: 110, y: 180 + index * 72 } },
      })),
    ],
    summary: {
      ...graphResponse.summary,
      state_node_count: 5,
      state_instance_count: 5,
      activity_node_count: 0,
      executable_activity_count: 0,
      edge_count: 0,
    },
  }
}

async function routeNetworkEditorFixture(page: any, options: {
  graphResponse?: any | ((request: any) => any)
  stateNodes?: any[]
  activityNodes?: any[]
  atomicActivities?: any[]
  opRules?: any[]
  bindings?: any[]
  stateReferences?: any[]
  activityPackageRefs?: any[] | ((request: any) => any[])
  validationResponse?: any | ((request: any) => any)
  onCommit?: (body: any, request: any) => any
} = {}) {
  const fixtureStateNodes = options.stateNodes || stateNodes
  const fixtureActivityNodes = options.activityNodes || activityNodes
  const fixtureAtomicActivities = options.atomicActivities || atomicActivities
  const fixtureOpRules = options.opRules || [
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
  ]
  const fixtureBindings = options.bindings || bindings
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
      await route.fulfill({ status: 200, body: JSON.stringify(fixtureStateNodes) })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/activity-nodes')) {
      await route.fulfill({ status: 200, body: JSON.stringify(fixtureActivityNodes) })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/atomic-activities')) {
      await route.fulfill({ status: 200, body: JSON.stringify(fixtureAtomicActivities) })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/state-node-references')) {
      await route.fulfill({ status: 200, body: JSON.stringify(options.stateReferences || []) })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/activity-state-bindings')) {
      await route.fulfill({ status: 200, body: JSON.stringify(fixtureBindings) })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/op-rules')) {
      await route.fulfill({
        status: 200,
        body: JSON.stringify(fixtureOpRules),
      })
      return
    }

    if (/\/api\/v1\/activity-nodes\/\d+\/atomic-activity-refs$/.test(url)) {
      const activityNodeId = Number(url.match(/\/activity-nodes\/(\d+)\/atomic-activity-refs$/)?.[1] || 0)
      const response = typeof options.activityPackageRefs === 'function'
        ? options.activityPackageRefs(request)
        : (options.activityPackageRefs || (activityNodeId === 10 ? activityPackageAtomicRefs : []))
      await route.fulfill({
        status: 200,
        body: JSON.stringify(response),
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

    if (url.endsWith('/api/v1/machine-types/1/network-editor/commit') && method === 'POST') {
      const body = JSON.parse(request.postData() || '{}')
      const response = options.onCommit
        ? options.onCommit(body, request)
        : {
            revision: 'fixture-revision-after-commit',
            applied_change_count: body.changes?.length || 0,
            changed_entities: [],
          }
      await route.fulfill({ status: 200, body: JSON.stringify(response) })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/network-editor/validate') && method === 'POST') {
      if (options.validationResponse) {
        const response = typeof options.validationResponse === 'function'
          ? options.validationResponse(request)
          : options.validationResponse
        await route.fulfill({ status: 200, body: JSON.stringify(response) })
        return
      }
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
  stateNodes?: any[]
  activityNodes?: any[]
  atomicActivities?: any[]
  opRules?: any[]
  bindings?: any[]
  stateReferences?: any[]
  activityPackageRefs?: any[] | ((request: any) => any[])
  onCommit?: (body: any, request: any) => any
  expectedRootStateId?: number
  expectInitialLeafNodes?: boolean
  expectActivityNodes?: boolean
} | null = null) {
  if (options) {
    await page.unroute(/\/(health|api\/v1\/)/)
    await routeNetworkEditorFixture(page, options)
  }
  await page.getByTestId('network-editor-machine-type-select').locator('.el-select__wrapper').click()
  await page.locator('.el-select-dropdown:visible .el-select-dropdown__item', { hasText: 'CNC Lathe (LATHE)' }).click()
  await expect(page.getByTestId('network-editor-canvas')).toBeVisible()
  await expect(page.getByTestId('network-editor-x6-canvas')).toBeVisible()
  await waitForNetworkEditorIdle(page)
  await expect(page.locator('.state-column')).toHaveCount(0)
  await expect(page.locator('.activity-column')).toHaveCount(0)
  await expect(page.getByTestId(`network-editor-state-node-${options?.expectedRootStateId || 1}`)).toBeVisible()
  await expect(page.getByTestId('network-editor-activity-node-activity_node:10')).toHaveCount(0)
  if (options?.expectInitialLeafNodes !== false) {
    const childState = page.getByTestId('network-editor-state-node-3')
    if (await childState.count() === 0) {
      const root = page.getByTestId('network-editor-state-node-1')
      await toggleStateExpansionAndWait(page, root.locator('[data-action="toggle"]'))
    }
    await expect(page.getByTestId('network-editor-state-node-3')).toBeVisible()
  }
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

async function resizeContainerBy(page: any, container: any, dx: number, dy: number) {
  await dragLocatorBy(page, container.locator('.container-resize-handle'), dx, dy)
  await waitForNetworkEditorIdle(page)
  await page.waitForTimeout(120)
}

async function leftDragCanvasPanBy(page: any, locator: any, dx: number, dy: number, position = { x: 0.5, y: 0.5 }) {
  const canvas = page.getByTestId('network-editor-x6-canvas')
  await locator.scrollIntoViewIfNeeded()
  const box = await locatorClientRect(locator, { preferOwnRect: true })
  const canvasBox = await locatorClientRect(canvas, { preferOwnRect: true })
  const visibleLeft = Math.max(box.x, canvasBox.x + 8)
  const visibleTop = Math.max(box.y, canvasBox.y + 8)
  const visibleRight = Math.min(box.x + box.width, canvasBox.x + canvasBox.width - 8)
  const visibleBottom = Math.min(box.y + box.height, canvasBox.y + canvasBox.height - 8)
  expect(visibleRight).toBeGreaterThan(visibleLeft)
  expect(visibleBottom).toBeGreaterThan(visibleTop)
  const startX = visibleLeft + (visibleRight - visibleLeft) * position.x
  const startY = visibleTop + (visibleBottom - visibleTop) * position.y
  await page.mouse.move(startX, startY)
  await page.mouse.down({ button: 'left' })
  await page.waitForTimeout(180)
  await expect(canvas).not.toHaveClass(/is-canvas-panning/)
  await page.mouse.move(startX + dx, startY + dy, { steps: 12 })
  await expect(canvas).toHaveClass(/is-canvas-panning/)
  await page.mouse.up({ button: 'left' })
  await expect(canvas).not.toHaveClass(/is-canvas-panning/)
  await expect(page.getByTestId('network-editor-blank-context-menu')).toHaveCount(0)
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

function rectsOverlap(a: any, b: any) {
  return a.x < b.x + b.width &&
    a.x + a.width > b.x &&
    a.y < b.y + b.height &&
    a.y + a.height > b.y
}

function expectRectToContain(outer: any, inner: any, tolerance = 2) {
  expect(inner.x).toBeGreaterThanOrEqual(outer.x - tolerance)
  expect(inner.y).toBeGreaterThanOrEqual(outer.y - tolerance)
  expect(inner.x + inner.width).toBeLessThanOrEqual(outer.x + outer.width + tolerance)
  expect(inner.y + inner.height).toBeLessThanOrEqual(outer.y + outer.height + tolerance)
}

async function readPackageProxyGeometry(page: any, packageIds: number[]) {
  return page.getByTestId('network-editor-x6-canvas').evaluate((canvas: HTMLElement, ids: number[]) => {
    const rectValue = (rect: DOMRect) => ({
      x: rect.x,
      y: rect.y,
      width: rect.width,
      height: rect.height,
      right: rect.right,
      bottom: rect.bottom,
    })
    const nodeRects = ids.map((id) => {
      const node = canvas.querySelector(`[data-testid="network-editor-state-node-${id}"]`)
      const cell = node?.closest('[data-cell-id]') || node
      if (!cell) throw new Error(`Missing package node ${id}`)
      return {
        id: `state_node:${id}`,
        ...rectValue(cell.getBoundingClientRect()),
      }
    })
    const routeViolations: any[] = []
    const routeKinds: string[] = []
    const paths = Array.from(canvas.querySelectorAll<SVGPathElement>('path[data-flow-role="proxy"]'))
    for (const path of paths) {
      const sourceId = String(path.getAttribute('data-source-id') || '')
      const targetId = String(path.getAttribute('data-target-id') || '')
      routeKinds.push(String(path.getAttribute('data-flow-route') || ''))
      const length = path.getTotalLength()
      const matrix = path.getScreenCTM()
      if (!matrix || !Number.isFinite(length)) continue
      for (let distance = 2; distance < length - 2; distance += 4) {
        const point = path.getPointAtLength(distance)
        const screenPoint = {
          x: point.x * matrix.a + point.y * matrix.c + matrix.e,
          y: point.x * matrix.b + point.y * matrix.d + matrix.f,
        }
        for (const rect of nodeRects) {
          if (rect.id === sourceId || rect.id === targetId) continue
          if (
            screenPoint.x > rect.x + 1 &&
            screenPoint.x < rect.right - 1 &&
            screenPoint.y > rect.y + 1 &&
            screenPoint.y < rect.bottom - 1
          ) {
            routeViolations.push({ sourceId, targetId, obstacleId: rect.id, screenPoint })
            distance = length
            break
          }
        }
      }
    }
    const labelRects = Array.from(canvas.querySelectorAll<SVGGElement>('.x6-edge-label'))
      .map((label) => ({
        ...rectValue(label.getBoundingClientRect()),
        edgeId: label.closest('[data-cell-id]')?.getAttribute('data-cell-id') || '',
        transform: label.getAttribute('transform') || '',
      }))
      .filter((rect) => rect.width > 0 && rect.height > 0)
    const labelViolations = labelRects.flatMap((label, labelIndex) =>
      nodeRects
        .filter((node) => (
          label.x < node.right &&
          label.right > node.x &&
          label.y < node.bottom &&
          label.bottom > node.y
        ))
        .map((node) => ({ labelIndex, nodeId: node.id, label, node })),
    )
    const rows: any[][] = []
    for (const rect of [...nodeRects].sort((a, b) => a.y - b.y || a.x - b.x)) {
      const centerY = rect.y + rect.height / 2
      const row = rows.find((items) => Math.abs((items[0].y + items[0].height / 2) - centerY) < 24)
      if (row) row.push(rect)
      else rows.push([rect])
    }
    const horizontalGaps = rows.flatMap((row) => {
      const sorted = [...row].sort((a, b) => a.x - b.x)
      return sorted.slice(1).map((rect, index) => rect.x - sorted[index].right)
    })
    const sortedRows = rows
      .map((row) => ({ top: Math.min(...row.map((rect) => rect.y)), bottom: Math.max(...row.map((rect) => rect.bottom)) }))
      .sort((a, b) => a.top - b.top)
    const verticalGaps = sortedRows.slice(1).map((row, index) => row.top - sortedRows[index].bottom)
    return {
      routeKinds,
      routeViolations,
      labelCount: labelRects.length,
      labelViolations,
      horizontalGaps,
      verticalGaps,
    }
  }, packageIds)
}

async function openCreateMenuItem(page: any, testId: string) {
  await page.getByTestId('network-editor-create-menu').click()
  const item = page.getByTestId(testId).last()
  await expect(item).toBeVisible()
  await item.click()
}

async function readEditorLayoutMetrics(page: any) {
  await expect(page.getByTestId('network-editor-x6-canvas')).toBeVisible()
  return page.getByTestId('network-editor').evaluate((root: HTMLElement) => {
    const workspace = root.querySelector('.workspace-body')?.getBoundingClientRect()
    const resource = root.querySelector('[data-testid="network-editor-resource-pane"]')?.getBoundingClientRect()
    const canvas = root.querySelector('[data-testid="network-editor-canvas-pane"]')?.getBoundingClientRect()
    const properties = root.querySelector('[data-testid="network-editor-properties-pane"]')?.getBoundingClientRect()
    const wrapper = root.querySelector('[data-testid="network-editor-canvas"]')?.getBoundingClientRect()
    const x6Canvas = root.querySelector('[data-testid="network-editor-x6-canvas"]')?.getBoundingClientRect()
    const validationPane = root.querySelector('[data-testid="network-editor-validation-pane"]')
    return {
      workspaceWidth: workspace?.width || 0,
      resourceWidth: resource?.width || 0,
      canvasWidth: canvas?.width || 0,
      canvasHeight: canvas?.height || 0,
      propertiesWidth: properties?.width || 0,
      wrapperWidth: wrapper?.width || 0,
      wrapperHeight: wrapper?.height || 0,
      x6Width: x6Canvas?.width || 0,
      x6Height: x6Canvas?.height || 0,
      legacyCanvasCount: root.querySelectorAll('[data-testid="network-editor-legacy-canvas"]').length,
      validationExpanded: !!validationPane,
    }
  })
}

async function clickAndWaitForGraphReload(page: any, action: () => Promise<void>) {
  await Promise.all([
    page.waitForResponse((response: any) =>
      response.url().includes('/api/v1/machine-types/1/network-editor/graph') &&
      response.request().method() === 'POST',
    ),
    action(),
  ])
  await waitForNetworkEditorIdle(page)
}

async function openBlankCreateMenuItem(page: any, itemIndex: number) {
  const canvas = page.getByTestId('network-editor-x6-canvas')
  await canvas.click({ button: 'right', position: { x: 520, y: 220 } })
  const menu = page.getByTestId('network-editor-blank-context-menu')
  await expect(menu).toBeVisible()
  await menu.locator('button').nth(itemIndex).click()
}

async function toggleStateExpansionAndWait(page: any, locator: any) {
  await locator.click()
  await waitForNetworkEditorIdle(page)
  await page.waitForTimeout(80)
}

async function pressActionAndWaitForGraphReloadWithoutTemporaryConnection(page: any, locator: any) {
  await pressActionWithoutTemporaryConnection(page, locator)
  await waitForNetworkEditorIdle(page)
  await page.waitForTimeout(80)
}

async function pressActionWithoutTemporaryConnection(page: any, locator: any) {
  await locator.scrollIntoViewIfNeeded()
  const box = await locator.boundingBox()
  expect(box).toBeTruthy()
  if (!box) throw new Error('Missing action button bounds')
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down({ button: 'left' })
  await page.waitForTimeout(120)
  await expect(page.locator('[data-cell-id="temporary-connection-preview"]')).toHaveCount(0)
  await page.mouse.up({ button: 'left' })
  await expect(page.locator('[data-cell-id="temporary-connection-preview"]')).toHaveCount(0)
  await expect(page.locator('[data-cell-id^="pending-binding-preview"]')).toHaveCount(0)
}

async function waitForNetworkEditorIdle(page: any) {
  await expect(page.getByTestId('network-editor-canvas-pane').locator('.el-loading-mask:visible')).toHaveCount(0)
}

async function chooseStateKind(drawer: any, kind: 'aggregate' | 'atomic') {
  const index = kind === 'aggregate' ? 0 : 1
  await drawer.getByTestId('network-editor-state-kind-segmented').locator('.el-segmented__item').nth(index).click()
}

async function fillAtomicStateFact(page: any, drawer: any, featureKey: string, targetValue = 'true') {
  await chooseElSelectOption(page, drawer.getByTestId('network-editor-state-feature'), templateFeatureKey(featureKey))
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

test.describe('Network Editor state-transition MVP', () => {
  test.beforeEach(async ({ page }) => {
    await routeNetworkEditorFixture(page)
    await page.goto('/')
    await page.waitForSelector('.el-header', { timeout: 10000 })
    await page.locator('.el-tabs__item:has-text("网络编辑器")').click()
    await expect(page.getByTestId('network-editor')).toBeVisible()
  })

  test('defaults to state cards and edits realizer/precondition through unified draft submit', async ({ page }) => {
    const commitBodies: any[] = []
    await openNetworkEditorFixture(page, {
      expectActivityNodes: false,
      onCommit: (body: any) => {
        commitBodies.push(body)
        return {
          machine_type_id: 1,
          revision: 'state-transition-after-commit',
          applied_change_count: body.changes?.length || 0,
          results: [],
          validation: null,
        }
      },
    })

    await expect(page.getByTestId('network-editor-view-mode')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-activity-node-activity_node:10')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-activity-node-atomic_activity:20')).toHaveCount(0)
    const doneStateNode = page.getByTestId('network-editor-state-node-4')
    await expect(doneStateNode).toContainText('AA_FINISH')
    await expect(doneStateNode).toContainText('前置')
    await expect(doneStateNode).not.toContainText('STATE_DONE')
    await expect(doneStateNode.locator('.node-code')).toHaveCount(0)
    await expect(doneStateNode.locator('.node-meta')).toHaveCount(0)
    const doneStateBox = await locatorClientRect(doneStateNode, { preferOwnRect: true })
    expect(doneStateBox.width).toBeLessThanOrEqual(260)
    expect(doneStateBox.height).toBeLessThanOrEqual(68)
    const initialStateNode = page.getByTestId('network-editor-state-node-5')
    await expect(initialStateNode).toContainText('起始条件')
    await expect(initialStateNode).not.toContainText('待补达成活动')
    const initialStateBox = await locatorClientRect(initialStateNode, { preferOwnRect: true })
    expect(initialStateBox.width).toBeLessThanOrEqual(260)
    expect(initialStateBox.height).toBeLessThanOrEqual(60)

    await page.getByTestId('network-editor-state-node-4').click()
    const transitionDetail = page.getByTestId('network-editor-state-transition-detail')
    await expect(transitionDetail).toBeVisible()
    await expect(transitionDetail).toHaveAttribute('data-display-state-graph-id', 'state_node:4')
    await expect(transitionDetail).toHaveAttribute('data-canonical-state-id', '4')
    await expect(transitionDetail).toHaveAttribute('data-source-status', 'committed')
    await expect(page.getByTestId('network-editor-activity-node-atomic_activity:20')).toHaveCount(0)
    await expect(transitionDetail).toContainText('AA_FINISH')
    await expect(page.getByTestId('network-editor-transition-precondition-5')).toContainText('INPUT_1')

    await page.getByTestId('network-editor-enter-edit').click()
    await page.getByTestId('network-editor-transition-remove-precondition-5').click()
    await expect(page.getByTestId('network-editor-transition-precondition-5')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()

    await chooseElSelectOption(page, page.getByTestId('network-editor-transition-precondition-select'), 'PKG_READY')
    await page.getByTestId('network-editor-transition-add-precondition').click()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()
    await expect(transitionDetail).toHaveAttribute('data-source-status', 'draft')

    await chooseElSelectOption(page, page.getByTestId('network-editor-transition-realizer-select'), 'AA_ALT')
    await page.getByTestId('network-editor-transition-add-realizer').click()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()

    await page.getByTestId('network-editor-submit-draft').click()
    await expect.poll(() => commitBodies.length).toBe(1)
    const bindingChanges = commitBodies[0].changes.filter((change: any) => change.entity_type === 'activity_state_binding')
    expect(bindingChanges).toEqual(expect.arrayContaining([
      expect.objectContaining({
        operation: 'delete',
        entity_id: 200,
      }),
      expect.objectContaining({
        operation: 'create',
        payload: expect.objectContaining({
          atomic_activity_id: 20,
          state_node_id: 1,
          binding_role: 'input',
          covered_leaf_state_ids: expect.arrayContaining([3]),
        }),
      }),
      expect.objectContaining({
        operation: 'create',
        payload: expect.objectContaining({
          atomic_activity_id: 21,
          state_node_id: 4,
          binding_role: 'output',
        }),
      }),
    ]))
  })

  test('projects referenced atomic library states after expanding their package with transition details', async ({ page }) => {
    const referencedAtomicState = {
      id: 30,
      machine_type_id: 1,
      parent_id: null,
      level: 1,
      code: 'REF_READY_TRUE',
      name: 'Referenced ready true',
      state_kind: 'atomic',
      feature_key: concreteFeatureKey('draft_atomic_option', 'referenced ready'),
      operator: 'eq',
      target_value: 'true',
      sort_order: 3,
      is_active: true,
      metadata_json: stateTemplateMetadata('draft_atomic_option', 'referenced ready', {
        _network_editor_layout: { x: 20, y: 20 },
      }),
    }
    const referencedStateRef = {
      id: 901,
      state_node_id: 30,
      parent_state_node_id: 4,
      sort_order: 1,
      is_active: true,
      metadata_json: { _network_editor_layout: { x: 136, y: 520 } },
      state_node_code: 'REF_READY_TRUE',
      state_node_name: 'Referenced ready true',
      parent_state_node_code: 'STATE_DONE',
      parent_state_node_name: 'State done',
      created_at: new Date().toISOString(),
    }
    const referencedOutputBinding = {
      id: 301,
      machine_type_id: 1,
      activity_node_id: null,
      atomic_activity_id: 20,
      op_rule_id: 900,
      state_node_id: 30,
      binding_role: 'output',
      binding_type: 'direct',
      coverage_policy: 'explicit',
      covered_leaf_state_ids: [30],
      coverage_status: 'complete',
      is_inherited: false,
      is_active: true,
      metadata_json: null,
    }
    const referencedBaseNode = graphNodeForStateFixture(referencedAtomicState, {
      reference_parent_ids: [4],
      reference_ids: [901],
      metadata_json: stateTemplateMetadata('draft_atomic_option', 'referenced ready', {
        _network_editor_layout: { x: 20, y: 20 },
      }),
    })
    const referencedInstanceNode = {
      ...referencedBaseNode,
      id: 'state_node:30:ref:901',
      parent_id: 4,
      primary_parent_graph_id: 'state_node:4',
      reference_parent_ids: [4],
      reference_ids: [901],
      path_ids: [4, 30],
      metadata_json: { _network_editor_layout: { x: 136, y: 520 } },
      reference_id: 901,
      is_reference_instance: true,
      reference_parent_id: 4,
    }

    await openNetworkEditorFixture(page, {
      stateNodes: [...stateNodes, referencedAtomicState],
      stateReferences: [referencedStateRef],
      bindings: [...bindings, referencedOutputBinding],
      graphResponse: {
        ...graphResponse,
        state_nodes: [
          ...graphResponse.state_nodes,
          referencedBaseNode,
          referencedInstanceNode,
        ],
        bindings: [...graphResponse.bindings, referencedOutputBinding],
        edges: [
          ...graphResponse.edges,
          {
            id: 'binding:301:ACTIVITY_TO_STATE',
            source_id: 'atomic_activity:20',
            target_id: 'state_node:30:ref:901',
            canonical_target_id: 'state_node:30',
            type: 'ACTIVITY_TO_STATE',
            binding_id: 301,
            binding_role: 'output',
            source_kind: 'activity_state_binding',
            coverage_status: 'complete',
          },
        ],
      },
      expectActivityNodes: false,
    })

    const referencedNode = page.getByTestId('network-editor-state-node-30')
    await expect(referencedNode).toBeHidden()
    const containingPackage = page.getByTestId('network-editor-state-node-4')
    await toggleStateExpansionAndWait(page, containingPackage.locator('[data-action="toggle"]'))
    await expect(referencedNode).toHaveCount(1)
    await expect(referencedNode).toContainText('Referenced ready true')
    await expect(referencedNode).toContainText('AA_FINISH')

    await referencedNode.click()
    const referencedDetail = page.getByTestId('network-editor-state-transition-detail')
    await expect(referencedDetail).toHaveAttribute('data-display-state-graph-id', 'state_node:30:ref:901')
    await expect(referencedDetail).toHaveAttribute('data-canonical-state-id', '30')
    await expect(referencedDetail).toContainText('AA_FINISH')
    await expect(page.getByTestId('network-editor-transition-precondition-5')).toContainText('INPUT_1')
  })

  test('keeps transition editor populated when the projected graph is activity-scoped away', async ({ page }) => {
    await openNetworkEditorFixture(page, {
      graphResponse: {
        ...graphResponse,
        activity_nodes: [],
        bindings: [],
        edges: [],
        summary: {
          ...graphResponse.summary,
          activity_node_count: 0,
          executable_activity_count: 0,
          edge_count: 0,
          binding_count: 0,
        },
      },
      expectActivityNodes: false,
    })

    await expect(page.getByTestId('network-editor-state-node-4')).toContainText('AA_FINISH')
    await page.getByTestId('network-editor-state-node-4').click()
    await expect(page.getByTestId('network-editor-state-transition-detail')).toContainText('AA_FINISH')
    await expect(page.getByTestId('network-editor-transition-precondition-5')).toContainText('INPUT_1')

    await page.getByTestId('network-editor-enter-edit').click()
    await expectElSelectHasOption(page, page.getByTestId('network-editor-transition-realizer-select'), 'AA_ALT')
    await expectElSelectHasOption(page, page.getByTestId('network-editor-transition-precondition-select'), 'PKG_READY')
  })

  test('shows flow backbone and active paths without creating drafts', async ({ page }) => {
    const unrelatedInputBinding = {
      id: 260,
      machine_type_id: 1,
      activity_node_id: null,
      atomic_activity_id: 21,
      op_rule_id: null,
      state_node_id: 3,
      binding_role: 'input',
      binding_type: 'direct',
      coverage_policy: 'explicit',
      covered_leaf_state_ids: [3],
      coverage_status: 'complete',
      is_inherited: false,
      is_active: true,
      metadata_json: null,
    }
    const unrelatedOutputBinding = {
      id: 261,
      machine_type_id: 1,
      activity_node_id: null,
      atomic_activity_id: 21,
      op_rule_id: null,
      state_node_id: 2,
      binding_role: 'output',
      binding_type: 'direct',
      coverage_policy: 'explicit',
      covered_leaf_state_ids: [2],
      coverage_status: 'complete',
      is_inherited: false,
      is_active: true,
      metadata_json: null,
    }
    const flowBindings = [...bindings, unrelatedInputBinding, unrelatedOutputBinding]
    const flowGraphResponse = {
      ...graphResponse,
      state_nodes: [
        ...graphResponse.state_nodes,
        graphNodeForStateFixture(reflexiveReadyFalseState, {
          metadata_json: { _network_editor_layout: { x: 90, y: 700 } },
        }),
      ],
      bindings: flowBindings,
      edges: [
        ...graphResponse.edges,
        {
          id: 'binding:260:STATE_TO_ACTIVITY',
          source_id: 'state_node:3',
          target_id: 'atomic_activity:21',
          type: 'STATE_TO_ACTIVITY',
          binding_id: 260,
          binding_role: 'input',
          source_kind: 'activity_state_binding',
          coverage_status: 'complete',
        },
        {
          id: 'binding:261:ACTIVITY_TO_STATE',
          source_id: 'atomic_activity:21',
          target_id: 'state_node:2',
          type: 'ACTIVITY_TO_STATE',
          binding_id: 261,
          binding_role: 'output',
          source_kind: 'activity_state_binding',
          coverage_status: 'complete',
        },
      ],
      summary: {
        ...graphResponse.summary,
        state_node_count: graphResponse.summary.state_node_count + 1,
        state_instance_count: graphResponse.summary.state_instance_count + 1,
        edge_count: graphResponse.summary.edge_count + 2,
        binding_count: (graphResponse.summary.binding_count || bindings.length) + 2,
      },
    }

    await openNetworkEditorFixture(page, {
      graphResponse: flowGraphResponse,
      bindings: flowBindings,
      expectActivityNodes: false,
    })

    const flowLines = page.locator('[data-testid="network-editor-flow-edge-line"]')
    await expect.poll(() => flowLines.count()).toBeGreaterThan(0)
    const relayNodes = page.getByTestId('network-editor-transition-relay-node')
    const finishRelay = relayNodes.filter({ hasText: 'AA_FINISH' }).first()
    await expect.poll(() => relayNodes.count()).toBeGreaterThan(0)
    await expect(finishRelay).toBeVisible()
    const relayOwnBox = await locatorClientRect(finishRelay, { preferOwnRect: true })
    expect(relayOwnBox.width).toBeLessThanOrEqual(150)
    expect(relayOwnBox.height).toBeLessThanOrEqual(50)
    const relayTooltip = finishRelay.locator('.relay-tooltip')
    await expect(relayTooltip).toHaveCSS('opacity', '0')
    await finishRelay.hover()
    await expect(relayTooltip).toContainText('AA_FINISH')
    await expect(relayTooltip).toHaveCSS('opacity', '1')
    await page.mouse.move(4, 4)
    await expect(page.locator('[data-flow-role="transition"]')).toHaveCount(0)
    const preconditionPaths = page.locator('[data-flow-role="precondition"]')
    const realizerPaths = page.locator('[data-flow-role="realizer"]')
    await expect.poll(() => preconditionPaths.count()).toBeGreaterThan(0)
    await expect.poll(() => realizerPaths.count()).toBeGreaterThan(0)
    await expect(preconditionPaths.first()).toHaveAttribute('data-source-side', 'right')
    await expect(preconditionPaths.first()).toHaveAttribute('data-target-side', 'left')
    await expect(page.getByTestId('network-editor-activity-node-atomic_activity:20')).toHaveCount(0)

    await page.getByTestId('network-editor-state-node-4').click()
    await expect(page.getByTestId('network-editor-activity-node-atomic_activity:20')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-state-transition-detail')).toContainText('AA_FINISH')
    await expect.poll(() => page.locator('[data-flow-state="active"]').count()).toBeGreaterThan(0)
    await expect.poll(() => page.locator('[data-flow-state="muted"]').count()).toBeGreaterThan(0)
    const inputStatePosition = await readCanvasPosition(page.getByTestId('network-editor-state-node-5'))
    const relayPosition = await readCanvasPosition(finishRelay)
    expect(Number.isFinite(inputStatePosition.x)).toBe(true)
    expect(Number.isFinite(relayPosition.x)).toBe(true)
    await expect(page.locator('[data-flow-route="join"], [data-flow-route="corridor"]')).toHaveCount(0)

    await finishRelay.click()
    await expect(finishRelay).toHaveClass(/selected/)
    await expect(page.locator('.detail-block').first()).toContainText('AA_FINISH')

    await page.getByTestId('network-editor-enter-edit').click()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeDisabled()
    await expect(page.locator('.draft-change-list')).toHaveCount(0)
  })

  test('auto arrange alternates state columns with transition relay columns', async ({ page }) => {
    await openNetworkEditorFixture(page, { expectActivityNodes: false, expectInitialLeafNodes: false })

    await page.getByTestId('network-editor-enter-edit').click()
    const sourceState = page.getByTestId('network-editor-state-node-5')
    const targetState = page.getByTestId('network-editor-state-node-4')
    const finishRelay = page.getByTestId('network-editor-transition-relay-node').filter({ hasText: 'AA_FINISH' }).first()
    await expect(finishRelay).toBeVisible()

    await page.getByTestId('network-editor-more-actions').click()
    await page.getByTestId('network-editor-auto-arrange').click()
    await waitForNetworkEditorIdle(page)
    await page.waitForTimeout(160)

    const sourcePosition = await readCanvasPosition(sourceState)
    const relayPosition = await readCanvasPosition(finishRelay)
    const targetPosition = await readCanvasPosition(targetState)
    expect(relayPosition.x).toBeGreaterThan(sourcePosition.x + 120)
    expect(targetPosition.x).toBeGreaterThan(relayPosition.x + 32)
    expect(targetPosition.x - relayPosition.x).toBeLessThan(190)
    await expect.poll(() =>
      page.locator('[data-flow-route^="elk"][data-source-side="right"][data-target-side="left"]').count(),
    ).toBeGreaterThan(0)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()

    await Promise.all([
      page.waitForResponse((response: any) =>
        response.url().endsWith('/api/v1/machine-types/1/network-editor/commit') &&
        response.request().method() === 'POST',
      ),
      page.getByTestId('network-editor-submit-draft').click(),
    ])
    await waitForNetworkEditorIdle(page)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeHidden()
    await expect.poll(() =>
      page.locator('[data-flow-route^="elk"][data-source-side="right"][data-target-side="left"]').count(),
    ).toBeGreaterThan(0)
    const previewSourcePosition = await readCanvasPosition(sourceState)
    const previewRelayPosition = await readCanvasPosition(finishRelay)
    const previewTargetPosition = await readCanvasPosition(targetState)
    expect(Math.abs(previewSourcePosition.x - sourcePosition.x)).toBeLessThanOrEqual(2)
    expect(Math.abs(previewSourcePosition.y - sourcePosition.y)).toBeLessThanOrEqual(2)
    expect(Math.abs(previewRelayPosition.x - relayPosition.x)).toBeLessThanOrEqual(2)
    expect(Math.abs(previewRelayPosition.y - relayPosition.y)).toBeLessThanOrEqual(2)
    expect(Math.abs(previewTargetPosition.x - targetPosition.x)).toBeLessThanOrEqual(2)
    expect(Math.abs(previewTargetPosition.y - targetPosition.y)).toBeLessThanOrEqual(2)
  })

  test('auto arrange lays out long state transition ranks left to right', async ({ page }) => {
    await openNetworkEditorFixture(page, {
      graphResponse: wrappedFlowGraphResponseForRequest,
      stateNodes: [...stateNodes, ...wrappedFlowStateNodes],
      bindings: wrappedFlowBindings,
      expectActivityNodes: false,
      expectInitialLeafNodes: false,
    })

    await page.getByTestId('network-editor-enter-edit').click()
    const packageNode = page.getByTestId('network-editor-state-node-4')
    await toggleStateExpansionAndWait(page, packageNode.locator('[data-action="toggle"]'))
    await expect(page.getByTestId('network-editor-state-package-container-4')).toBeVisible()

    await page.getByTestId('network-editor-more-actions').click()
    await page.getByTestId('network-editor-auto-arrange').click()
    await waitForNetworkEditorIdle(page)
    await page.waitForTimeout(160)

    const step1 = page.getByTestId('network-editor-state-node-50')
    const step2 = page.getByTestId('network-editor-state-node-51')
    const step3 = page.getByTestId('network-editor-state-node-52')
    const step4 = page.getByTestId('network-editor-state-node-53')
    const p1 = await readCanvasPosition(step1)
    const p2 = await readCanvasPosition(step2)
    const p3 = await readCanvasPosition(step3)
    const p4 = await readCanvasPosition(step4)
    expect(p2.x).toBeGreaterThan(p1.x + 120)
    expect(p3.x).toBeGreaterThan(p2.x + 120)
    expect(p4.x).toBeGreaterThan(p3.x + 120)
    await expect.poll(() => page.locator('[data-flow-route^="elk"]').count()).toBeGreaterThan(0)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()
  })

  test('summarizes folded package internal transitions without drawing self-loop proxies', async ({ page }) => {
    await openNetworkEditorFixture(page, {
      graphResponse: nestedForkJoinFlowGraphResponseForRequest,
      stateNodes: [...stateNodes, nestedForkJoinPackageState, ...nestedForkJoinFlowStateNodes],
      bindings: forkJoinFlowBindings,
      expectActivityNodes: false,
      expectInitialLeafNodes: false,
    })

    const rootPackageNode = page.getByTestId('network-editor-state-node-4')
    await toggleStateExpansionAndWait(page, rootPackageNode.locator('[data-action="toggle"]'))
    await expect(page.getByTestId('network-editor-state-package-container-4')).toBeVisible()
    const packageNode = page.getByTestId('network-editor-state-node-70')
    await expect(packageNode).toBeVisible()
    await expect(page.getByTestId('network-editor-state-node-60')).toBeHidden()
    await expect(page.locator('[data-flow-role="proxy"]')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-transition-relay-node')).toHaveCount(0)

    const expandAllButton = page.getByTestId('network-editor-filter-strip').getByText('展开全部', { exact: true })
    await clickAndWaitForGraphReload(page, () => expandAllButton.click())
    await expect(page.getByTestId('network-editor-state-node-60')).toBeVisible()
    await expect.poll(() => page.locator('[data-flow-role="proxy"]').count()).toBe(0)
  })

  test('aggregates high-parallel hidden transitions into eight package proxy edges', async ({ page }) => {
    await openNetworkEditorFixture(page, {
      graphResponse: packageAggregationGraphResponseForRequest,
      stateNodes: [
        packageAggregationRootState,
        packageAggregationPeerRootState,
        ...packageAggregationPackageStates,
        ...packageAggregationLeafStates,
      ],
      activityNodes: [],
      atomicActivities: packageAggregationAtomicActivities,
      opRules: packageAggregationOpRules,
      bindings: packageAggregationBindings,
      expectedRootStateId: 100,
      expectActivityNodes: false,
      expectInitialLeafNodes: false,
    })

    const root = page.getByTestId('network-editor-state-node-100')
    await toggleStateExpansionAndWait(page, root.locator('[data-action="toggle"]'))
    for (const packageId of packageAggregationPackageIds) {
      await expect(page.getByTestId(`network-editor-state-node-${packageId}`)).toBeVisible()
    }
    await expect(page.getByTestId('network-editor-transition-relay-node')).toHaveCount(0)
    await expect(page.locator('[data-flow-role="proxy"]')).toHaveCount(8)
    await expect(page.locator('[data-flow-role="proxy"][data-flow-route="obstacle"]')).toHaveCount(8)
    await expect(page.getByTestId('network-editor-x6-canvas').getByText('1 条转移', { exact: true })).toHaveCount(8)
    const geometry = await readPackageProxyGeometry(page, packageAggregationPackageIds)
    expect(geometry.routeKinds).toEqual(Array(8).fill('obstacle'))
    expect(geometry.routeViolations).toEqual([])
    expect(geometry.labelCount).toBe(8)
    expect(geometry.labelViolations).toEqual([])
    expect(Math.min(...geometry.horizontalGaps)).toBeGreaterThanOrEqual(88)
    expect(Math.min(...geometry.verticalGaps)).toBeGreaterThanOrEqual(72)
  })

  test('expands nested state packages locally while preserving roots and siblings', async ({ page }) => {
    await openNetworkEditorFixture(page, {
      graphResponse: packageAggregationGraphResponseForRequest,
      stateNodes: [
        packageAggregationRootState,
        packageAggregationPeerRootState,
        ...packageAggregationPackageStates,
        ...packageAggregationLeafStates,
      ],
      activityNodes: [],
      atomicActivities: packageAggregationAtomicActivities,
      opRules: packageAggregationOpRules,
      bindings: packageAggregationBindings,
      expectedRootStateId: 100,
      expectActivityNodes: false,
      expectInitialLeafNodes: false,
    })

    const root = page.getByTestId('network-editor-state-node-100')
    const peerRoot = page.getByTestId('network-editor-state-node-170')
    const expandedPackage = page.getByTestId('network-editor-state-node-120')
    const leaf = page.getByTestId('network-editor-state-node-121')

    await expect(root).toBeVisible()
    await expect(peerRoot).toBeVisible()
    await expect(page.getByTestId('network-editor-state-node-110')).toBeHidden()

    await toggleStateExpansionAndWait(page, root.locator('[data-action="toggle"]'))
    for (const packageId of packageAggregationPackageIds) {
      await expect(page.getByTestId(`network-editor-state-node-${packageId}`)).toBeVisible()
    }
    await expect(peerRoot).toBeVisible()
    await expect(leaf).toBeHidden()

    await toggleStateExpansionAndWait(page, expandedPackage.locator('[data-action="toggle"]'))
    await expect(leaf).toBeVisible()
    await expect(page.getByTestId('network-editor-state-node-110')).toBeVisible()
    await expect(page.getByTestId('network-editor-state-node-160')).toBeVisible()
    await expect(peerRoot).toBeVisible()

    await toggleStateExpansionAndWait(page, expandedPackage.locator('[data-action="toggle"]'))
    await expect(leaf).toBeHidden()
    await expect(page.getByTestId('network-editor-state-node-110')).toBeVisible()
    await expect(peerRoot).toBeVisible()

    await toggleStateExpansionAndWait(page, root.locator('[data-action="toggle"]'))
    for (const packageId of packageAggregationPackageIds) {
      await expect(page.getByTestId(`network-editor-state-node-${packageId}`)).toBeHidden()
    }
    await expect(root).toBeVisible()
    await expect(peerRoot).toBeVisible()
  })

  test('anchors a high-parallel wide expanded child container while moving sibling packages clear', async ({ page }) => {
    await openNetworkEditorFixture(page, {
      graphResponse: packageAggregationWideChildGraphResponseForRequest,
      stateNodes: [
        packageAggregationRootState,
        packageAggregationPeerRootState,
        ...packageAggregationPackageStates,
        ...packageAggregationLeafStates,
        ...packageAggregationWideChildLeafStates,
      ],
      activityNodes: [],
      atomicActivities: [
        ...packageAggregationAtomicActivities,
        ...packageAggregationWideChildAtomicActivities,
      ],
      opRules: [
        ...packageAggregationOpRules,
        ...packageAggregationWideChildOpRules,
      ],
      bindings: [...packageAggregationBindings, ...packageAggregationWideChildBindings],
      expectedRootStateId: 100,
      expectActivityNodes: false,
      expectInitialLeafNodes: false,
    })

    await page.getByTestId('network-editor-enter-edit').click()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeDisabled()
    await expect(page.locator('.draft-change-list')).toHaveCount(0)

    const root = page.getByTestId('network-editor-state-node-100')
    await toggleStateExpansionAndWait(page, root.locator('[data-action="toggle"]'))
    const outerContainer = page.getByTestId('network-editor-state-package-container-100')
    const outerBeforeExpansion = await locatorClientRect(outerContainer)
    const outerBeforePosition = await readCanvasPosition(outerContainer)
    const siblingIds = packageAggregationPackageIds.filter((id) => id !== 120)
    const siblingPositions = new Map<number, { x: number; y: number }>()
    for (const siblingId of siblingIds) {
      siblingPositions.set(siblingId, await readCanvasPosition(page.getByTestId(`network-editor-state-node-${siblingId}`)))
    }

    const expandedPackage = page.getByTestId('network-editor-state-node-120')
    const expandedPackageBefore = await readCanvasPosition(expandedPackage)
    await toggleStateExpansionAndWait(page, expandedPackage.locator('[data-action="toggle"]'))
    const expandedLeaves = [
      packageAggregationLeafStates.find((state) => state.parent_id === 120),
      ...packageAggregationWideChildLeafStates,
    ].filter(Boolean)
    for (const leaf of expandedLeaves) {
      await expect(page.getByTestId(`network-editor-state-node-${leaf.id}`)).toBeVisible()
    }
    const relayNodes = page.getByTestId('network-editor-transition-relay-node')
    await expect(relayNodes).toHaveCount(9)

    const expandedContainer = page.getByTestId('network-editor-state-package-container-120')
    const containerPosition = await readCanvasPosition(expandedContainer)
    expect(Math.abs(containerPosition.x - expandedPackageBefore.x)).toBeLessThanOrEqual(2)
    expect(Math.abs(containerPosition.y - expandedPackageBefore.y)).toBeLessThanOrEqual(2)
    const containerBox = await locatorClientRect(expandedContainer)
    const outerExpandedBox = await locatorClientRect(outerContainer)
    expectRectToContain(outerExpandedBox, containerBox)
    expect(outerExpandedBox.width).toBeGreaterThan(outerBeforeExpansion.width + 100)
    for (const leaf of expandedLeaves) {
      expectRectToContain(
        containerBox,
        await locatorClientRect(page.getByTestId(`network-editor-state-node-${leaf.id}`)),
      )
    }
    const relayBoxes = await relayNodes.evaluateAll((elements: HTMLElement[]) => elements.map((element) => {
      const rect = element.getBoundingClientRect()
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
    }))
    for (const relayBox of relayBoxes) expectRectToContain(containerBox, relayBox)
    for (const siblingId of siblingIds) {
      const siblingBox = await locatorClientRect(page.getByTestId(`network-editor-state-node-${siblingId}`))
      expect(rectsOverlap(containerBox, siblingBox), `expanded container overlaps sibling ${siblingId}`).toBe(false)
    }

    await toggleStateExpansionAndWait(page, expandedPackage.locator('[data-action="toggle"]'))
    await expect(relayNodes).toHaveCount(0)
    const outerRestoredBox = await locatorClientRect(outerContainer)
    const outerRestoredPosition = await readCanvasPosition(outerContainer)
    expect(Math.abs(outerRestoredPosition.x - outerBeforePosition.x)).toBeLessThanOrEqual(2)
    expect(Math.abs(outerRestoredPosition.y - outerBeforePosition.y)).toBeLessThanOrEqual(2)
    expect(Math.abs(outerRestoredBox.width - outerBeforeExpansion.width)).toBeLessThanOrEqual(2)
    expect(Math.abs(outerRestoredBox.height - outerBeforeExpansion.height)).toBeLessThanOrEqual(2)
    for (const siblingId of siblingIds) {
      const restored = await readCanvasPosition(page.getByTestId(`network-editor-state-node-${siblingId}`))
      const before = siblingPositions.get(siblingId)!
      expect(Math.abs(restored.x - before.x)).toBeLessThanOrEqual(2)
      expect(Math.abs(restored.y - before.y)).toBeLessThanOrEqual(2)
    }
    await expect(page.getByTestId('network-editor-submit-draft')).toBeDisabled()
    await expect(page.locator('.draft-change-list')).toHaveCount(0)
  })

  test('auto arrange isolates an expanded target package and restores its parent layout', async ({ page }) => {
    let committedPayload: any = null
    const fixtureBindings = statePackageBindingRows('complete')
    await openNetworkEditorFixture(page, {
      graphResponse: (request: any) => statePackageBindingGraphResponseForRequest(request, fixtureBindings),
      stateNodes: statePackageBindingStates,
      activityNodes: [],
      atomicActivities: [statePackageBindingActivity],
      opRules: [statePackageBindingRule],
      bindings: fixtureBindings,
      expectedRootStateId: 200,
      expectActivityNodes: false,
      expectInitialLeafNodes: false,
      onCommit: (body: any) => {
        committedPayload = body
        return {
          revision: 'fixture-local-state-layout-commit',
          applied_change_count: body.changes?.length || 0,
          changed_entities: [],
        }
      },
    })

    const root = page.getByTestId('network-editor-state-node-200')
    const sourcePackage = page.getByTestId('network-editor-state-node-210')
    const targetPackage = page.getByTestId('network-editor-state-node-220')
    await toggleStateExpansionAndWait(page, root.locator('[data-action="toggle"]'))
    const rootBefore = await readCanvasPosition(root)
    const sourceBefore = await readCanvasPosition(sourcePackage)
    await toggleStateExpansionAndWait(page, targetPackage.locator('[data-action="toggle"]'))
    await expect(page.getByTestId('network-editor-state-node-221')).toBeVisible()

    await page.getByTestId('network-editor-enter-edit').click()
    await page.getByTestId('network-editor-more-actions').click()
    await page.getByTestId('network-editor-auto-arrange').click()
    await waitForNetworkEditorIdle(page)
    await page.waitForTimeout(160)

    const rootAfterArrange = await readCanvasPosition(root)
    const sourceAfterArrange = await readCanvasPosition(sourcePackage)
    expect(Math.abs(rootAfterArrange.x - rootBefore.x)).toBeLessThanOrEqual(2)
    expect(Math.abs(rootAfterArrange.y - rootBefore.y)).toBeLessThanOrEqual(2)
    expect(Math.abs(sourceAfterArrange.x - sourceBefore.x)).toBeLessThanOrEqual(2)
    expect(Math.abs(sourceAfterArrange.y - sourceBefore.y)).toBeLessThanOrEqual(2)

    const relay = page.getByTestId('network-editor-transition-relay-node').first()
    const targetContainer = page.getByTestId('network-editor-state-package-container-220')
    await expect(relay).toBeVisible()
    const relayBox = await locatorClientRect(relay, { preferOwnRect: true })
    const targetBox = await locatorClientRect(targetContainer)
    expect(relayBox.x).toBeGreaterThanOrEqual(targetBox.x - 2)
    expect(relayBox.y).toBeGreaterThanOrEqual(targetBox.y - 2)
    expect(relayBox.x + relayBox.width).toBeLessThanOrEqual(targetBox.x + targetBox.width + 2)
    expect(relayBox.y + relayBox.height).toBeLessThanOrEqual(targetBox.y + targetBox.height + 2)

    await toggleStateExpansionAndWait(page, targetPackage.locator('[data-action="toggle"]'))
    await expect(page.getByTestId('network-editor-state-node-221')).toBeHidden()
    const rootAfterCollapse = await readCanvasPosition(root)
    const sourceAfterCollapse = await readCanvasPosition(sourcePackage)
    expect(Math.abs(rootAfterCollapse.x - rootBefore.x)).toBeLessThanOrEqual(2)
    expect(Math.abs(rootAfterCollapse.y - rootBefore.y)).toBeLessThanOrEqual(2)
    expect(Math.abs(sourceAfterCollapse.x - sourceBefore.x)).toBeLessThanOrEqual(2)
    expect(Math.abs(sourceAfterCollapse.y - sourceBefore.y)).toBeLessThanOrEqual(2)
    await expect(page.locator('[data-flow-route^="elk"]')).toHaveCount(0)

    await page.getByTestId('network-editor-submit-draft').click()
    await waitForNetworkEditorIdle(page)
    expect(committedPayload).toBeTruthy()
    const changedStateIds = committedPayload.changes
      .filter((change: any) => change.entity_type === 'state_node')
      .map((change: any) => Number(change.entity_id))
    expect(changedStateIds).not.toContain(200)
    expect(changedStateIds).not.toContain(210)
    expect(changedStateIds.every((id: number) => [220, 221].includes(id))).toBe(true)
  })

  test('keeps a complete state package precondition as one semantic edge', async ({ page }) => {
    const fixtureBindings = statePackageBindingRows('complete')
    await openNetworkEditorFixture(page, {
      graphResponse: (request: any) => statePackageBindingGraphResponseForRequest(request, fixtureBindings),
      stateNodes: statePackageBindingStates,
      activityNodes: [],
      atomicActivities: [statePackageBindingActivity],
      opRules: [statePackageBindingRule],
      bindings: fixtureBindings,
      expectedRootStateId: 200,
      expectActivityNodes: false,
      expectInitialLeafNodes: false,
    })

    const root = page.getByTestId('network-editor-state-node-200')
    await toggleStateExpansionAndWait(page, root.locator('[data-action="toggle"]'))
    await expect(page.getByTestId('network-editor-state-node-210')).toBeVisible()
    await expect(page.getByTestId('network-editor-state-node-220')).toBeVisible()
    await expect(page.getByTestId('network-editor-transition-relay-node')).toHaveCount(0)
    await expect(page.locator('[data-flow-role="proxy"]')).toHaveCount(1)
    await expect(page.getByTestId('network-editor-x6-canvas').getByText(
      '1 条转移 · 状态包前置 · 全部 3/3',
      { exact: true },
    )).toBeVisible()

    const expandAllButton = page.getByTestId('network-editor-filter-strip').getByText('展开全部', { exact: true })
    await clickAndWaitForGraphReload(page, () => expandAllButton.click())
    await expect(page.getByTestId('network-editor-state-node-211')).toBeVisible()
    await expect(page.getByTestId('network-editor-state-node-221')).toBeVisible()
    await expect(page.getByTestId('network-editor-transition-relay-node')).toHaveCount(1)
    await expect(page.locator('[data-flow-role="proxy"]')).toHaveCount(0)
    await expect(page.locator('[data-flow-role="precondition"]')).toHaveCount(1)
    await expect(page.getByTestId('network-editor-x6-canvas').getByText(
      '状态包前置 · 全部 3/3',
      { exact: true },
    )).toBeVisible()
  })

  test('aggregates package and hidden atomic preconditions into one package proxy', async ({ page }) => {
    const baseBindings = statePackageBindingRows('complete')
    const fixtureBindings = [
      baseBindings[0],
      {
        id: 3202,
        machine_type_id: 1,
        activity_node_id: null,
        atomic_activity_id: 1200,
        op_rule_id: 2200,
        state_node_id: 211,
        binding_role: 'input',
        binding_type: 'atomic_state',
        coverage_policy: 'snapshot',
        covered_leaf_state_ids: [211],
        coverage_status: 'complete',
        is_inherited: false,
        is_active: true,
        metadata_json: null,
      },
      baseBindings[1],
    ]
    await openNetworkEditorFixture(page, {
      graphResponse: (request: any) => statePackageBindingGraphResponseForRequest(request, fixtureBindings),
      stateNodes: statePackageBindingStates,
      activityNodes: [],
      atomicActivities: [statePackageBindingActivity],
      opRules: [statePackageBindingRule],
      bindings: fixtureBindings,
      expectedRootStateId: 200,
      expectActivityNodes: false,
      expectInitialLeafNodes: false,
    })

    const root = page.getByTestId('network-editor-state-node-200')
    await toggleStateExpansionAndWait(page, root.locator('[data-action="toggle"]'))
    const proxy = page.locator('[data-flow-role="proxy"]')
    await expect(proxy).toHaveCount(1)
    await expect(proxy).toHaveAttribute('data-transition-count', '1')
    await expect(proxy).toHaveAttribute('data-dependency-count', '2')
    await expect(proxy).toHaveAttribute('data-package-binding-count', '1')
  })

  test('keeps an explicit state package output on the visible relay', async ({ page }) => {
    const fixtureBindings = statePackageOutputBindingRows()
    await openNetworkEditorFixture(page, {
      graphResponse: (request: any) => statePackageBindingGraphResponseForRequest(request, fixtureBindings),
      stateNodes: statePackageBindingStates,
      activityNodes: [],
      atomicActivities: [statePackageBindingActivity],
      opRules: [statePackageBindingRule],
      bindings: fixtureBindings,
      expectedRootStateId: 200,
      expectActivityNodes: false,
      expectInitialLeafNodes: false,
    })

    const root = page.getByTestId('network-editor-state-node-200')
    await toggleStateExpansionAndWait(page, root.locator('[data-action="toggle"]'))
    await expect(page.getByTestId('network-editor-transition-relay-node')).toHaveCount(1)
    await expect(page.locator('[data-flow-role="proxy"]')).toHaveCount(1)
    await expect(page.locator('[data-flow-role="realizer"]')).toHaveCount(1)
    await expect(page.getByTestId('network-editor-x6-canvas').getByText(
      '状态包产出 · 全部 1/1',
      { exact: true },
    )).toBeVisible()
  })

  for (const [coverageStatus, coverageLabel] of [
    ['partial', '部分成员'],
    ['stale', '覆盖已变更'],
  ] as const) {
    test(`shows ${coverageStatus} state package binding coverage on the package proxy`, async ({ page }) => {
      const fixtureBindings = statePackageBindingRows(coverageStatus)
      await openNetworkEditorFixture(page, {
        graphResponse: (request: any) => statePackageBindingGraphResponseForRequest(request, fixtureBindings),
        stateNodes: statePackageBindingStates,
        activityNodes: [],
        atomicActivities: [statePackageBindingActivity],
        opRules: [statePackageBindingRule],
        bindings: fixtureBindings,
        expectedRootStateId: 200,
        expectActivityNodes: false,
        expectInitialLeafNodes: false,
      })

      const root = page.getByTestId('network-editor-state-node-200')
      await toggleStateExpansionAndWait(page, root.locator('[data-action="toggle"]'))
      await expect(page.locator('[data-flow-role="proxy"]')).toHaveCount(1)
      await expect(page.getByTestId('network-editor-x6-canvas').getByText(
        `1 条转移 · 状态包前置 · ${coverageLabel} 2/3`,
        { exact: true },
      )).toBeVisible()
    })
  }

  test('auto arrange keeps ordinary state and transition relay chains compact', async ({ page }) => {
    await openNetworkEditorFixture(page, { expectActivityNodes: false, expectInitialLeafNodes: false })

    await page.getByTestId('network-editor-enter-edit').click()

    const inputState = page.getByTestId('network-editor-state-node-1')
    const activity = page.getByTestId('network-editor-transition-relay-node').filter({ hasText: 'AA_FINISH' }).first()
    const outputState = page.getByTestId('network-editor-state-node-4')
    await expect(activity).toBeVisible()

    await page.getByTestId('network-editor-more-actions').click()
    await page.getByTestId('network-editor-auto-arrange').click()
    await waitForNetworkEditorIdle(page)
    await page.waitForTimeout(160)

    const inputPosition = await readCanvasPosition(inputState)
    const activityPosition = await readCanvasPosition(activity)
    const outputPosition = await readCanvasPosition(outputState)
    const inputGap = activityPosition.x - inputPosition.x
    const outputGap = outputPosition.x - activityPosition.x
    expect(inputGap).toBeGreaterThan(120)
    expect(inputGap).toBeLessThan(560)
    expect(outputGap).toBeGreaterThan(80)
    expect(outputGap).toBeLessThan(390)
    expect(Math.abs(activityPosition.y - ((inputPosition.y + outputPosition.y) / 2))).toBeLessThan(170)
    await expect.poll(() =>
      page.locator('[data-flow-route^="elk"][data-source-side="right"][data-target-side="left"]').count(),
    ).toBeGreaterThan(0)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()
  })

  test('auto arrange falls back when ELK layout fails', async ({ page }) => {
    await page.addInitScript(() => {
      ;(window as any).__NETWORK_EDITOR_FORCE_ELK_FAILURE__ = true
      window.localStorage.setItem('networkEditor.forceElkFailure', '1')
    })
    await openNetworkEditorFixture(page, { expectActivityNodes: false, expectInitialLeafNodes: false })
    await page.evaluate(() => {
      ;(window as any).__NETWORK_EDITOR_FORCE_ELK_FAILURE__ = true
      window.localStorage.setItem('networkEditor.forceElkFailure', '1')
    })

    await page.getByTestId('network-editor-enter-edit').click()
    await page.getByTestId('network-editor-more-actions').click()
    await page.getByTestId('network-editor-auto-arrange').click()
    await waitForNetworkEditorIdle(page)

    await expect(page.getByText('自动排布引擎暂不可用，已使用基础排布')).toBeVisible()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()
    await expect.poll(() =>
      page.locator('[data-flow-role="precondition"][data-source-side="right"][data-target-side="left"]').count(),
    ).toBeGreaterThan(0)
  })

  test('keeps preview relay chips from overlapping saved state cards', async ({ page }) => {
    const collisionGraphResponse = {
      ...graphResponse,
      state_nodes: graphResponse.state_nodes.map((node: any) =>
        node.state_node_id === 5
          ? {
              ...node,
              metadata_json: {
                ...(node.metadata_json || {}),
                _network_editor_layout: { x: 332, y: 76 },
              },
            }
          : node,
      ),
    }

    await openNetworkEditorFixture(page, {
      graphResponse: collisionGraphResponse,
      expectActivityNodes: false,
    })

    const collidingState = page.getByTestId('network-editor-state-node-5')
    const finishRelay = page.getByTestId('network-editor-transition-relay-node').filter({ hasText: 'AA_FINISH' }).first()
    await expect(collidingState).toBeVisible()
    await expect(finishRelay).toBeVisible()

    const stateBox = await locatorClientRect(collidingState, { preferOwnRect: true })
    const relayBox = await locatorClientRect(finishRelay, { preferOwnRect: true })
    expect(relayBox.width).toBeLessThanOrEqual(150)
    expect(relayBox.height).toBeLessThanOrEqual(50)
    expect(rectsOverlap(stateBox, relayBox)).toBe(false)
    expect(relayBox.y).toBeGreaterThan(stateBox.y + 20)
  })

  test('wraps expanded flow nodes into swimlanes without creating drafts', async ({ page }) => {
    await openNetworkEditorFixture(page, {
      graphResponse: wrappedFlowGraphResponseForRequest,
      stateNodes: [...stateNodes, ...wrappedFlowStateNodes],
      bindings: wrappedFlowBindings,
      expectActivityNodes: false,
      expectInitialLeafNodes: false,
    })

    await page.getByTestId('network-editor-enter-edit').click()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeDisabled()

    const packageNode = page.getByTestId('network-editor-state-node-4')
    await toggleStateExpansionAndWait(page, packageNode.locator('[data-action="toggle"]'))
    await expect(page.getByTestId('network-editor-state-package-container-4')).toBeVisible()

    const step1 = page.getByTestId('network-editor-state-node-50')
    const step2 = page.getByTestId('network-editor-state-node-51')
    const step3 = page.getByTestId('network-editor-state-node-52')
    const step4 = page.getByTestId('network-editor-state-node-53')
    const step5 = page.getByTestId('network-editor-state-node-54')
    await expect(step5).toBeVisible()

    const p1 = await readCanvasPosition(step1)
    const p2 = await readCanvasPosition(step2)
    const p3 = await readCanvasPosition(step3)
    const p4 = await readCanvasPosition(step4)
    const p5 = await readCanvasPosition(step5)
    expect(p2.x).toBeGreaterThan(p1.x + 120)
    expect(p3.x).toBeGreaterThan(p2.x + 120)
    expect(Math.abs(p2.y - p1.y)).toBeLessThan(wrappedFlowRowTolerance)
    expect(Math.abs(p3.y - p2.y)).toBeLessThan(wrappedFlowRowTolerance)
    expect(p4.x).toBeLessThan(p3.x - 120)
    expect(p4.y).toBeGreaterThan(p1.y + 64)
    expect(p5.x).toBeGreaterThan(p4.x + 120)
    expect(Math.abs(p5.y - p4.y)).toBeLessThan(wrappedFlowRowTolerance)

    const relayNodes = page.getByTestId('network-editor-transition-relay-node')
    await expect.poll(() => relayNodes.count()).toBeGreaterThan(0)
    await expect.poll(() =>
      page.locator('[data-flow-role="precondition"][data-source-side="right"][data-target-side="left"]').count(),
    ).toBeGreaterThan(0)
    await expect.poll(() =>
      page.locator('[data-flow-role="realizer"][data-source-side="right"][data-target-side="left"]').count(),
    ).toBeGreaterThan(0)
    await expect(page.locator('[data-flow-role="transition"]')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeDisabled()
    await expect(page.locator('.draft-change-list')).toHaveCount(0)

    await dragLocatorBy(page, step4.locator('.layout-handle'), 40, 18)
    await waitForNetworkEditorIdle(page)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()
    await expect(page.locator('.draft-change-list')).toHaveCount(1)
  })

  test('routes relay branch lines with ELK without creating duplicate paths', async ({ page }) => {
    await openNetworkEditorFixture(page, {
      graphResponse: forkJoinFlowGraphResponseForRequest,
      stateNodes: [...stateNodes, ...forkJoinFlowStateNodes],
      bindings: forkJoinFlowBindings,
      expectActivityNodes: false,
      expectInitialLeafNodes: false,
    })

    await page.getByTestId('network-editor-enter-edit').click()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeDisabled()

    const packageNode = page.getByTestId('network-editor-state-node-4')
    await toggleStateExpansionAndWait(page, packageNode.locator('[data-action="toggle"]'))
    await expect(page.getByTestId('network-editor-state-package-container-4')).toBeVisible()

    const frame = page.getByTestId('network-editor-state-node-60')
    const moduleA = page.getByTestId('network-editor-state-node-61')
    const moduleB = page.getByTestId('network-editor-state-node-62')
    const alignment = page.getByTestId('network-editor-state-node-63')
    await expect(alignment).toBeVisible()

    await page.getByTestId('network-editor-more-actions').click()
    await page.getByTestId('network-editor-auto-arrange').click()
    await waitForNetworkEditorIdle(page)
    await page.waitForTimeout(160)

    const framePosition = await readCanvasPosition(frame)
    const moduleAPosition = await readCanvasPosition(moduleA)
    const moduleBPosition = await readCanvasPosition(moduleB)
    const alignmentPosition = await readCanvasPosition(alignment)
    expect(moduleAPosition.x).toBeGreaterThan(framePosition.x + 120)
    expect(Math.abs(moduleBPosition.x - moduleAPosition.x)).toBeLessThan(24)
    expect(moduleBPosition.y).toBeGreaterThan(moduleAPosition.y + 50)
    expect(alignmentPosition.x).toBeGreaterThan(moduleAPosition.x + 120)

    const elkLines = page.locator('[data-flow-route^="elk"][data-source-side="right"][data-target-side="left"]')
    const resultLines = page.locator('[data-flow-role="realizer"][data-source-side="right"][data-target-side="left"]')
    await expect.poll(() => elkLines.count()).toBeGreaterThanOrEqual(4)
    await expect.poll(() => resultLines.count()).toBeGreaterThanOrEqual(2)
    const routePaths = await elkLines.evaluateAll((nodes: Element[]) =>
      nodes.map((node) => node.getAttribute('d') || '').filter(Boolean),
    )
    expect(new Set(routePaths).size).toBe(routePaths.length)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()
    await expect(page.locator('.draft-change-list')).not.toHaveCount(0)
  })

  test('automatically adds a reflexive precondition when binding a realizer', async ({ page }) => {
    const commitBodies: any[] = []
    await openNetworkEditorFixture(page, {
      expectActivityNodes: false,
      onCommit: (body: any) => {
        commitBodies.push(body)
        return {
          machine_type_id: 1,
          revision: 'auto-reflexive-after-commit',
          applied_change_count: body.changes?.length || 0,
          results: [],
          validation: null,
        }
      },
    })

    await page.getByTestId('network-editor-state-node-3').click()
    await page.getByTestId('network-editor-enter-edit').click()
    await chooseElSelectOption(page, page.getByTestId('network-editor-transition-realizer-select'), 'AA_ALT')
    await page.getByTestId('network-editor-transition-add-realizer').click()

    await expect(page.getByTestId('network-editor-transition-precondition-2')).toContainText('READY_FALSE')
    await expect(page.getByTestId('network-editor-state-node-3').locator('.node-transition-warnings')).toHaveCount(0)
    await page.getByTestId('network-editor-submit-draft').click()
    await expect.poll(() => commitBodies.length).toBe(1)

    const ruleChanges = commitBodies[0].changes.filter((change: any) => change.entity_type === 'op_rule')
    expect(ruleChanges).toEqual([
      expect.objectContaining({
        operation: 'create',
        payload: expect.objectContaining({
          atomic_activity_id: 21,
          preconditions: expect.arrayContaining([
            expect.objectContaining({ feature_key: reflexiveReadyFalseState.feature_key, feature_value: 'false' }),
          ]),
          effects: expect.arrayContaining([
            expect.objectContaining({ feature_key: stateNodes.find((state) => state.id === 3)?.feature_key, new_value: 'true' }),
          ]),
        }),
      }),
    ])
    const ruleDraftRef = { _draft_ref: ruleChanges[0].client_id }
    const bindingChanges = commitBodies[0].changes.filter((change: any) => change.entity_type === 'activity_state_binding')
    expect(bindingChanges).toEqual(expect.arrayContaining([
      expect.objectContaining({
        operation: 'create',
        payload: expect.objectContaining({
          atomic_activity_id: 21,
          op_rule_id: expect.objectContaining(ruleDraftRef),
          state_node_id: 3,
          binding_role: 'output',
        }),
      }),
      expect.objectContaining({
        operation: 'create',
        payload: expect.objectContaining({
          atomic_activity_id: 21,
          op_rule_id: expect.objectContaining(ruleDraftRef),
          state_node_id: 2,
          binding_role: 'input',
        }),
      }),
    ]))
  })

  test('does not duplicate an existing reflexive precondition', async ({ page }) => {
    const existingReflexiveBinding = {
      id: 180,
      machine_type_id: 1,
      activity_node_id: null,
      atomic_activity_id: 21,
      op_rule_id: null,
      state_node_id: 2,
      binding_role: 'input',
      binding_type: 'direct',
      coverage_policy: 'explicit',
      covered_leaf_state_ids: [2],
      coverage_status: 'complete',
      is_inherited: false,
      is_active: true,
      metadata_json: null,
    }
    const commitBodies: any[] = []
    await openNetworkEditorFixture(page, {
      bindings: [...bindings, existingReflexiveBinding],
      expectActivityNodes: false,
      onCommit: (body: any) => {
        commitBodies.push(body)
        return {
          machine_type_id: 1,
          revision: 'existing-reflexive-after-commit',
          applied_change_count: body.changes?.length || 0,
          results: [],
          validation: null,
        }
      },
    })

    await page.getByTestId('network-editor-state-node-3').click()
    await page.getByTestId('network-editor-enter-edit').click()
    await chooseElSelectOption(page, page.getByTestId('network-editor-transition-realizer-select'), 'AA_ALT')
    await page.getByTestId('network-editor-transition-add-realizer').click()
    await expect(page.getByTestId('network-editor-transition-precondition-2')).toContainText('READY_FALSE')
    await expect(page.getByTestId('network-editor-state-node-3').locator('.node-transition-warnings')).toHaveCount(0)

    await page.getByTestId('network-editor-submit-draft').click()
    await expect.poll(() => commitBodies.length).toBe(1)
    const ruleChanges = commitBodies[0].changes.filter((change: any) => change.entity_type === 'op_rule')
    expect(ruleChanges).toHaveLength(1)
    const ruleDraftRef = { _draft_ref: ruleChanges[0].client_id }
    const bindingCreates = commitBodies[0].changes.filter((change: any) =>
      change.entity_type === 'activity_state_binding' && change.operation === 'create',
    )
    const bindingUpdates = commitBodies[0].changes.filter((change: any) =>
      change.entity_type === 'activity_state_binding' && change.operation === 'update',
    )
    expect(bindingCreates.filter((change: any) =>
      change.payload.atomic_activity_id === 21 &&
      change.payload.state_node_id === 2 &&
      change.payload.binding_role === 'input',
    )).toHaveLength(0)
    expect(bindingCreates).toEqual(expect.arrayContaining([
      expect.objectContaining({
        payload: expect.objectContaining({
          atomic_activity_id: 21,
          op_rule_id: expect.objectContaining(ruleDraftRef),
          state_node_id: 3,
          binding_role: 'output',
        }),
      }),
    ]))
    expect(bindingUpdates).toEqual(expect.arrayContaining([
      expect.objectContaining({
        entity_id: 180,
        payload: expect.objectContaining({
          atomic_activity_id: 21,
          op_rule_id: expect.objectContaining(ruleDraftRef),
          state_node_id: 2,
          binding_role: 'input',
        }),
      }),
    ]))
  })

  test('does not re-add a reflexive precondition deleted in the same edit session', async ({ page }) => {
    const alternateReadyTargetState = {
      id: 12,
      machine_type_id: 1,
      parent_id: null,
      level: 3,
      code: 'READY_TRUE_TARGET',
      name: 'Ready flag true target',
      state_kind: 'atomic',
      feature_key: concreteFeatureKey('ready_flag', 'Ready flag true target'),
      operator: 'eq',
      target_value: 'true',
      sort_order: 20,
      is_active: true,
      metadata_json: stateTemplateMetadata('ready_flag', 'Ready flag true target', {
        _network_editor_layout: { x: 320, y: 230 },
      }),
    }
    const existingReflexiveBinding = {
      id: 180,
      machine_type_id: 1,
      activity_node_id: null,
      atomic_activity_id: 21,
      op_rule_id: null,
      state_node_id: 2,
      binding_role: 'input',
      binding_type: 'direct',
      coverage_policy: 'explicit',
      covered_leaf_state_ids: [2],
      coverage_status: 'complete',
      is_inherited: false,
      is_active: true,
      metadata_json: null,
    }
    const existingOutputBinding = {
      id: 181,
      machine_type_id: 1,
      activity_node_id: null,
      atomic_activity_id: 21,
      op_rule_id: null,
      state_node_id: 3,
      binding_role: 'output',
      binding_type: 'direct',
      coverage_policy: 'explicit',
      covered_leaf_state_ids: [3],
      coverage_status: 'complete',
      is_inherited: false,
      is_active: true,
      metadata_json: null,
    }
    const fixtureBindings = [...bindings, existingReflexiveBinding, existingOutputBinding]
    const commitBodies: any[] = []
    await openNetworkEditorFixture(page, {
      stateNodes: [...stateNodes, alternateReadyTargetState],
      bindings: fixtureBindings,
      graphResponse: {
        ...graphResponse,
        state_nodes: [...graphResponse.state_nodes, graphNodeForStateFixture(alternateReadyTargetState)],
        bindings: fixtureBindings,
      },
      expectActivityNodes: false,
      onCommit: (body: any) => {
        commitBodies.push(body)
        return {
          machine_type_id: 1,
          revision: 'deleted-reflexive-after-commit',
          applied_change_count: body.changes?.length || 0,
          results: [],
          validation: null,
        }
      },
    })

    await page.getByTestId('network-editor-state-node-3').click()
    await page.getByTestId('network-editor-enter-edit').click()
    await expect(page.getByTestId('network-editor-transition-precondition-2')).toContainText('READY_FALSE')
    await page.getByTestId('network-editor-transition-remove-precondition-2').click()
    await expect(page.getByTestId('network-editor-transition-precondition-2')).toHaveCount(0)

    await page.locator('.unplaced-row', { hasText: 'READY_TRUE_TARGET' }).click()
    await expect(page.getByTestId('network-editor-state-transition-detail')).toContainText('READY_TRUE_TARGET')
    await chooseElSelectOption(page, page.getByTestId('network-editor-transition-realizer-select'), 'AA_ALT')
    await expect(page.getByTestId('network-editor-transition-add-realizer')).toBeEnabled()
    await page.getByTestId('network-editor-transition-add-realizer').click()
    await expect(page.getByTestId('network-editor-transition-precondition-2')).toHaveCount(0)

    await page.getByTestId('network-editor-submit-draft').click()
    await expect.poll(() => commitBodies.length).toBe(1)
    const bindingChanges = commitBodies[0].changes.filter((change: any) => change.entity_type === 'activity_state_binding')
    expect(bindingChanges).toEqual(expect.arrayContaining([
      expect.objectContaining({ operation: 'delete', entity_id: 180 }),
      expect.objectContaining({
        operation: 'create',
        payload: expect.objectContaining({
          atomic_activity_id: 21,
          state_node_id: 12,
          binding_role: 'output',
        }),
      }),
    ]))
    expect(bindingChanges.filter((change: any) =>
      change.operation === 'create' &&
      change.payload?.atomic_activity_id === 21 &&
      change.payload?.state_node_id === 2 &&
      change.payload?.binding_role === 'input',
    )).toHaveLength(0)
  })

  test('new transition realizers save the reflexive precondition automatically', async ({ page }) => {
    const commitBodies: any[] = []
    await openNetworkEditorFixture(page, {
      expectActivityNodes: false,
      onCommit: (body: any) => {
        commitBodies.push(body)
        return {
          machine_type_id: 1,
          revision: 'new-reflexive-realizer-after-commit',
          applied_change_count: body.changes?.length || 0,
          results: [],
          validation: null,
        }
      },
    })

    await page.getByTestId('network-editor-state-node-3').click()
    await page.getByTestId('network-editor-enter-edit').click()
    await page.getByTestId('network-editor-transition-create-realizer').click()
    const atomicDrawer = page.getByTestId('network-editor-atomic-drawer')
    await expect(atomicDrawer).toBeVisible()
    await expect(atomicDrawer.getByTestId('network-editor-atomic-output-states')).toContainText('STATE_IN_READY')
    await atomicDrawer.locator('.el-form-item').nth(1).locator('input').fill('Auto reflexive realizer')
    await atomicDrawer.getByTestId('network-editor-atomic-drawer-save').click()
    await expect(atomicDrawer).toBeHidden()
    await expect(page.getByTestId('network-editor-state-transition-detail')).toContainText('Auto reflexive realizer')
    await expect(page.getByTestId('network-editor-state-transition-detail')).not.toContainText('待补达成活动')
    await expect(page.getByTestId('network-editor-transition-precondition-2')).toContainText('READY_FALSE')
    await expect(page.getByTestId('network-editor-activity-node-atomic_activity:draft-atomic-activity:draft-1')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-state-node-3')).not.toContainText('缺规则')

    await page.getByTestId('network-editor-submit-draft').click()
    await expect.poll(() => commitBodies.length).toBe(1)
    expect(commitBodies[0].changes.filter((change: any) => change.entity_type === 'activity_node')).toHaveLength(0)
    const atomicChanges = commitBodies[0].changes.filter((change: any) => change.entity_type === 'atomic_activity')
    expect(atomicChanges).toHaveLength(1)
    expect(atomicChanges[0].payload).not.toHaveProperty('package_id')
    const ruleChanges = commitBodies[0].changes.filter((change: any) => change.entity_type === 'op_rule')
    expect(ruleChanges).toEqual([
      expect.objectContaining({
        operation: 'create',
        payload: expect.objectContaining({
          atomic_activity_id: expect.objectContaining({ _draft_ref: 'draft-1' }),
          preconditions: expect.arrayContaining([
            expect.objectContaining({ feature_key: concreteFeatureKey('ready_flag', '包内原子状态'), feature_value: 'false' }),
          ]),
          effects: expect.arrayContaining([
            expect.objectContaining({ feature_key: concreteFeatureKey('ready_flag', '包内原子状态'), new_value: 'true' }),
          ]),
        }),
      }),
    ])
    const bindingChanges = commitBodies[0].changes.filter((change: any) => change.entity_type === 'activity_state_binding')
    expect(bindingChanges).toEqual(expect.arrayContaining([
      expect.objectContaining({
        operation: 'create',
        payload: expect.objectContaining({
          atomic_activity_id: expect.objectContaining({ _draft_ref: 'draft-1' }),
          op_rule_id: expect.objectContaining({ _draft_ref: 'draft-2' }),
          state_node_id: 2,
          binding_role: 'input',
        }),
      }),
      expect.objectContaining({
        operation: 'create',
        payload: expect.objectContaining({
          atomic_activity_id: expect.objectContaining({ _draft_ref: 'draft-1' }),
          op_rule_id: expect.objectContaining({ _draft_ref: 'draft-2' }),
          state_node_id: 3,
          binding_role: 'output',
        }),
      }),
    ]))
  })

  test('new transition realizers do not inherit the selected activity', async ({ page }) => {
    const commitBodies: any[] = []
    await page.goto('/')
    await page.waitForSelector('.el-header', { timeout: 10000 })
    await page.locator('.el-tabs__item:has-text("网络编辑器")').click()
    await expect(page.getByTestId('network-editor')).toBeVisible()
    await openNetworkEditorFixture(page, {
      onCommit: (body: any) => {
        commitBodies.push(body)
        return {
          machine_type_id: 1,
          revision: 'transition-realizer-package-inheritance-after-commit',
          applied_change_count: body.changes?.length || 0,
          results: [],
          validation: null,
        }
      },
    })

    await page.locator('[data-activity-graph-id="atomic_activity:20"]').click()
    await page.getByTestId('network-editor-state-node-3').click()
    await page.getByTestId('network-editor-enter-edit').click()
    await page.getByTestId('network-editor-transition-create-realizer').click()
    const atomicDrawer = page.getByTestId('network-editor-atomic-drawer')
    await expect(atomicDrawer).toBeVisible()
    await expect(atomicDrawer.getByTestId('network-editor-atomic-output-states')).toContainText('STATE_IN_READY')
    await atomicDrawer.locator('.el-form-item').nth(1).locator('input').fill('Detached transition realizer')
    await atomicDrawer.getByTestId('network-editor-atomic-drawer-save').click()
    await expect(atomicDrawer).toBeHidden()

    await page.getByTestId('network-editor-submit-draft').click()
    await expect.poll(() => commitBodies.length).toBe(1)
    expect(commitBodies[0].changes.filter((change: any) => change.entity_type === 'activity_node')).toHaveLength(0)
    const atomicChanges = commitBodies[0].changes.filter((change: any) => change.entity_type === 'atomic_activity')
    expect(atomicChanges).toHaveLength(1)
    expect(atomicChanges[0].payload).not.toHaveProperty('package_id')
    const ruleChanges = commitBodies[0].changes.filter((change: any) => change.entity_type === 'op_rule')
    expect(ruleChanges).toHaveLength(1)
    const bindingChanges = commitBodies[0].changes.filter((change: any) => change.entity_type === 'activity_state_binding')
    expect(bindingChanges).toEqual(expect.arrayContaining([
      expect.objectContaining({
        operation: 'create',
        payload: expect.objectContaining({
          atomic_activity_id: expect.objectContaining({ _draft_ref: 'draft-1' }),
          op_rule_id: expect.objectContaining({ _draft_ref: 'draft-2' }),
          state_node_id: 3,
          binding_role: 'output',
        }),
      }),
    ]))
  })
})

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
    await expect(page.getByTestId('network-editor-toolbar').locator('[data-testid="network-editor-create-state"]')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-create-menu')).toBeDisabled()
    const statePackageNode = page.getByTestId('network-editor-state-node-1')
    await expect(statePackageNode).toHaveCSS('border-radius', '5px')
    await expect(statePackageNode.locator('[data-action="create"]')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-zoom-reset')).toContainText('100%')
    await page.getByTestId('network-editor-zoom-in').click()
    await expect(page.getByTestId('network-editor-zoom-reset')).toContainText('110%')
    await page.getByTestId('network-editor-zoom-reset').click()
    await expect(page.getByTestId('network-editor-zoom-reset')).toContainText('100%')

    const x6Canvas = page.getByTestId('network-editor-x6-canvas')
    await expect(x6Canvas.getByText('历史状态包上下文 / 跨层级')).toHaveCount(0)

    await page.getByTestId('network-editor-enter-edit').click()
    await expect(page.getByTestId('network-editor-toolbar').getByText('编辑模式', { exact: true })).toBeVisible()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeVisible()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeDisabled()
    await expect(page.getByTestId('network-editor-create-menu')).toBeEnabled()
    await page.getByTestId('network-editor-create-menu').click()
    await expect(page.getByTestId('network-editor-create-state').last()).toBeVisible()
    await expect(page.getByTestId('network-editor-create-atomic').last()).toBeVisible()
    await page.keyboard.press('Escape')
    const statePackageCreate = statePackageNode.locator('[data-action="create"]')
    await expect(statePackageCreate).toHaveCSS('opacity', '0')
    await statePackageNode.hover()
    await expect(statePackageCreate).toHaveCSS('opacity', '1')
  })

  test('keeps the board dominant with collapsible side panes and collapsed validation details', async ({ page }) => {
    await openNetworkEditorFixture(page)
    const toolbar = page.getByTestId('network-editor-toolbar')
    await expect(toolbar.locator('[data-testid="network-editor-create-state"]')).toHaveCount(0)
    await expect(toolbar.locator('[data-testid="network-editor-create-activity"]')).toHaveCount(0)
    await expect(toolbar.locator('[data-testid="network-editor-create-atomic"]')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-canvas-pane')).toContainText('网络画板')
    await expect(page.getByText('二部图画布')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-x6-canvas')).toHaveCount(1)
    await expect(page.getByTestId('network-editor-legacy-canvas')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-validation-pane')).toHaveCount(0)

    const initialLayout = await readEditorLayoutMetrics(page)
    expect(initialLayout.validationExpanded).toBe(false)
    expect(initialLayout.legacyCanvasCount).toBe(0)
    expect(initialLayout.canvasWidth / initialLayout.workspaceWidth).toBeGreaterThan(0.45)
    expect(initialLayout.resourceWidth).toBeGreaterThan(230)
    expect(initialLayout.propertiesWidth).toBeGreaterThan(290)

    await dragLocatorBy(page, page.getByTestId('network-editor-resource-pane-resize'), 70, 0)
    await page.waitForTimeout(120)
    const resourceResizedLayout = await readEditorLayoutMetrics(page)
    expect(resourceResizedLayout.resourceWidth).toBeGreaterThan(initialLayout.resourceWidth + 40)

    await dragLocatorBy(page, page.getByTestId('network-editor-properties-pane-resize'), -80, 0)
    await page.waitForTimeout(120)
    const panesResizedLayout = await readEditorLayoutMetrics(page)
    expect(panesResizedLayout.propertiesWidth).toBeGreaterThan(resourceResizedLayout.propertiesWidth + 50)

    await page.getByTestId('network-editor-resource-pane-toggle').click()
    await page.getByTestId('network-editor-properties-pane-toggle').click()
    await page.waitForTimeout(120)
    const collapsedLayout = await readEditorLayoutMetrics(page)
    expect(collapsedLayout.canvasWidth).toBeGreaterThan(panesResizedLayout.canvasWidth + 160)
    expect(collapsedLayout.x6Width).toBeGreaterThanOrEqual(collapsedLayout.wrapperWidth - 4)
    expect(collapsedLayout.x6Height).toBeGreaterThanOrEqual(collapsedLayout.wrapperHeight - 4)
    expect(collapsedLayout.wrapperWidth).toBeGreaterThan(collapsedLayout.canvasWidth - 24)
    expect(collapsedLayout.legacyCanvasCount).toBe(0)
    await expect(page.getByTestId('network-editor-x6-canvas')).toBeVisible()

    await page.getByTestId('network-editor-validation-toggle').click()
    await expect(page.getByTestId('network-editor-validation-pane')).toBeVisible()
    await page.getByTestId('network-editor-validation-toggle').click()
    await expect(page.getByTestId('network-editor-validation-pane')).toHaveCount(0)
  })

  test('creates draft bindings from the editor form without canvas endpoints', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeVisible()

    const sourceState = page.getByTestId('network-editor-state-node-3')
    const targetActivity = page.getByTestId('network-editor-activity-node-atomic_activity:20')
    await expect(sourceState.locator('.semantic-port')).toHaveCount(0)
    await expect(targetActivity.locator('.semantic-port')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-create-selected-input-edge')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-create-selected-output-edge')).toHaveCount(0)

    await chooseElSelectOption(page, page.getByTestId('network-editor-binding-state'), 'STATE_IN_READY')
    await chooseElSelectOption(page, page.getByTestId('network-editor-binding-activity'), 'AA_FINISH')
    await expect(page.locator('[data-cell-id^="pending-binding-preview"]')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-create-binding')).toBeEnabled()

    await page.getByTestId('network-editor-create-binding').click()
    await expect(page.locator('[data-cell-id^="pending-binding-preview"]')).toHaveCount(0)

    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()
    await expect(page.locator('.draft-change-list')).toContainText('input')
    await expect(page.locator('.draft-change-list')).toContainText('STATE_IN_READY')
  })

  test('does not create pending bindings from canvas endpoint dragging', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeVisible()

    const sourceState = page.getByTestId('network-editor-state-node-3')
    const targetActivity = page.getByTestId('network-editor-activity-node-activity_node:10')
    await expect(sourceState.locator('.semantic-port')).toHaveCount(0)
    await expect(targetActivity.locator('.semantic-port')).toHaveCount(0)
    await expect(page.locator('[data-cell-id="temporary-connection-preview"]')).toHaveCount(0)
    await expect(page.locator('[data-cell-id^="pending-binding-preview"]')).toHaveCount(0)
    await expect(page.locator('[data-cell-id^="draft-binding"]')).toHaveCount(0)
  })

  test('deletes nodes into drafts and can undo draft changes', async ({ page }) => {
    await openNetworkEditorFixture(page)
    const committedState = page.getByTestId('network-editor-state-node-4')
    await committedState.click()
    await expect(page.getByTestId('network-editor-state-transition-detail')).toBeVisible()
    await page.getByTestId('network-editor-enter-edit').click()
    await expect(page.getByTestId('network-editor-delete-selected')).toBeEnabled()
    await page.getByTestId('network-editor-delete-selected').click()
    let dialog = page.locator('.el-message-box')
    await expect(dialog).toBeVisible()
    await dialog.locator('.el-button--primary').click()
    await expect(dialog).toBeHidden()
    await expect(committedState).toBeHidden()
    await expect(page.locator('.draft-change-list')).toContainText('删除')
    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()

    await page.getByTestId('network-editor-undo-draft-draft-1').click()
    await expect(committedState).toBeVisible()
    await expect(page.locator('.draft-change-list')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeDisabled()

    await openCreateMenuItem(page, 'network-editor-create-state')
    const drawer = page.getByTestId('network-editor-state-drawer')
    await expect(drawer).toBeVisible()
    await chooseStateKind(drawer, 'aggregate')
    await drawer.locator('.el-form-item').nth(1).locator('input').fill('Draft node to delete')
    await drawer.getByTestId('network-editor-state-drawer-save').click()
    await expect(drawer).toBeHidden()

    const draftState = page.getByTestId('network-editor-state-node-draft-state:draft-2')
    await expect(draftState).toBeVisible()
    await draftState.click()
    await expect(page.getByTestId('network-editor-delete-selected')).toBeEnabled()
    await page.getByTestId('network-editor-delete-selected').click()
    dialog = page.locator('.el-message-box')
    await expect(dialog).toBeVisible()
    await dialog.locator('.el-button--primary').click()
    await expect(dialog).toBeHidden()
    await expect(draftState).toBeHidden()
    await expect(page.locator('.draft-change-list')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeDisabled()
  })

  test('allows preview expand and collapse without exposing state-package write actions', async ({ page }) => {
    await openNetworkEditorFixture(page)
    const stateNode = page.getByTestId('network-editor-state-node-1')
    const statePackageContainer = page.getByTestId('network-editor-state-package-container-1')

    await expect(stateNode.getByText('添加状态', { exact: true })).toBeHidden()
    await expect(stateNode.getByText('折叠', { exact: true })).toBeVisible()
    await stateNode.getByText('折叠', { exact: true }).click()
    await expect(statePackageContainer).toBeHidden()
    await expect(stateNode.getByText('展开', { exact: true })).toBeVisible()
    await stateNode.getByText('展开', { exact: true }).click()
    await expect(stateNode.getByText('折叠', { exact: true })).toBeVisible()
    await expect(statePackageContainer).toBeVisible()
    await expect(stateNode).toContainText('准备状态包')
    await expect(statePackageContainer.locator('.node-code')).toHaveCount(0)
    await expect(statePackageContainer).not.toContainText('完成原子活动')
    await expect(page.getByTestId('network-editor-toolbar').getByText('预览模式', { exact: true })).toBeVisible()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeHidden()
  })

  test('does not start connection drag from edit-mode state package actions', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeVisible()

    const statePackage = page.getByTestId('network-editor-state-node-1')
    const stateContainer = page.getByTestId('network-editor-state-package-container-1')
    await expect(stateContainer).toBeVisible()
    await pressActionAndWaitForGraphReloadWithoutTemporaryConnection(page, statePackage.locator('[data-action="toggle"]'))
    await expect(stateContainer).toBeHidden()
    await toggleStateExpansionAndWait(page, statePackage.locator('[data-action="toggle"]'))
    await expect(stateContainer).toBeVisible()
    await expect(page.getByTestId('network-editor-state-node-3')).toBeVisible()
    await expect(page.locator('[data-cell-id="temporary-connection-preview"]')).toHaveCount(0)
    await expect(page.locator('[data-cell-id^="pending-binding-preview"]')).toHaveCount(0)
  })

  test('preserves independent state root expansion while toggling another root', async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('.el-header', { timeout: 10000 })
    await page.locator('.el-tabs__item:has-text("网络编辑器")').click()
    await expect(page.getByTestId('network-editor')).toBeVisible()
    await openNetworkEditorFixture(page, {
      graphResponse: independentStateRootsGraphResponseForRequest,
      expectActivityNodes: false,
      expectInitialLeafNodes: false,
    })

    const stateOne = page.getByTestId('network-editor-state-node-1')
    const stateDone = page.getByTestId('network-editor-state-node-4')
    const stateOneContainer = page.getByTestId('network-editor-state-package-container-1')
    const stateDoneContainer = page.getByTestId('network-editor-state-package-container-4')

    await toggleStateExpansionAndWait(page, stateOne.locator('[data-action="toggle"]'))
    await expect(stateOneContainer).toBeVisible()
    await expect(page.getByTestId('network-editor-state-node-3')).toBeVisible()

    await toggleStateExpansionAndWait(page, stateDone.locator('[data-action="toggle"]'))
    await expect(stateOneContainer).toBeVisible()
    await expect(page.getByTestId('network-editor-state-node-3')).toBeVisible()
    await expect(stateDoneContainer).toBeVisible()
    await expect(page.getByTestId('network-editor-state-node-40')).toBeVisible()

    await toggleStateExpansionAndWait(page, stateDone.locator('[data-action="toggle"]'))
    await expect(stateDoneContainer).toBeHidden()
    await expect(stateOneContainer).toBeVisible()
    await expect(page.getByTestId('network-editor-state-node-3')).toBeVisible()

    await toggleStateExpansionAndWait(page, stateDone.locator('[data-action="toggle"]'))
    await expect(stateDoneContainer).toBeVisible()
    await toggleStateExpansionAndWait(page, stateOne.locator('[data-action="toggle"]'))
    await expect(stateOneContainer).toBeHidden()
    await expect(stateDoneContainer).toBeVisible()
    await expect(page.getByTestId('network-editor-state-node-40')).toBeVisible()
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
    await page.getByTestId('network-editor-validation-toggle').click()

    const solverIssueTable = page.getByTestId('network-editor-solver-issues-table')
    await expect(solverIssueTable).toContainText('求解链路断裂')
    await expect(solverIssueTable).toContainText('完成原子活动')
    await solverIssueTable.getByTestId('network-editor-solver-issue-locate').click()
    await expect(page.locator('.detail-block').first()).toContainText('完成原子活动')
  })

  test('keeps validation issue locate on state side when issue also references an activity', async ({ page }) => {
    const graphRequestBodies: any[] = []
    const graphWithoutTargetState = {
      ...graphResponse,
      state_nodes: graphResponse.state_nodes.filter((node: any) => node.state_node_id !== 4),
    }
    await openNetworkEditorFixture(page, {
      graphResponse: (request: any) => {
        const body = JSON.parse(request.postData() || '{}')
        graphRequestBodies.push(body)
        if ((body.state_root_ids || []).some((id: any) => Number(id) === 4)) {
          return graphResponse
        }
        return graphWithoutTargetState
      },
      validationResponse: {
        status: 'blocked',
        summary: {
          modeling_issue_count: 1,
          solver_ready_issue_count: 0,
          blocking_count: 0,
          warning_count: 1,
          issue_count: 1,
        },
        modeling_issues: [
          {
            id: 'model:BINDING_COVERAGE_NOT_COMPLETE:state-first',
            code: 'BINDING_COVERAGE_NOT_COMPLETE',
            severity: 'warning',
            category: 'coverage',
            message: 'Binding coverage is stale',
            related_state_ids: [4],
            related_activity_ids: ['atomic_activity:20'],
            details: { binding_id: 101, coverage_status: 'stale' },
            suggested_action: 'Refresh coverage',
          },
        ],
        solver_ready_issues: [],
      },
    })

    await Promise.all([
      page.waitForResponse((response: any) =>
        response.url().includes('/api/v1/machine-types/1/network-editor/validate') &&
        response.request().method() === 'POST',
      ),
      page.getByTestId('network-editor-validate').click(),
    ])
    await page.getByTestId('network-editor-validation-toggle').click()

    const beforeLocate = graphRequestBodies.length
    const modelIssueTable = page.getByTestId('network-editor-model-issues-table')
    await Promise.all([
      page.waitForResponse((response: any) => {
        if (!response.url().includes('/api/v1/machine-types/1/network-editor/graph')) return false
        const body = JSON.parse(response.request().postData() || '{}')
        return (body.state_root_ids || []).some((id: any) => Number(id) === 4)
      }),
      modelIssueTable.getByTestId('network-editor-model-issue-locate').click(),
    ])

    const locateBodies = graphRequestBodies.slice(beforeLocate)
    expect(locateBodies.some((body) => (body.state_root_ids || []).some((id: any) => Number(id) === 4))).toBe(true)
    expect(locateBodies.some((body) => (body.activity_scope_node_ids || []).length > 0)).toBe(false)
    await expect(page.getByTestId('network-editor-properties-pane')).toContainText('STATE_DONE')
  })

  test('cancels edit session and restores submitted layout without committing drafts', async ({ page }) => {
    await openNetworkEditorFixture(page)
    const stateNode = page.getByTestId('network-editor-state-node-1')
    const childStateNode = page.getByTestId('network-editor-state-node-3')
    const submittedPosition = await readCanvasPosition(childStateNode)

    await page.getByTestId('network-editor-enter-edit').click()
    await expect(page.getByTestId('network-editor-toolbar').getByText('编辑模式', { exact: true })).toBeVisible()
    await stateNode.dblclick()
    const stateDrawer = page.getByTestId('network-editor-state-drawer')
    await expect(stateDrawer).toBeVisible()
    await stateDrawer.getByTestId('network-editor-state-drawer-cancel').click()
    await expect(stateDrawer).toBeHidden()
    await dragLocatorBy(page, childStateNode.locator('.layout-handle'), 48, 16)

    const draftedPosition = await readCanvasPosition(childStateNode)
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
    const restoredPosition = await readCanvasPosition(childStateNode)
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
    await openCreateMenuItem(page, 'network-editor-create-state')

    const drawer = page.getByTestId('network-editor-state-drawer')
    await expect(drawer).toBeVisible()
    await chooseStateKind(drawer, 'aggregate')
    await drawer.locator('.el-form-item').nth(1).locator('input').fill('一次性提交状态')
    await drawer.getByTestId('network-editor-state-drawer-save').click()

    await expect(drawer).toBeHidden()
    await expect(page.locator('.draft-change-list')).toContainText('新建状态：一次性提交状态')
    const draftedStateNode = page.getByTestId('network-editor-state-node-draft-state:draft-1')
    await expect(draftedStateNode).toBeVisible()
    await openCreateMenuItem(page, 'network-editor-create-state')
    await expect(drawer).toBeVisible()
    await chooseStateKind(drawer, 'aggregate')
    await drawer.locator('.el-form-item').nth(1).locator('input').fill('Draft child state')
    await drawer.getByTestId('network-editor-state-drawer-save').click()

    await expect(drawer).toBeHidden()
    await expect(page.locator('.draft-change-list')).toContainText('Draft child state')
    await openCreateMenuItem(page, 'network-editor-create-state')
    await expect(drawer).toBeVisible()
    await drawer.locator('.el-form-item').nth(1).locator('input').fill('Draft nested state')
    await fillAtomicStateFact(page, drawer, 'draft_nested_state')
    await drawer.getByTestId('network-editor-state-drawer-save').click()

    await expect(drawer).toBeHidden()
    await expect(page.locator('.draft-change-list')).toContainText('Draft nested state')
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
    expect(payload.changes).toHaveLength(5)
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
        parent_id: null,
        level: 1,
        state_kind: 'atomic',
        feature_key: concreteFeatureKey('draft_nested_state', 'Draft nested state'),
        target_value: 'true',
        metadata_json: {
          dimension_template_key: templateFeatureKey('draft_nested_state'),
          state_object_name: 'Draft nested state',
        },
      },
    })
    expect(payload.changes[3]).toMatchObject({
      entity_type: 'state_node_reference',
      operation: 'create',
      payload: {
        state_node_id: { _draft_ref: 'draft-3' },
        parent_state_node_id: { _draft_ref: 'draft-2' },
      },
    })
    expect(payload.changes[4]).toMatchObject({
      entity_type: 'state_node',
      operation: 'create',
      payload: {
        name: 'Draft nested state false',
        parent_id: null,
        level: 1,
        state_kind: 'atomic',
        feature_key: concreteFeatureKey('draft_nested_state', 'Draft nested state'),
        target_value: 'false',
      },
    })
    expect(commitRequests).toHaveLength(1)
    await expect(page.getByTestId('network-editor-toolbar').getByText('预览模式', { exact: true })).toBeVisible()
  })

  test('does not reuse a state solely because it has the same state dimension and value', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()

    await openCreateMenuItem(page, 'network-editor-create-state')
    const drawer = page.getByTestId('network-editor-state-drawer')
    await expect(drawer).toBeVisible()
    await drawer.locator('.el-form-item').nth(1).locator('input').fill('同维度不同名状态')
    await fillAtomicStateFact(page, drawer, 'ready_flag')
    await drawer.getByTestId('network-editor-state-drawer-save').click()

    await expect(drawer).toBeHidden()
    await expect(page.getByTestId('network-editor-duplicate-state-dialog')).toHaveCount(0)
    await expect(page.locator('.draft-change-list')).toContainText('新建状态：同维度不同名状态')
    await expect(page.locator('.draft-change-list')).toContainText('自动补齐相反状态')
    await expect(page.getByTestId('network-editor-state-node-draft-state:draft-1')).toBeVisible()
  })

  test('creates atomic state library objects with only the selected value referenced on canvas', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()

    await openCreateMenuItem(page, 'network-editor-create-state')
    const drawer = page.getByTestId('network-editor-state-drawer')
    await expect(drawer).toBeVisible()
    await chooseElSelectOption(
      page,
      drawer.getByTestId('network-editor-state-parent-select'),
      '跨层级目标状态',
    )
    await drawer.locator('.el-form-item').nth(1).locator('input').fill('Widget A true')
    await fillAtomicStateFact(page, drawer, 'draft_atomic_option', 'true')
    await drawer.getByTestId('network-editor-state-drawer-save').click()

    await expect(drawer).toBeHidden()
    await expect(page.locator('.draft-change-row')).toHaveCount(3)
    await expect(page.locator('.draft-change-list')).toContainText('Widget A true')
    await expect(page.locator('.draft-change-list')).toContainText('Widget A false')
    const selectedReference = page.getByTestId('network-editor-state-node-draft-state:draft-1').last()
    await expect(selectedReference).toBeVisible()
    await expect(selectedReference).toContainText('Widget A true')
    await expect(page.getByTestId('network-editor-state-node-draft-state:draft-3')).toHaveCount(0)

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
      entity_type: 'state_node',
      operation: 'create',
      payload: {
        name: 'Widget A true',
        parent_id: null,
        level: 1,
        state_kind: 'atomic',
        feature_key: concreteFeatureKey('draft_atomic_option', 'Widget A'),
        target_value: 'true',
        metadata_json: {
          dimension_template_key: templateFeatureKey('draft_atomic_option'),
          state_object_name: 'Widget A',
        },
      },
    })
    expect(payload.changes[1]).toMatchObject({
      entity_type: 'state_node_reference',
      operation: 'create',
      payload: {
        state_node_id: { _draft_ref: 'draft-1' },
        parent_state_node_id: 4,
        metadata_json: {
          _network_editor_reuse: { source: 'atomic_state_library_create' },
        },
      },
    })
    expect(payload.changes[2]).toMatchObject({
      entity_type: 'state_node',
      operation: 'create',
      payload: {
        name: 'Widget A false',
        parent_id: null,
        level: 1,
        state_kind: 'atomic',
        feature_key: concreteFeatureKey('draft_atomic_option', 'Widget A'),
        target_value: 'false',
        metadata_json: {
          dimension_template_key: templateFeatureKey('draft_atomic_option'),
          state_object_name: 'Widget A',
          _network_editor_auto_opposite: {
            source_target_value: 'true',
            source_state_name: 'Widget A true',
          },
        },
      },
    })
  })

  test('does not duplicate an existing opposite atomic state library value', async ({ page }) => {
    const existingOppositeState = {
      id: 80,
      machine_type_id: 1,
      parent_id: null,
      level: 1,
      code: 'WIDGET_B_FALSE',
      name: 'Widget B false',
      state_kind: 'atomic',
      feature_key: concreteFeatureKey('draft_atomic_option', 'Widget B'),
      operator: 'eq',
      target_value: 'false',
      sort_order: 80,
      is_active: true,
      metadata_json: stateTemplateMetadata('draft_atomic_option', 'Widget B'),
    }
    await openNetworkEditorFixture(page, { stateNodes: [...stateNodes, existingOppositeState] })
    await page.getByTestId('network-editor-enter-edit').click()

    await openCreateMenuItem(page, 'network-editor-create-state')
    const drawer = page.getByTestId('network-editor-state-drawer')
    await expect(drawer).toBeVisible()
    await chooseElSelectOption(
      page,
      drawer.getByTestId('network-editor-state-parent-select'),
      '跨层级目标状态',
    )
    await drawer.locator('.el-form-item').nth(1).locator('input').fill('Widget B true')
    await fillAtomicStateFact(page, drawer, 'draft_atomic_option', 'true')
    await drawer.getByTestId('network-editor-state-drawer-save').click()

    await expect(drawer).toBeHidden()
    await expect(page.locator('.draft-change-row')).toHaveCount(2)
    await expect(page.locator('.draft-change-list')).not.toContainText('Widget B false')
    await expect(page.getByTestId('network-editor-state-node-80')).toHaveCount(0)

    const [commitRequest] = await Promise.all([
      page.waitForRequest((request: any) =>
        request.url().endsWith('/api/v1/machine-types/1/network-editor/commit') &&
        request.method() === 'POST',
      ),
      page.getByTestId('network-editor-submit-draft').click(),
    ])
    const payload = JSON.parse(commitRequest.postData() || '{}')
    expect(payload.changes).toHaveLength(2)
    expect(payload.changes.filter((change: any) => change.entity_type === 'state_node')).toHaveLength(1)
    expect(payload.changes[0]).toMatchObject({
      entity_type: 'state_node',
      operation: 'create',
      payload: {
        name: 'Widget B true',
        parent_id: null,
        feature_key: concreteFeatureKey('draft_atomic_option', 'Widget B'),
        target_value: 'true',
      },
    })
    expect(payload.changes[1]).toMatchObject({
      entity_type: 'state_node_reference',
      operation: 'create',
      payload: {
        state_node_id: { _draft_ref: 'draft-1' },
        parent_state_node_id: 4,
      },
    })
  })

  test('searches existing atomic state names in the state drawer', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()

    await openCreateMenuItem(page, 'network-editor-create-state')
    const drawer = page.getByTestId('network-editor-state-drawer')
    await expect(drawer).toBeVisible()
    const nameInput = drawer.locator('.el-form-item').nth(1).locator('input')
    await nameInput.click()
    await nameInput.fill('包内')
    await expect(page.locator('.el-autocomplete-suggestion:visible li', { hasText: '包内原子状态' }).first()).toBeVisible()
  })

  test('reuses exact same-name template states instead of creating duplicates', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()

    await openCreateMenuItem(page, 'network-editor-create-state')
    const drawer = page.getByTestId('network-editor-state-drawer')
    await expect(drawer).toBeVisible()
    await drawer.locator('.el-form-item').nth(1).locator('input').fill('包内原子状态')
    await fillAtomicStateFact(page, drawer, 'ready_flag')
    await drawer.getByTestId('network-editor-state-drawer-save').click()
    await expect(drawer).toBeHidden()
    await expect(page.getByTestId('network-editor-duplicate-state-dialog')).toHaveCount(0)
    await expect(page.locator('.draft-change-list')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeDisabled()
    if (false) {
      {

    await expect(page.locator('.el-message', { hasText: '请引用' })).toContainText('STATE_IN_READY 包内原子状态')
    await expect(drawer).toBeVisible()
    await expect(page.getByTestId('network-editor-duplicate-state-dialog')).toHaveCount(0)
    await expect(page.locator('.draft-change-list')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeDisabled()
      }
    }
  })

  test('creates a state package reference when an exact template state is reused in another package', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()

    await openCreateMenuItem(page, 'network-editor-create-state')
    const drawer = page.getByTestId('network-editor-state-drawer')
    await expect(drawer).toBeVisible()
    await chooseElSelectOption(
      page,
      drawer.getByTestId('network-editor-state-parent-select'),
      '跨层级目标状态',
    )
    await drawer.locator('.el-form-item').nth(1).locator('input').fill('包内原子状态')
    await fillAtomicStateFact(page, drawer, 'ready_flag')
    await drawer.getByTestId('network-editor-state-drawer-save').click()
    await expect(drawer).toBeHidden()
    await expect(page.locator('.draft-change-list')).toContainText('STATE_IN_READY')
    const draftedRef = page.getByTestId('network-editor-state-node-3').last()
    await expect(draftedRef).toBeVisible()
    await expect(draftedRef).toHaveAttribute('title', /STATE_IN_READY/)

    const [commitRequest] = await Promise.all([
      page.waitForRequest((request: any) =>
        request.url().endsWith('/api/v1/machine-types/1/network-editor/commit') &&
        request.method() === 'POST',
      ),
      page.getByTestId('network-editor-submit-draft').click(),
    ])
    const payload = JSON.parse(commitRequest.postData() || '{}')
    expect(payload.changes).toHaveLength(1)
    expect(payload.changes[0]).toMatchObject({
      entity_type: 'state_node_reference',
      operation: 'create',
      payload: {
        state_node_id: 3,
        parent_state_node_id: 4,
      },
    })
    if (false) {

    await expect(page.locator('.el-message', { hasText: '请引用' })).toContainText('STATE_IN_READY 包内原子状态')
    await expect(drawer).toBeVisible()
    await expect(drawer.getByTestId('network-editor-state-reference-select')).toContainText('包内原子状态')
    await expect(page.locator('.draft-change-list')).toHaveCount(0)

    await drawer.getByTestId('network-editor-state-reference-add').click()
    await expect(drawer).toBeHidden()
    await expect(page.locator('.draft-change-list')).toContainText('复用状态：STATE_IN_READY 包内原子状态')
    const draftedRef = page.getByTestId('network-editor-state-node-3').last()
    await expect(draftedRef).toBeVisible()
    await expect(draftedRef).toContainText('包内原子状态')

    const [commitRequest] = await Promise.all([
      page.waitForRequest((request: any) =>
        request.url().endsWith('/api/v1/machine-types/1/network-editor/commit') &&
        request.method() === 'POST',
      ),
      page.getByTestId('network-editor-submit-draft').click(),
    ])
    const payload = JSON.parse(commitRequest.postData() || '{}')
    expect(payload.changes).toHaveLength(1)
    expect(payload.changes[0]).toMatchObject({
      entity_type: 'state_node_reference',
      operation: 'create',
      payload: {
        state_node_id: 3,
        parent_state_node_id: 4,
      },
    })
    }
  })

  test('lists draft states in the state reference entry and commits draft refs', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()

    await openCreateMenuItem(page, 'network-editor-create-state')
    const drawer = page.getByTestId('network-editor-state-drawer')
    await expect(drawer).toBeVisible()
    await drawer.locator('.el-form-item').nth(1).locator('input').fill('Session reusable true')
    await fillAtomicStateFact(page, drawer, 'draft_atomic_option')
    await drawer.getByTestId('network-editor-state-drawer-save').click()
    await expect(drawer).toBeHidden()
    await expect(page.locator('.draft-change-list')).toContainText('新建状态：Session reusable true')

    await openCreateMenuItem(page, 'network-editor-create-state')
    await expect(drawer).toBeVisible()
    await chooseElSelectOption(
      page,
      drawer.getByTestId('network-editor-state-parent-select'),
      '跨层级目标状态',
    )
    await chooseElSelectOption(
      page,
      drawer.getByTestId('network-editor-state-reference-select'),
      'Session reusable true',
    )
    await drawer.getByTestId('network-editor-state-reference-add').click()

    await expect(drawer).toBeHidden()
    await expect(page.locator('.draft-change-list')).toContainText('复用状态：Session reusable true')
    const draftedRef = page.getByTestId('network-editor-state-node-draft-state:draft-1').last()
    await expect(draftedRef).toBeVisible()
    await expect(draftedRef).toContainText('Session reusable true')

    const [commitRequest] = await Promise.all([
      page.waitForRequest((request: any) =>
        request.url().endsWith('/api/v1/machine-types/1/network-editor/commit') &&
        request.method() === 'POST',
      ),
      page.getByTestId('network-editor-submit-draft').click(),
    ])
    const payload = JSON.parse(commitRequest.postData() || '{}')
    expect(payload.changes).toHaveLength(4)
    expect(payload.changes[3]).toMatchObject({
      entity_type: 'state_node_reference',
      operation: 'create',
      payload: {
        state_node_id: { _draft_ref: 'draft-1' },
        parent_state_node_id: 4,
      },
    })
  })

  test('rejects exact same-name draft states in the same edit session', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()

    await openCreateMenuItem(page, 'network-editor-create-state')
    const drawer = page.getByTestId('network-editor-state-drawer')
    await expect(drawer).toBeVisible()
    await drawer.locator('.el-form-item').nth(1).locator('input').fill('会话内同名原子')
    await fillAtomicStateFact(page, drawer, 'draft_atomic_option')
    await drawer.getByTestId('network-editor-state-drawer-save').click()
    await expect(drawer).toBeHidden()
    await expect(page.locator('.draft-change-row')).toHaveCount(3)

    await openCreateMenuItem(page, 'network-editor-create-state')
    await expect(drawer).toBeVisible()
    await drawer.locator('.el-form-item').nth(1).locator('input').fill('会话内同名原子')
    await fillAtomicStateFact(page, drawer, 'input_1')
    await drawer.getByTestId('network-editor-state-drawer-save').click()

    await expect(page.locator('.el-message', { hasText: '请引用' })).toContainText('会话内同名原子')
    await expect(drawer).toBeVisible()
    await expect(page.getByTestId('network-editor-duplicate-state-dialog')).toHaveCount(0)
    await expect(page.locator('.draft-change-row')).toHaveCount(3)
    await expect(page.locator('.draft-change-list')).toContainText('新建状态：会话内同名原子')
  })

  test('fills atomic reference entry when same-name atomic activity is blocked', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()

    await openCreateMenuItem(page, 'network-editor-create-atomic')
    const atomicDrawer = page.getByTestId('network-editor-atomic-drawer')
    await expect(atomicDrawer).toBeVisible()
    await chooseElSelectOption(
      page,
      atomicDrawer.getByTestId('network-editor-atomic-package-select'),
      '准备活动包',
    )
    await atomicDrawer.locator('.el-form-item').nth(1).locator('input').fill('备用达成活动')
    await atomicDrawer.getByTestId('network-editor-atomic-drawer-save').click()

    await expect(page.locator('.el-message', { hasText: '请引用该原子活动' })).toContainText('AA_ALT 备用达成活动')
    await expect(atomicDrawer).toBeVisible()
    await expect(atomicDrawer.getByTestId('network-editor-atomic-reference-select')).toContainText('备用达成活动')
    await expect(page.locator('.draft-change-list')).toHaveCount(0)

    await atomicDrawer.getByTestId('network-editor-atomic-reference-add').click()
    await expect(atomicDrawer).toBeHidden()
    await expect(page.locator('.draft-change-list')).toContainText('引用原子活动：AA_ALT 备用达成活动')
    const draftedRef = page.getByTestId('network-editor-activity-node-atomic_activity:21:draft-ref:draft-1')
    await expect(draftedRef).toHaveCount(0)

    const [commitRequest] = await Promise.all([
      page.waitForRequest((request: any) =>
        request.url().endsWith('/api/v1/machine-types/1/network-editor/commit') &&
        request.method() === 'POST',
      ),
      page.getByTestId('network-editor-submit-draft').click(),
    ])
    const payload = JSON.parse(commitRequest.postData() || '{}')
    expect(payload.changes).toHaveLength(1)
    expect(payload.changes[0]).toMatchObject({
      entity_type: 'activity_package_atomic_ref',
      operation: 'create',
      payload: {
        package_id: 10,
        atomic_activity_id: 21,
      },
    })
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

    await openCreateMenuItem(page, 'network-editor-create-state')
    const stateDrawer = page.getByTestId('network-editor-state-drawer')
    await expect(stateDrawer).toBeVisible()
    await stateDrawer.locator('.el-form-item').nth(1).locator('input').fill('Draft atomic option true')
    await fillAtomicStateFact(page, stateDrawer, 'draft_atomic_option')
    await stateDrawer.getByTestId('network-editor-state-drawer-save').click()
    await expect(stateDrawer).toBeHidden()
    await expect(page.getByTestId('network-editor-state-node-draft-state:draft-1')).toBeVisible()

    await openCreateMenuItem(page, 'network-editor-create-atomic')
    const atomicDrawer = page.getByTestId('network-editor-atomic-drawer')
    await expect(atomicDrawer).toBeVisible()
    await expectElSelectHasOption(page, atomicDrawer.getByTestId('network-editor-atomic-input-states'), 'Draft atomic option true')
    await expectElSelectHasOption(page, atomicDrawer.getByTestId('network-editor-atomic-output-states'), 'Draft atomic option true')

    await atomicDrawer.locator('.el-form-item').nth(1).locator('input').fill('Atomic without boundary states')
    await atomicDrawer.getByTestId('network-editor-atomic-drawer-save').click()
    await expect(atomicDrawer).toBeHidden()
    await expect(page.locator('.draft-change-list')).toContainText('Atomic without boundary states')
    const draftAtomicActivity = page.getByTestId('network-editor-activity-node-atomic_activity:draft-atomic-activity:draft-3')
    await expect(draftAtomicActivity).toHaveCount(0)
    await expect(page.getByTestId('network-editor-state-node-draft-state:draft-1')).toBeVisible()
    await page.waitForTimeout(impactDebounceBufferMs)
    expect(JSON.stringify(impactPayloads)).not.toContain('draft-state:')
    expect(JSON.stringify(impactPayloads)).not.toContain('draft-atomic-activity:')

    await openCreateMenuItem(page, 'network-editor-create-atomic')
    await expect(atomicDrawer).toBeVisible()
    await atomicDrawer.locator('.el-form-item').nth(1).locator('input').fill('Atomic using draft states')
    await chooseElSelectOption(page, atomicDrawer.getByTestId('network-editor-atomic-input-states'), 'Draft atomic option true')
    await chooseElSelectOption(page, atomicDrawer.getByTestId('network-editor-atomic-output-states'), 'Draft atomic option true')
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
    expect(bindingChanges.length).toBeGreaterThanOrEqual(3)
    expect(bindingChanges).toEqual(expect.arrayContaining([
      expect.objectContaining({
        payload: expect.objectContaining({
          binding_role: 'input',
          state_node_id: { _draft_ref: 'draft-1' },
        }),
      }),
      expect.objectContaining({
        payload: expect.objectContaining({
          binding_role: 'input',
          state_node_id: { _draft_ref: 'draft-3' },
        }),
      }),
      expect.objectContaining({
        payload: expect.objectContaining({
          binding_role: 'output',
          state_node_id: { _draft_ref: 'draft-1' },
        }),
      }),
    ]))
    expect(payload.changes.some((change: any) =>
      change.entity_type === 'atomic_activity' &&
      change.payload.name === 'Atomic without boundary states',
    )).toBe(true)
  })

  test('writes package atomic ref layout drafts and redraws from commit reload', async ({ page }) => {
    let committed = false
    const beforeLayout = { x: 520, y: 260 }
    const afterLayout = { x: 660, y: 340 }
    const layoutBindings = bindings
      .filter((binding: any) => [100, 101].includes(Number(binding.id)))
      .map((binding: any) => Number(binding.id) === 100
        ? {
            ...binding,
            activity_node_id: null,
            atomic_activity_id: 20,
            binding_role: 'input',
          }
        : binding)
    const refWithLayout = (layout: any) => ({
      ...activityPackageAtomicRefs[0],
      metadata_json: {
        ...(activityPackageAtomicRefs[0].metadata_json || {}),
        _network_editor_layout: layout,
      },
    })
    const graphWithLayout = (layout: any, revision: string) => ({
      ...graphResponse,
      revision,
      bindings: layoutBindings,
      activity_nodes: graphResponse.activity_nodes.map((node: any) =>
        node.id === 'atomic_activity:20'
          ? {
              ...node,
              id: 'atomic_activity:20:ref:700',
              canonical_id: 'atomic_activity:20',
              is_reference_instance: true,
              reference_id: 700,
              reference_ids: [700],
              package_ref_ids: [700],
              parent_graph_id: 'activity_node:10',
              metadata_json: refWithLayout(layout).metadata_json,
              atomic_metadata_json: atomicActivities[0].metadata_json,
            }
          : node,
      ),
      edges: graphResponse.edges
        .filter((edge: any) => [100, 101].includes(Number(edge.binding_id)))
        .map((edge: any) => ({
        ...edge,
        binding_role: Number(edge.binding_id) === 100 ? 'input' : edge.binding_role,
        source_id: edge.source_id === 'atomic_activity:20'
          ? 'atomic_activity:20:ref:700'
          : edge.source_id,
        target_id: edge.target_id === 'atomic_activity:20' || Number(edge.binding_id) === 100
          ? 'atomic_activity:20:ref:700'
          : edge.target_id,
        canonical_source_id: edge.source_id === 'atomic_activity:20'
          ? 'atomic_activity:20'
          : edge.canonical_source_id,
        canonical_target_id: edge.target_id === 'atomic_activity:20' || Number(edge.binding_id) === 100
          ? 'atomic_activity:20'
          : edge.canonical_target_id,
      })),
    })

    await openNetworkEditorFixture(page, {
      graphResponse: () => graphWithLayout(
        committed ? afterLayout : beforeLayout,
        committed ? 'fixture-revision-after-layout-commit' : 'fixture-revision-before-layout-commit',
      ),
      bindings: layoutBindings,
      activityPackageRefs: () => [refWithLayout(committed ? afterLayout : beforeLayout)],
      onCommit: (body: any) => {
        committed = true
        return {
          revision: 'fixture-revision-after-layout-commit',
          applied_change_count: body.changes?.length || 0,
          changed_entities: ['activity_package_atomic_ref:700'],
        }
      },
    })
    await page.getByTestId('network-editor-enter-edit').click()

    const atomicActivity = page.locator(
      '[data-testid="network-editor-transition-relay-node"][data-activity-graph-id="atomic_activity:20:ref:700"]',
    )
    await expect(atomicActivity).toBeVisible()
    const atomicBefore = await readCanvasPosition(atomicActivity)
    await dragLocatorBy(page, atomicActivity, 72, 36)
    const atomicAfter = await readCanvasPosition(atomicActivity)

    const [commitRequest] = await Promise.all([
      page.waitForRequest((request: any) =>
        request.url().endsWith('/api/v1/machine-types/1/network-editor/commit') &&
        request.method() === 'POST',
      ),
      page.getByTestId('network-editor-submit-draft').click(),
    ])
    const payload = JSON.parse(commitRequest.postData() || '{}')
    const refChange = payload.changes.find((change: any) =>
      change.entity_type === 'activity_package_atomic_ref' &&
      change.operation === 'update' &&
      change.entity_id === 700,
    )
    expect(refChange).toBeTruthy()
    expect(refChange.payload).toMatchObject({
      atomic_activity_id: 20,
      sort_order: 1,
      is_active: true,
    })
    expect(refChange.payload.metadata_json._network_editor_layout.x).toBeGreaterThan(beforeLayout.x)
    expect(refChange.payload.metadata_json._network_editor_layout.y).toBeGreaterThan(beforeLayout.y)
    expect(payload.changes.some((change: any) =>
      change.entity_type === 'atomic_activity' && change.entity_id === 20,
    )).toBe(false)

    await waitForNetworkEditorIdle(page)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeHidden()
    await expect(atomicActivity).toBeVisible()
    const atomicPreview = await readCanvasPosition(atomicActivity)
    expect(Math.abs(atomicPreview.x - atomicAfter.x)).toBeLessThan(2)
    expect(Math.abs(atomicPreview.y - atomicAfter.y)).toBeLessThan(2)

    await page.getByTestId('network-editor-more-actions').click()
    await Promise.all([
      page.waitForResponse((response: any) =>
        response.url().endsWith('/api/v1/machine-types/1/network-editor/graph') &&
        response.request().method() === 'POST',
      ),
      page.getByTestId('network-editor-refresh').click(),
    ])
    await waitForNetworkEditorIdle(page)
    const atomicReloaded = await readCanvasPosition(atomicActivity)
    expect(atomicReloaded.x).toBeGreaterThan(atomicBefore.x + 90)
    expect(atomicReloaded.y).toBeGreaterThan(atomicBefore.y + 50)
  })

  test('keeps activity-package creation out of the graph create menu', async ({ page }) => {
    await openNetworkEditorFixture(page)
    await page.getByTestId('network-editor-enter-edit').click()
    await page.getByTestId('network-editor-create-menu').click()
    await expect(page.getByTestId('network-editor-create-activity')).toHaveCount(0)
    await expect(page.getByTestId('network-editor-create-state').last()).toBeVisible()
    await expect(page.getByTestId('network-editor-create-atomic').last()).toBeVisible()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeDisabled()
  })

  test('renders nested containers when adding a child under a referenced state package', async ({ page }) => {
    await openNetworkEditorFixture(page, {
      graphResponse: referencedStatePackageGraphResponse(),
      expectedRootStateId: 4,
      expectInitialLeafNodes: false,
    })
    await page.getByTestId('network-editor-enter-edit').click()

    const outerStateNode = page.getByTestId('network-editor-state-node-4')
    await outerStateNode.locator('[data-action="toggle"]').click()

    const outerContainer = page.getByTestId('network-editor-state-package-container-4')
    const referencedPackageContainer = page.getByTestId('network-editor-state-package-container-1')
    const referencedPackageNode = page.getByTestId('network-editor-state-node-1')
    await expect(outerContainer).toBeVisible()
    await referencedPackageNode.locator('[data-action="toggle"]').click()
    await expect(referencedPackageContainer).toBeVisible()
    await expect(referencedPackageNode).toContainText('准备状态包')

    const createChildButton = referencedPackageNode.locator('[data-action="create"]')
    await expect(createChildButton).toHaveCSS('opacity', '0')
    await referencedPackageNode.hover()
    await expect(createChildButton).toHaveCSS('opacity', '1')
    const createChildButtonBox = await locatorClientRect(createChildButton, { preferOwnRect: true })
    await page.mouse.move(
      createChildButtonBox.x + createChildButtonBox.width / 2,
      createChildButtonBox.y + createChildButtonBox.height / 2,
    )
    await expect(createChildButton).toHaveCSS('opacity', '1')
    await createChildButton.click()
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

  })

  test('container resize keeps an unsafe axis while applying a safe axis', async ({ page }) => {
    await openNetworkEditorFixture(page, {
      graphResponse: statePackageResizeGraphResponse(),
      expectActivityNodes: false,
      expectInitialLeafNodes: false,
    })
    await page.getByTestId('network-editor-enter-edit').click()

    const statePackageRoot = page.getByTestId('network-editor-state-node-1')
    await toggleStateExpansionAndWait(page, statePackageRoot.locator('[data-action="toggle"]'))
    const statePackageContainer = page.getByTestId('network-editor-state-package-container-1')
    await expect(statePackageContainer).toBeVisible()

    const before = await locatorClientRect(statePackageContainer)
    await resizeContainerBy(page, statePackageContainer, -180, 90)
    const afterHeightResize = await locatorClientRect(statePackageContainer)
    expect(afterHeightResize.width).toBeGreaterThanOrEqual(before.width - 3)
    expect(afterHeightResize.height).toBeGreaterThan(before.height + 50)

    await resizeContainerBy(page, statePackageContainer, 100, -180)
    const afterWidthResize = await locatorClientRect(statePackageContainer)
    expect(afterWidthResize.width).toBeGreaterThan(afterHeightResize.width + 50)
    expect(Math.abs(afterWidthResize.height - afterHeightResize.height)).toBeLessThanOrEqual(4)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()
  })

  test('container resize expands parent state packages when a child container exceeds bounds', async ({ page }) => {
    await openNetworkEditorFixture(page, {
      graphResponse: referencedStatePackageGraphResponse(),
      expectedRootStateId: 4,
      expectInitialLeafNodes: false,
    })
    await page.getByTestId('network-editor-enter-edit').click()

    const outerStateNode = page.getByTestId('network-editor-state-node-4')
    await toggleStateExpansionAndWait(page, outerStateNode.locator('[data-action="toggle"]'))

    const outerContainer = page.getByTestId('network-editor-state-package-container-4')
    const childPackageContainer = page.getByTestId('network-editor-state-package-container-1')
    await expect(outerContainer).toBeVisible()
    await page.getByTestId('network-editor-state-node-1').locator('[data-action="toggle"]').click()
    await expect(childPackageContainer).toBeVisible()

    const outerBefore = await locatorClientRect(outerContainer)
    await resizeContainerBy(page, childPackageContainer, 420, 0)
    const outerAfter = await locatorClientRect(outerContainer)
    expect(outerAfter.width).toBeGreaterThan(outerBefore.width + 300)
    expect(outerAfter.height).toBeGreaterThanOrEqual(outerBefore.height - 4)
    expect(outerAfter.height).toBeLessThanOrEqual(outerBefore.height + 24)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()
  })

  test('auto arrange wraps state package children by container width and grows height', async ({ page }) => {
    await openNetworkEditorFixture(page, {
      graphResponse: statePackageAutoArrangeGraphResponse(),
      expectActivityNodes: false,
      expectInitialLeafNodes: false,
    })
    await page.getByTestId('network-editor-enter-edit').click()

    const statePackageRoot = page.getByTestId('network-editor-state-node-1')
    await toggleStateExpansionAndWait(page, statePackageRoot.locator('[data-action="toggle"]'))
    const statePackageContainer = page.getByTestId('network-editor-state-package-container-1')
    await expect(statePackageContainer).toBeVisible()
    const before = await locatorClientRect(statePackageContainer)

    await page.getByTestId('network-editor-more-actions').click()
    await page.getByTestId('network-editor-auto-arrange').click()
    await waitForNetworkEditorIdle(page)
    await page.waitForTimeout(160)

    const after = await locatorClientRect(statePackageContainer)
    const firstChild = await locatorClientRect(page.getByTestId('network-editor-state-node-3'))
    const thirdChild = await locatorClientRect(page.getByTestId('network-editor-state-node-6'))
    expect(after.width).toBeGreaterThanOrEqual(500)
    expect(after.width).toBeLessThanOrEqual(before.width + 3)
    expect(after.height).toBeGreaterThan(before.height + 24)
    expect(thirdChild.y).toBeGreaterThan(firstChild.y + 60)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()
  })

  test('renders a draft referenced state inside its target state package', async ({ page }) => {
    await openNetworkEditorFixture(page, { expectInitialLeafNodes: false })
    await page.getByTestId('network-editor-enter-edit').click()

    await chooseElSelectOption(
      page,
      page.getByTestId('network-editor-reference-state-select'),
      '包内原子状态',
    )
    await chooseElSelectOption(
      page,
      page.getByTestId('network-editor-reference-parent-select'),
      '跨层级目标状态',
    )
    await page.locator('.reference-form').getByRole('button', { name: '添加' }).click()

    await expect(page.locator('.draft-change-list')).toContainText('复用状态：STATE_IN_READY')
    const targetPackageNode = page.getByTestId('network-editor-state-node-4')
    const targetContainer = page.getByTestId('network-editor-state-package-container-4')
    const referencedStateNode = page.getByTestId('network-editor-state-node-3').last()
    await expect(targetPackageNode).toBeVisible()
    await expect(targetContainer).toBeVisible()
    await expect(referencedStateNode).toContainText('包内原子状态')

    const containerBox = await locatorClientRect(targetContainer)
    const childBox = await locatorClientRect(referencedStateNode)
    expect(childBox.x).toBeGreaterThanOrEqual(containerBox.x - 2)
    expect(childBox.y).toBeGreaterThanOrEqual(containerBox.y - 2)
    expect(childBox.x + childBox.width).toBeLessThanOrEqual(containerBox.x + containerBox.width + 2)
    expect(childBox.y + childBox.height).toBeLessThanOrEqual(containerBox.y + containerBox.height + 2)

    const [commitRequest] = await Promise.all([
      page.waitForRequest((request: any) =>
        request.url().endsWith('/api/v1/machine-types/1/network-editor/commit') &&
        request.method() === 'POST',
      ),
      page.getByTestId('network-editor-submit-draft').click(),
    ])
    const payload = JSON.parse(commitRequest.postData() || '{}')
    expect(payload.changes).toHaveLength(1)
    expect(payload.changes[0]).toMatchObject({
      entity_type: 'state_node_reference',
      operation: 'create',
      payload: {
        state_node_id: 3,
        parent_state_node_id: 4,
      },
    })
  })

  test('keeps expanded containers from overlapping and restores folded positions', async ({ page }) => {
    await openNetworkEditorFixture(page, {
      graphResponse: overlappingExpandedContainersGraphResponseForRequest,
      activityNodes: nestedActivityNodes,
      expectInitialLeafNodes: false,
    })
    await page.getByTestId('network-editor-enter-edit').click()
    await expect(page.getByTestId('network-editor-submit-draft')).toBeDisabled()

    const stateReady = page.getByTestId('network-editor-state-node-1')
    const stateDone = page.getByTestId('network-editor-state-node-4')
    const stateDoneBefore = await readCanvasPosition(stateDone)
    await toggleStateExpansionAndWait(page, stateReady.locator('[data-action="toggle"]'))
    await toggleStateExpansionAndWait(page, stateDone.locator('[data-action="toggle"]'))

    const readyContainer = page.getByTestId('network-editor-state-package-container-1')
    const doneContainer = page.getByTestId('network-editor-state-package-container-4')
    await expect(readyContainer).toBeVisible()
    await expect(doneContainer).toBeVisible()
    const readyContainerBox = await locatorClientRect(readyContainer)
    const doneContainerBox = await locatorClientRect(doneContainer)
    const doneChild = page.getByTestId('network-editor-state-node-40')
    const doneChildBox = await locatorClientRect(doneChild)
    const doneTitleBox = await locatorClientRect(stateDone, { preferOwnRect: true })
    expect(rectsOverlap(readyContainerBox, doneContainerBox)).toBe(false)
    expect(doneTitleBox.height).toBeLessThanOrEqual(58)
    expect(rectsOverlap(doneTitleBox, doneChildBox)).toBe(false)
    expect(doneChildBox.y - doneContainerBox.y).toBeLessThan(220)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeDisabled()

    await toggleStateExpansionAndWait(page, stateDone.locator('[data-action="toggle"]'))
    await expect(doneContainer).toBeHidden()
    const stateDoneAfter = await readCanvasPosition(stateDone)
    expect(Math.abs(stateDoneAfter.x - stateDoneBefore.x)).toBeLessThan(2)
    expect(Math.abs(stateDoneAfter.y - stateDoneBefore.y)).toBeLessThan(2)
    await expect(page.getByTestId('network-editor-submit-draft')).toBeDisabled()

    await toggleStateExpansionAndWait(page, stateDone.locator('[data-action="toggle"]'))
    await expect(doneContainer).toBeVisible()
    await page.getByTestId('network-editor-more-actions').click()
    await page.getByTestId('network-editor-auto-arrange').click()
    await waitForNetworkEditorIdle(page)
    await page.waitForTimeout(160)
    const compactDoneContainerBox = await locatorClientRect(doneContainer)
    const compactDoneChildBox = await locatorClientRect(doneChild)
    expect(compactDoneContainerBox.y + compactDoneContainerBox.height - (compactDoneChildBox.y + compactDoneChildBox.height)).toBeLessThan(150)
    expect(compactDoneContainerBox.width).toBeLessThan(560)
    expect(compactDoneContainerBox.height).toBeLessThan(430)

    const childBeforeDrag = await readCanvasPosition(doneChild)
    await dragLocatorBy(page, doneChild.locator('.layout-handle'), 0, -60)
    await waitForNetworkEditorIdle(page)
    const childAfterDrag = await readCanvasPosition(doneChild)
    expect(childAfterDrag.y).toBeLessThan(childBeforeDrag.y - 20)
  })

  test('moves folded package descendants with the parent before expansion', async ({ page }) => {
    await openNetworkEditorFixture(page, {
      graphResponse: overlappingExpandedContainersGraphResponseForRequest,
      activityNodes: nestedActivityNodes,
      expectInitialLeafNodes: false,
    })
    await page.getByTestId('network-editor-enter-edit').click()

    const statePackageRoot = page.getByTestId('network-editor-state-node-1')
    const childState = page.getByTestId('network-editor-state-node-3')
    const statePackageContainer = page.getByTestId('network-editor-state-package-container-1')
    await expect(statePackageContainer).toBeHidden()
    await expect(childState).toHaveCount(0)

    const rootBefore = await readCanvasPosition(statePackageRoot)
    await dragLocatorBy(page, statePackageRoot.locator('.layout-handle'), 220, 64)
    await waitForNetworkEditorIdle(page)
    const rootAfter = await readCanvasPosition(statePackageRoot)
    expect(rootAfter.x).toBeGreaterThan(rootBefore.x + 140)
    expect(rootAfter.y).toBeGreaterThan(rootBefore.y + 32)

    await toggleStateExpansionAndWait(page, statePackageRoot.locator('[data-action="toggle"]'))
    await expect(statePackageContainer).toBeVisible()
    await expect(childState).toBeVisible()
    const containerBox = await locatorClientRect(statePackageContainer)
    const rootBox = await locatorClientRect(statePackageRoot)
    const childBox = await locatorClientRect(childState)
    expect(containerBox.width).toBeLessThan(520)
    expect(containerBox.height).toBeLessThan(360)
    expect(rootBox.x).toBeGreaterThanOrEqual(containerBox.x - 2)
    expect(childBox.x).toBeGreaterThanOrEqual(containerBox.x - 2)
    expect(rootBox.x + rootBox.width).toBeLessThanOrEqual(containerBox.x + containerBox.width + 2)
    expect(childBox.x + childBox.width).toBeLessThanOrEqual(containerBox.x + containerBox.width + 2)

  })

  test('moves internal nodes freely inside expanded containers', async ({ page }) => {
    await openNetworkEditorFixture(page, { expectInitialLeafNodes: false })
    await page.getByTestId('network-editor-enter-edit').click()

    const statePackageRoot = page.getByTestId('network-editor-state-node-1')
    await toggleStateExpansionAndWait(page, statePackageRoot.locator('[data-action="toggle"]'))
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
    expect(Math.abs(statePackageRootAfter.x - statePackageRootBefore.x)).toBeLessThan(60)
    expect(Math.abs(statePackageRootAfter.y - statePackageRootBefore.y)).toBeLessThan(40)

    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()
    await expect(page.locator('.draft-change-list')).toContainText('调整状态位置')
  })

  test('moves expanded containers with their internal nodes as one draft batch', async ({ page }) => {
    await openNetworkEditorFixture(page, { expectInitialLeafNodes: false })
    await page.getByTestId('network-editor-enter-edit').click()

    const stateNode = page.getByTestId('network-editor-state-node-1')
    await toggleStateExpansionAndWait(page, stateNode.locator('[data-action="toggle"]'))
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

    await expect(page.getByTestId('network-editor-submit-draft')).toBeEnabled()
    await expect(page.locator('.draft-change-list')).toContainText('调整状态位置')
  })
})
