function packagePath(packageId, packageById) {
  const path = []
  const seen = new Set()
  let current = packageById.get(packageId)
  while (current && !seen.has(current.id)) {
    seen.add(current.id)
    path.unshift(current.id)
    current = current.parent_id ? packageById.get(current.parent_id) : null
  }
  return path
}

function layoutMetadata(layout = {}) {
  const metadata = {}
  if (Number.isFinite(Number(layout.x)) && Number.isFinite(Number(layout.y))) {
    metadata._network_editor_layout = { x: Number(layout.x), y: Number(layout.y) }
  }
  if (Number.isFinite(Number(layout.width)) && Number.isFinite(Number(layout.height))) {
    metadata._network_editor_container = { width: Number(layout.width), height: Number(layout.height) }
  }
  return metadata
}

export function plannerGraphToX6(graph = {}) {
  const containers = graph.containers || []
  const packageById = new Map(containers.map((item) => [item.id, item]))
  const packageNodes = containers.map((item) => {
    const path = packagePath(item.id, packageById)
    return {
      id: item.id,
      activity_node_id: item.id,
      activity_type: 'activity_package',
      level: item.level,
      parent_id: item.parent_id,
      parent_activity_node_ids: path.slice(0, -1),
      path_ids: path,
      code: item.display_code,
      name: item.name,
      display_meta: item.level === 1 ? '一级活动包' : '二级活动包',
      metadata_json: layoutMetadata(item.layout),
      _planner_kind: 'package',
      _planner_id: item.id,
    }
  })

  const activityNodes = (graph.nodes || []).map((item) => {
    const path = item.package_id ? packagePath(item.package_id, packageById) : []
    return {
      id: item.id,
      activity_node_id: item.id,
      atomic_activity_id: item.canonical_activity_id,
      activity_type: 'atomic_activity',
      level: 3,
      parent_id: item.package_id,
      parent_graph_id: item.package_id,
      parent_activity_node_ids: path,
      path_ids: [...path, item.id],
      code: item.display_code,
      name: item.name,
      duration: item.duration,
      display_meta: `活动 · 工期 ${item.duration}`,
      metadata_json: layoutMetadata(item.layout),
      _planner_kind: 'activity',
      _planner_id: item.id,
      canonical_activity_id: item.canonical_activity_id,
    }
  })

  const edges = (graph.edges || []).map((item) => ({
    ...item,
    source_id: item.source,
    target_id: item.target,
    type: 'STATE_FLOW',
    displayLabel: item.relation_role === 'transition' ? '替换前置' : '保留前置',
    flow: { state: 'backbone', role: item.relation_role || 'required' },
  }))

  return {
    activityNodes: [...packageNodes, ...activityNodes],
    edges,
    rootPackageIds: containers.filter((item) => item.level === 1).map((item) => item.id),
  }
}

export function plannerPathToTasks(path = {}, scenario = {}) {
  const activities = new Map((scenario.activities || []).map((item) => [item.id, item]))
  const resources = new Map((scenario.resources || []).map((item) => [item.id, item.name]))
  const executions = path.executions || []
  const producerByState = new Map()
  executions.forEach((execution, index) => {
    for (const stateId of execution.after_state_ids || []) producerByState.set(stateId, index + 1)
  })

  return executions.map((execution, index) => {
    const activity = activities.get(execution.activity_id) || {}
    const predecessors = [...new Set(
      (execution.before_state_ids || []).map((stateId) => producerByState.get(stateId)).filter(Boolean),
    )]
    if (!predecessors.length && index > 0 && scenario.execution_mode === 'serial') predecessors.push(index)
    return {
      step_id: execution.instance_id || `${execution.activity_id}:${index + 1}`,
      step_order: index + 1,
      op_code: activity.display_code || `ACT-${String(index + 1).padStart(4, '0')}`,
      op_name: execution.activity_name || activity.name || execution.activity_id,
      op_rule_code: activity.display_code || `ACT-${String(index + 1).padStart(4, '0')}`,
      op_rule_name: execution.activity_name || activity.name || execution.activity_id,
      display_name: `${activity.display_code || index + 1} · ${execution.activity_name || activity.name || ''}`,
      start_min: Number(execution.start_time || 0),
      end_min: Number(execution.end_time || 0),
      duration_min: Number(execution.end_time || 0) - Number(execution.start_time || 0),
      predecessor_ids: predecessors,
      predecessors,
      resources: Object.entries(activity.resource_reqs || {}).map(([resourceId, quantity]) => ({
        resource_id: resourceId,
        code: resources.get(resourceId) || resourceId,
        name: resources.get(resourceId) || resourceId,
        quantity,
      })),
      step_role: 'normal',
      activity_id: execution.activity_id,
    }
  })
}
