import ELK from 'elkjs/lib/elk.bundled.js'
import {
  NETWORK_EDITOR_NODE_MAX_WIDTH,
  STATE_TRANSITION_ELK_EDGE_EDGE_GAP,
  STATE_TRANSITION_ELK_EDGE_NODE_GAP,
  STATE_TRANSITION_ELK_LAYER_GAP,
  STATE_TRANSITION_ELK_NODE_GAP,
} from './networkEditorLayoutMetrics'

const DEFAULT_STATE_WIDTH = 220
const DEFAULT_STATE_HEIGHT = 72
const DEFAULT_ACTIVITY_WIDTH = 220
const DEFAULT_ACTIVITY_HEIGHT = 72
const DEFAULT_RELAY_SIZE = 18
const X6_NODE_WIDTH = 168
const X6_NODE_HEIGHT = 44
const X6_NODE_MAX_WIDTH = NETWORK_EDITOR_NODE_MAX_WIDTH
const X6_NODE_TEXT_SIDE_SPACE = 54
const X6_NODE_NAME_LINE_HEIGHT = 16
const X6_NODE_SUMMARY_LINE_HEIGHT = 14
const X6_NODE_WARNING_HEIGHT = 16
const X6_NODE_VERTICAL_SPACE = 14
const CONTAINER_MIN_WIDTH = 220
const CONTAINER_MIN_HEIGHT = 104
const CONTAINER_HEADER_SPACE = 66
const CONTAINER_LEFT_RAIL_SPACE = 62
const CONTAINER_RIGHT_PADDING = 34
const CONTAINER_BOTTOM_PADDING = 28
const CONTAINER_WRAP_HEADER_SPACE = 92
const CONTAINER_WRAP_GAP_X = 24
const CONTAINER_WRAP_GAP_Y = 24
const COMPACT_PARALLEL_CONTAINER_MAX_WIDTH = 2400
const COMPACT_PARALLEL_COLUMN_GAP = 96
const COMPACT_PARALLEL_ROW_GAP = 28
const COMPACT_PARALLEL_SEGMENT_GAP_Y = 96
const DEFAULT_BASE_X = 72
const DEFAULT_BASE_Y = 70
const DUPLICATE_ROUTE_GAP = 8
const MAX_AUTO_ROUTE_VERTICES = 4
const ROOT_CONTAINER_ID = '__network_editor_layout_root__'

let elkInstance = null

function elk() {
  if (!elkInstance) elkInstance = new ELK()
  return elkInstance
}

export async function layoutStateTransitionGraph({
  stateNodes = [],
  relayGroups = [],
  baseX = DEFAULT_BASE_X,
  baseY = DEFAULT_BASE_Y,
  stateWidth = DEFAULT_STATE_WIDTH,
  stateHeight = DEFAULT_STATE_HEIGHT,
  relaySize = DEFAULT_RELAY_SIZE,
} = {}) {
  return layoutRelationGraph({
    stateNodes,
    activityNodes: [],
    edges: buildTransitionRelationEdges(relayGroups),
    relayNodeIds: (relayGroups || []).map((group) => group.relayId),
    baseX,
    baseY,
    stateWidth,
    stateHeight,
    activityWidth: relaySize,
    activityHeight: relaySize,
  })
}

export async function layoutRelationGraph({
  stateNodes = [],
  activityNodes = [],
  edges = [],
  relayNodeIds = [],
  baseX = DEFAULT_BASE_X,
  baseY = DEFAULT_BASE_Y,
  stateWidth = DEFAULT_STATE_WIDTH,
  stateHeight = DEFAULT_STATE_HEIGHT,
  activityWidth = DEFAULT_ACTIVITY_WIDTH,
  activityHeight = DEFAULT_ACTIVITY_HEIGHT,
} = {}) {
  if (
    globalThis?.__NETWORK_EDITOR_FORCE_ELK_FAILURE__ ||
    globalThis?.localStorage?.getItem?.('networkEditor.forceElkFailure') === '1'
  ) {
    throw new Error('Forced ELK layout failure')
  }

  const stateNodeById = new Map((stateNodes || []).map((node) => [String(node.id), node]))
  const activityNodeById = new Map((activityNodes || []).map((node) => [String(node.id), node]))
  const relayIds = new Set((relayNodeIds || []).map((id) => String(id)))
  const relationEdges = normalizeRelationEdges(edges, stateNodeById, activityNodeById, relayIds)

  if ((!stateNodeById.size && !activityNodeById.size && !relayIds.size) || !relationEdges.length) {
    return emptyRelationLayout()
  }

  const involvedStateIds = new Set()
  const involvedActivityIds = new Set()
  for (const edge of relationEdges) {
    if (stateNodeById.has(edge.sourceId)) involvedStateIds.add(edge.sourceId)
    if (stateNodeById.has(edge.targetId)) involvedStateIds.add(edge.targetId)
    if (activityNodeById.has(edge.sourceId) || relayIds.has(edge.sourceId)) involvedActivityIds.add(edge.sourceId)
    if (activityNodeById.has(edge.targetId) || relayIds.has(edge.targetId)) involvedActivityIds.add(edge.targetId)
  }

  const graph = {
    id: 'state-transition-root',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': 'RIGHT',
      'elk.edgeRouting': 'ORTHOGONAL',
      'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
      'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
      'elk.layered.layering.strategy': 'NETWORK_SIMPLEX',
      'elk.portConstraints': 'FIXED_SIDE',
      'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
      'elk.spacing.nodeNode': String(STATE_TRANSITION_ELK_NODE_GAP),
      'elk.layered.spacing.nodeNodeBetweenLayers': String(STATE_TRANSITION_ELK_LAYER_GAP),
      'elk.layered.spacing.edgeNodeBetweenLayers': String(STATE_TRANSITION_ELK_EDGE_NODE_GAP),
      'elk.layered.spacing.edgeEdgeBetweenLayers': String(STATE_TRANSITION_ELK_EDGE_EDGE_GAP),
      'elk.layered.mergeEdges': 'false',
      'elk.separateConnectedComponents': 'true',
      'elk.spacing.componentComponent': '48',
      'elk.randomSeed': '1',
    },
    children: [
      ...Array.from(involvedStateIds)
        .sort((a, b) => stableNodeOrder(stateNodeById.get(a), stateNodes) - stableNodeOrder(stateNodeById.get(b), stateNodes))
        .map((id) => elkNode(id, stateWidth, stateHeight)),
      ...Array.from(involvedActivityIds)
        .sort((a, b) => stableNodeOrder(activityNodeById.get(a), activityNodes) - stableNodeOrder(activityNodeById.get(b), activityNodes))
        .map((id) => elkNode(
          id,
          relayIds.has(id) ? DEFAULT_RELAY_SIZE : activityWidth,
          relayIds.has(id) ? DEFAULT_RELAY_SIZE : activityHeight,
        )),
    ],
    edges: relationEdges.map((edge) => ({
      id: edge.id,
      sources: [outputPortId(edge.sourceId)],
      targets: [inputPortId(edge.targetId)],
    })),
  }

  const result = await elk().layout(graph)
  return normalizeElkRelationLayout(result, { baseX, baseY, relayIds })
}

export async function layoutNestedContainerGraph({
  stateNodes = [],
  activityNodes = [],
  relayNodes = [],
  edges = [],
  expandedStateContainerIds = [],
  expandedActivityContainerIds = [],
  baseX = DEFAULT_BASE_X,
  baseY = DEFAULT_BASE_Y,
} = {}) {
  if (
    globalThis?.__NETWORK_EDITOR_FORCE_ELK_FAILURE__ ||
    globalThis?.localStorage?.getItem?.('networkEditor.forceElkFailure') === '1'
  ) {
    throw new Error('Forced ELK layout failure')
  }

  const items = new Map()
  const expandedStateIds = new Set((expandedStateContainerIds || []).map((id) => String(id)))
  const expandedActivityIds = new Set((expandedActivityContainerIds || []).map((id) => String(id)))
  const knownActivityIds = new Set()

  for (const node of stateNodes || []) {
    const id = String(node?.id || '')
    if (!id) continue
    items.set(id, {
      id,
      kind: 'state',
      node,
      isContainerCandidate: expandedStateIds.has(id) && !node?.is_leaf && !!node?.state_node_id,
      size: nodeDimensionsForLayout(node, 'state'),
    })
  }

  for (const node of activityNodes || []) {
    const id = String(node?.id || '')
    if (!id || knownActivityIds.has(id)) continue
    knownActivityIds.add(id)
    const relay = isTransitionRelayNode(node)
    items.set(id, {
      id,
      kind: relay ? 'relay' : 'activity',
      node,
      isContainerCandidate: !relay &&
        expandedActivityIds.has(id) &&
        node?.activity_type === 'virtual' &&
        !!node?.activity_node_id,
      size: nodeDimensionsForLayout(node, relay ? 'relay' : 'activity'),
    })
  }

  for (const node of relayNodes || []) {
    const id = String(node?.id || '')
    if (!id || items.has(id)) continue
    items.set(id, {
      id,
      kind: 'relay',
      node,
      isContainerCandidate: false,
      size: nodeDimensionsForLayout(node, 'relay'),
    })
  }

  const diagnostics = {
    source: 'elk-nested',
    nodeCount: items.size,
    edgeCount: 0,
    containerCount: 0,
    compactContainerCount: 0,
    oversizedContainerCount: 0,
  }
  if (!items.size) {
    return nestedLayoutResult({ diagnostics })
  }

  const rawParentById = buildRawParentMap(items)
  const parentById = new Map()
  for (const id of items.keys()) {
    parentById.set(id, nearestLayoutParent(id, items, rawParentById))
  }
  const childrenByParent = buildChildrenByParent(items, parentById)
  for (const item of items.values()) {
    item.isContainer = item.isContainerCandidate && (childrenByParent.get(item.id) || []).length > 0
    if (item.isContainer) diagnostics.containerCount += 1
  }
  const relationEdges = normalizeNestedLayoutEdges(edges, items)
  for (const id of items.keys()) {
    parentById.set(id, nearestLayoutParent(id, items, rawParentById))
  }
  assignRelayLayoutParents(rawParentById, parentById, items, relationEdges)
  for (const id of items.keys()) {
    parentById.set(id, nearestLayoutParent(id, items, rawParentById))
  }
  const layoutChildrenByParent = buildChildrenByParent(items, parentById)
  diagnostics.edgeCount = relationEdges.length

  const localPositions = new Map()
  const sizeById = new Map(Array.from(items.values()).map((item) => [item.id, item.size]))
  const containerSizes = new Map()
  const edgeRoutes = new Map()
  const localEdgeRoutes = []

  async function layoutContainer(containerId) {
    const childIds = layoutChildrenByParent.get(containerId) || []
    for (const childId of childIds) {
      const child = items.get(childId)
      if (child?.isContainer) {
        const size = await layoutContainer(childId)
        sizeById.set(childId, size)
      }
    }

    if (!childIds.length) return { width: CONTAINER_MIN_WIDTH, height: CONTAINER_MIN_HEIGHT }

    const containerItem = items.get(containerId)
    const direction = layoutDirectionForContainer(containerItem)
    const projectedEdges = projectedContainerEdges(containerId, childIds, relationEdges, parentById, items)
    const projectedEdgeById = new Map(projectedEdges.map((edge) => [edge.id, edge]))
    let result = null
    let childPositions = manualContainerChildPositions(containerItem, childIds, sizeById, projectedEdges)
    const preserveCurrentWidth = !!childPositions
    let compactedByWidth = false
    if (!childPositions) {
      childPositions = new Map()
      const graph = {
        id: containerId,
        layoutOptions: nestedLayoutOptions(containerItem, direction),
        children: childIds.map((id) => {
          const size = sizeById.get(id) || nodeDimensionsForLayout(items.get(id)?.node, items.get(id)?.kind)
          return elkNode(id, size.width, size.height)
        }),
        edges: projectedEdges.map((edge) => ({
          id: edge.id,
          sources: [outputPortId(edge.sourceId)],
          targets: [inputPortId(edge.targetId)],
        })),
      }
      result = await elk().layout(graph)
      for (const child of result.children || []) {
        childPositions.set(child.id, {
          x: Math.round(finiteNumber(child.x) ?? 0),
          y: Math.round(finiteNumber(child.y) ?? 0),
        })
      }
      const compacted = compactParallelContainerPositions({
        containerItem,
        childIds,
        childPositions,
        projectedEdges,
        sizeById,
      })
      if (compacted) {
        childPositions = compacted.positions
        compactedByWidth = true
        diagnostics.compactContainerCount += 1
        if (compacted.oversized) diagnostics.oversizedContainerCount += 1
      }
    }
    applyFallbackPositions(childIds, childPositions, sizeById, direction)
    for (const [id, position] of childPositions.entries()) {
      localPositions.set(id, position)
    }
    if (result && !compactedByWidth) {
      for (const edge of result.edges || []) {
        const projected = projectedEdgeById.get(edge.id)
        if (!projected?.routeEdgeIds?.length) continue
        const points = simplifyRoutePoints(edgeSectionPoints(edge, 0, 0))
        if (points.length < 2) continue
        const routedPoints = points.length > MAX_AUTO_ROUTE_VERTICES + 2
          ? compactOrthogonalRoute(points)
          : points
        for (const edgeId of projected.routeEdgeIds) {
          localEdgeRoutes.push({
            containerId,
            edgeId,
            points: routedPoints,
            vertices: routedPoints.slice(1, -1),
          })
        }
      }
    }

    if (containerId === ROOT_CONTAINER_ID) return { width: 0, height: 0 }

    const size = containerSizeFromChildren(containerItem, childIds, childPositions, sizeById, {
      preserveCurrentWidth,
    })
    containerSizes.set(containerId, size)
    return size
  }

  await layoutContainer(ROOT_CONTAINER_ID)

  const rootChildIds = layoutChildrenByParent.get(ROOT_CONTAINER_ID) || []
  const rootOffset = rootLayoutOffset(rootChildIds, localPositions, baseX, baseY)
  const absolutePositions = new Map()
  const containerOrigins = new Map()

  function expandAbsolute(containerId, origin) {
    containerOrigins.set(containerId, origin)
    for (const childId of layoutChildrenByParent.get(containerId) || []) {
      const local = localPositions.get(childId) || { x: 0, y: 0 }
      const absolute = {
        x: Math.round(origin.x + local.x),
        y: Math.round(origin.y + local.y),
      }
      absolutePositions.set(childId, absolute)
      if (items.get(childId)?.isContainer) {
        expandAbsolute(childId, absolute)
      }
    }
  }
  expandAbsolute(ROOT_CONTAINER_ID, rootOffset)

  for (const route of localEdgeRoutes) {
    const origin = containerOrigins.get(route.containerId) || rootOffset
    const points = route.points.map((point) => ({
      x: Math.round(origin.x + point.x),
      y: Math.round(origin.y + point.y),
    }))
    const vertices = route.vertices.map((point) => ({
      x: Math.round(origin.x + point.x),
      y: Math.round(origin.y + point.y),
    }))
    edgeRoutes.set(route.edgeId, {
      kind: 'elk',
      points,
      vertices,
    })
  }
  spreadDuplicateRoutes(edgeRoutes)

  const statePositions = new Map()
  const activityPositions = new Map()
  const relayPositions = new Map()
  for (const [id, position] of absolutePositions.entries()) {
    const item = items.get(id)
    if (!item) continue
    if (item.kind === 'state') statePositions.set(id, position)
    else if (item.kind === 'relay') relayPositions.set(id, position)
    else activityPositions.set(id, position)
  }

  return nestedLayoutResult({
    statePositions,
    activityPositions,
    relayPositions,
    containerSizes,
    edgeRoutes,
    diagnostics,
  })
}

export function emptyStateTransitionLayout() {
  return emptyRelationLayout()
}

export function emptyRelationLayout() {
  return {
    statePositions: new Map(),
    activityPositions: new Map(),
    relayPositions: new Map(),
    edgeRoutes: new Map(),
    diagnostics: {
      source: 'elk',
      nodeCount: 0,
      edgeCount: 0,
    },
  }
}

function buildTransitionRelationEdges(relayGroups) {
  const edges = []
  const seen = new Set()
  for (const group of relayGroups || []) {
    for (const input of group.inputs || []) {
      const key = `${input.source_id}->${group.relayId}:${group.activityId}`
      const id = `state-flow-relay-in:${key}`
      if (seen.has(id)) continue
      seen.add(id)
      edges.push({ id, source_id: input.source_id, target_id: group.relayId })
    }
    for (const output of group.outputs || []) {
      const key = `${group.relayId}->${output.target_id}:${group.activityId}`
      const id = `state-flow-relay-out:${key}`
      if (seen.has(id)) continue
      seen.add(id)
      edges.push({ id, source_id: group.relayId, target_id: output.target_id })
    }
  }
  return edges
}

function normalizeRelationEdges(edges, stateNodeById, activityNodeById, relayIds) {
  const known = new Set([
    ...stateNodeById.keys(),
    ...activityNodeById.keys(),
    ...relayIds,
  ])
  const seen = new Set()
  const result = []
  for (const edge of edges || []) {
    if ((edge?.aggregate && !edge?.projectionProxy) || edge?.isCollapsedInternalProxy) continue
    const sourceId = String(edge?.source_id || edge?.sourceId || '')
    const targetId = String(edge?.target_id || edge?.targetId || '')
    if (!sourceId || !targetId || sourceId === targetId) continue
    if (!known.has(sourceId) || !known.has(targetId)) continue
    const id = String(edge?.id || `${sourceId}->${targetId}`)
    if (seen.has(id)) continue
    seen.add(id)
    result.push({ id, sourceId, targetId })
  }
  return result
}

function elkNode(id, width, height) {
  return {
    id,
    width,
    height,
    layoutOptions: {
      'elk.portConstraints': 'FIXED_SIDE',
    },
    ports: [
      {
        id: inputPortId(id),
        width: 1,
        height: 1,
        layoutOptions: { 'elk.port.side': 'WEST' },
      },
      {
        id: outputPortId(id),
        width: 1,
        height: 1,
        layoutOptions: { 'elk.port.side': 'EAST' },
      },
    ],
  }
}

function normalizeElkRelationLayout(result, { baseX, baseY, relayIds }) {
  const childPositions = new Map()
  let minX = Infinity
  let minY = Infinity
  for (const child of result.children || []) {
    const x = finiteNumber(child.x) ?? 0
    const y = finiteNumber(child.y) ?? 0
    minX = Math.min(minX, x)
    minY = Math.min(minY, y)
    childPositions.set(child.id, { x, y })
  }
  if (!Number.isFinite(minX)) minX = 0
  if (!Number.isFinite(minY)) minY = 0
  const dx = Math.round(baseX - minX)
  const dy = Math.round(baseY - minY)

  const statePositions = new Map()
  const activityPositions = new Map()
  const relayPositions = new Map()
  for (const [id, position] of childPositions.entries()) {
    const target = id.startsWith('state_node:')
      ? statePositions
      : relayIds.has(id) || id.startsWith('transition_relay:') ? relayPositions : activityPositions
    target.set(id, {
      x: Math.round(position.x + dx),
      y: Math.round(position.y + dy),
    })
  }

  const edgeRoutes = new Map()
  for (const edge of result.edges || []) {
    const points = simplifyRoutePoints(edgeSectionPoints(edge, dx, dy))
    if (points.length >= 2) {
      const routedPoints = points.length > MAX_AUTO_ROUTE_VERTICES + 2
        ? compactOrthogonalRoute(points)
        : points
      edgeRoutes.set(edge.id, {
        kind: 'elk',
        points: routedPoints,
        vertices: routedPoints.slice(1, -1),
      })
    }
  }
  spreadDuplicateRoutes(edgeRoutes)

  return {
    statePositions,
    activityPositions,
    relayPositions,
    edgeRoutes,
    diagnostics: {
      source: 'elk',
      nodeCount: childPositions.size,
      edgeCount: edgeRoutes.size,
    },
  }
}

function simplifyRoutePoints(points) {
  const unique = []
  for (const point of points || []) {
    const previous = unique[unique.length - 1]
    if (previous && previous.x === point.x && previous.y === point.y) continue
    unique.push(point)
  }
  const simplified = []
  for (const point of unique) {
    simplified.push(point)
    while (simplified.length >= 3) {
      const a = simplified[simplified.length - 3]
      const b = simplified[simplified.length - 2]
      const c = simplified[simplified.length - 1]
      const collinearX = a.x === b.x && b.x === c.x
      const collinearY = a.y === b.y && b.y === c.y
      if (!collinearX && !collinearY) break
      simplified.splice(simplified.length - 2, 1)
    }
  }
  return simplified
}

function compactOrthogonalRoute(points) {
  const start = points[0]
  const end = points[points.length - 1]
  if (!start || !end) return points
  if (start.y === end.y || start.x === end.x) return [start, end]
  const midX = Math.round((start.x + end.x) / 2)
  return simplifyRoutePoints([
    start,
    { x: midX, y: start.y },
    { x: midX, y: end.y },
    end,
  ])
}

function edgeSectionPoints(edge, dx, dy) {
  const section = (edge.sections || [])[0]
  if (!section?.startPoint || !section?.endPoint) return []
  return [
    section.startPoint,
    ...(section.bendPoints || []),
    section.endPoint,
  ].map((point) => ({
    x: Math.round((finiteNumber(point.x) ?? 0) + dx),
    y: Math.round((finiteNumber(point.y) ?? 0) + dy),
  }))
}

function spreadDuplicateRoutes(edgeRoutes) {
  const groups = new Map()
  for (const [edgeId, route] of edgeRoutes.entries()) {
    const key = routeSignature(route.points)
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push([edgeId, route])
  }

  for (const group of groups.values()) {
    if (group.length < 2) continue
    const offsets = laneOffsets(group.length)
    group.forEach(([edgeId, route], index) => {
      const axis = routeAxis(route.points)
      const offset = offsets[index]
      if (!offset) return
      const vertices = route.vertices.map((point) => axis === 'x'
        ? { ...point, x: point.x + offset }
        : { ...point, y: point.y + offset })
      edgeRoutes.set(edgeId, {
        ...route,
        kind: 'elk-lane',
        vertices,
      })
    })
  }
}

function routeSignature(points) {
  return (points || []).map((point) => `${Math.round(point.x)},${Math.round(point.y)}`).join('|')
}

function routeAxis(points) {
  const first = points?.[0]
  const last = points?.[points.length - 1]
  if (!first || !last) return 'y'
  return Math.abs(first.x - last.x) < Math.abs(first.y - last.y) ? 'x' : 'y'
}

function laneOffsets(count) {
  if (count <= 1) return [0]
  const center = (count - 1) / 2
  return Array.from({ length: count }, (_, index) => Math.round((index - center) * DUPLICATE_ROUTE_GAP))
}

function inputPortId(id) {
  return `${String(id)}:in`
}

function outputPortId(id) {
  return `${String(id)}:out`
}

function stableNodeOrder(node, nodes) {
  if (!node) return 0
  const index = nodes.findIndex((item) => item.id === node.id)
  const layout = node?.metadata_json?._network_editor_layout || {}
  const y = finiteNumber(layout.y) ?? 0
  const x = finiteNumber(layout.x) ?? 0
  return Math.max(index, 0) + y * 10000 + x
}

function nestedLayoutResult({
  statePositions = new Map(),
  activityPositions = new Map(),
  relayPositions = new Map(),
  containerSizes = new Map(),
  edgeRoutes = new Map(),
  diagnostics = null,
} = {}) {
  return {
    statePositions,
    activityPositions,
    relayPositions,
    containerSizes,
    edgeRoutes,
    diagnostics: diagnostics || {
      source: 'elk-nested',
      nodeCount: 0,
      edgeCount: 0,
      containerCount: 0,
    },
  }
}

function buildRawParentMap(items) {
  const stateByStateNodeId = new Map()
  const activityByActivityNodeId = new Map()
  for (const item of items.values()) {
    if (item.kind === 'state' && item.node?.state_node_id && !stateByStateNodeId.has(String(item.node.state_node_id))) {
      stateByStateNodeId.set(String(item.node.state_node_id), item.id)
    }
    if (item.kind === 'activity' && item.node?.activity_node_id && !activityByActivityNodeId.has(String(item.node.activity_node_id))) {
      activityByActivityNodeId.set(String(item.node.activity_node_id), item.id)
    }
  }

  const parents = new Map()
  for (const item of items.values()) {
    const candidates = item.kind === 'state'
      ? stateParentCandidates(item.node, stateByStateNodeId)
      : item.kind === 'activity'
        ? activityParentCandidates(item.node, activityByActivityNodeId)
        : []
    const parent = candidates.find((id) => id && id !== item.id && items.has(id)) || null
    parents.set(item.id, parent)
  }
  return parents
}

function stateParentCandidates(node, stateByStateNodeId) {
  const candidates = []
  for (const graphId of [node?.primary_parent_graph_id, node?.parent_graph_id]) {
    if (graphId) candidates.push(String(graphId))
  }
  for (const stateId of [node?.parent_state_node_id, node?.parent_id]) {
    if (!stateId) continue
    const key = String(stateId)
    candidates.push(`state_node:${key}`)
    if (stateByStateNodeId.has(key)) candidates.push(stateByStateNodeId.get(key))
  }
  for (const stateId of node?.reference_parent_ids || []) {
    const key = String(stateId)
    candidates.push(`state_node:${key}`)
    if (stateByStateNodeId.has(key)) candidates.push(stateByStateNodeId.get(key))
  }
  return candidates
}

function activityParentCandidates(node, activityByActivityNodeId) {
  const candidates = []
  for (const graphId of [node?.parent_graph_id]) {
    if (graphId) candidates.push(String(graphId))
  }
  for (const activityId of [node?.parent_id]) {
    if (!activityId) continue
    const key = String(activityId)
    candidates.push(`activity_node:${key}`)
    if (activityByActivityNodeId.has(key)) candidates.push(activityByActivityNodeId.get(key))
  }
  const parentIds = Array.isArray(node?.parent_activity_node_ids) ? node.parent_activity_node_ids : []
  for (let index = parentIds.length - 1; index >= 0; index -= 1) {
    const key = String(parentIds[index])
    candidates.push(`activity_node:${key}`)
    if (activityByActivityNodeId.has(key)) candidates.push(activityByActivityNodeId.get(key))
  }
  return candidates
}

function nearestLayoutParent(id, items, rawParentById) {
  const seen = new Set([id])
  let parent = rawParentById.get(id)
  while (parent && items.has(parent) && !seen.has(parent)) {
    const parentItem = items.get(parent)
    if (parentItem?.isContainerCandidate && parentItem?.isContainer !== false) return parent
    seen.add(parent)
    parent = rawParentById.get(parent)
  }
  return ROOT_CONTAINER_ID
}

function buildChildrenByParent(items, parentById) {
  const children = new Map([[ROOT_CONTAINER_ID, []]])
  for (const id of items.keys()) {
    const parent = parentById.get(id) || ROOT_CONTAINER_ID
    if (!children.has(parent)) children.set(parent, [])
    children.get(parent).push(id)
  }
  for (const list of children.values()) list.sort((a, b) => itemSortKey(items.get(a)) - itemSortKey(items.get(b)))
  return children
}

function assignRelayLayoutParents(rawParentById, parentById, items, edges) {
  for (const item of items.values()) {
    if (item.kind !== 'relay') continue
    const outputTargetIds = (edges || [])
      .filter((edge) => edge.sourceId === item.id)
      .map((edge) => edge.targetId)
      .filter((id) => id && items.has(id) && items.get(id)?.kind === 'state')
    const targetParent = deepestCommonLayoutParent(outputTargetIds, parentById, items)
    const connectedIds = (edges || [])
      .filter((edge) => edge.sourceId === item.id || edge.targetId === item.id)
      .map((edge) => edge.sourceId === item.id ? edge.targetId : edge.sourceId)
      .filter((id) => id && items.has(id) && items.get(id)?.kind !== 'relay')
    const commonParent = targetParent !== ROOT_CONTAINER_ID
      ? targetParent
      : deepestCommonLayoutParent(connectedIds, parentById, items)
    rawParentById.set(item.id, commonParent === ROOT_CONTAINER_ID ? null : commonParent)
  }
}

function deepestCommonLayoutParent(ids, parentById, items) {
  const chains = (ids || [])
    .map((id) => layoutAncestorChain(id, parentById, items))
    .filter((chain) => chain.length)
  if (!chains.length) return ROOT_CONTAINER_ID
  const otherChains = chains.slice(1).map((chain) => new Set(chain))
  return chains[0].find((id) => otherChains.every((chain) => chain.has(id))) || ROOT_CONTAINER_ID
}

function layoutAncestorChain(id, parentById, items) {
  const chain = []
  const seen = new Set([id])
  let current = parentById.get(id) || ROOT_CONTAINER_ID
  while (current && !seen.has(current)) {
    chain.push(current)
    if (current === ROOT_CONTAINER_ID) break
    seen.add(current)
    current = parentById.get(current) || ROOT_CONTAINER_ID
    if (current !== ROOT_CONTAINER_ID && !items.has(current)) current = ROOT_CONTAINER_ID
  }
  if (!chain.includes(ROOT_CONTAINER_ID)) chain.push(ROOT_CONTAINER_ID)
  return chain
}

function itemSortKey(item) {
  const layout = item?.node?.metadata_json?._network_editor_layout || {}
  const y = finiteNumber(layout.y) ?? 0
  const x = finiteNumber(layout.x) ?? 0
  const sortOrder = finiteNumber(item?.node?.sort_order) ?? 0
  return sortOrder * 100000000 + y * 10000 + x
}

function normalizeNestedLayoutEdges(edges, items) {
  const known = new Set(items.keys())
  const seen = new Set()
  const result = []
  for (const edge of edges || []) {
    if ((edge?.aggregate && !edge?.projectionProxy) || edge?.isCollapsedInternalProxy) continue
    const sourceId = String(edge?.source_id || edge?.sourceId || '')
    const targetId = String(edge?.target_id || edge?.targetId || '')
    if (!sourceId || !targetId || sourceId === targetId) continue
    if (!known.has(sourceId) || !known.has(targetId)) continue
    const id = String(edge?.id || `${sourceId}->${targetId}`)
    if (seen.has(id)) continue
    seen.add(id)
    result.push({ id, sourceId, targetId })
  }
  return result
}

function layoutDirectionForContainer(item) {
  if (item?.kind === 'activity') return 'DOWN'
  return 'RIGHT'
}

function nestedLayoutOptions(item, direction) {
  const isRoot = !item
  const titleHeight = isRoot ? 0 : containerTitleHeightForLayout(item.node)
  const topPadding = isRoot ? 0 : Math.max(CONTAINER_HEADER_SPACE, titleHeight + 30)
  const leftPadding = isRoot ? 0 : CONTAINER_LEFT_RAIL_SPACE
  const rightPadding = isRoot ? 0 : CONTAINER_RIGHT_PADDING
  const bottomPadding = isRoot ? 0 : CONTAINER_BOTTOM_PADDING
  return {
    'elk.algorithm': 'layered',
    'elk.direction': direction,
    'elk.edgeRouting': 'ORTHOGONAL',
    'elk.padding': `[top=${topPadding},left=${leftPadding},right=${rightPadding},bottom=${bottomPadding}]`,
    'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
    'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
    'elk.layered.layering.strategy': 'NETWORK_SIMPLEX',
    'elk.portConstraints': 'FIXED_SIDE',
    'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
    'elk.spacing.nodeNode': direction === 'DOWN' ? '18' : String(STATE_TRANSITION_ELK_NODE_GAP),
    'elk.layered.spacing.nodeNodeBetweenLayers': direction === 'DOWN' ? '24' : String(STATE_TRANSITION_ELK_LAYER_GAP),
    'elk.layered.spacing.edgeNodeBetweenLayers': direction === 'DOWN' ? '16' : String(STATE_TRANSITION_ELK_EDGE_NODE_GAP),
    'elk.layered.spacing.edgeEdgeBetweenLayers': direction === 'DOWN' ? '10' : String(STATE_TRANSITION_ELK_EDGE_EDGE_GAP),
    'elk.layered.mergeEdges': 'false',
    'elk.separateConnectedComponents': 'true',
    'elk.spacing.componentComponent': '42',
    'elk.randomSeed': '1',
  }
}

function projectedContainerEdges(containerId, childIds, edges, parentById, items) {
  const childSet = new Set(childIds)
  const result = []
  const edgeByKey = new Map()
  for (const edge of edges || []) {
    const sourceId = directChildForEndpoint(edge.sourceId, containerId, childSet, parentById, items)
    const targetId = directChildForEndpoint(edge.targetId, containerId, childSet, parentById, items)
    if (!sourceId || !targetId || sourceId === targetId) continue
    const key = `${sourceId}->${targetId}`
    let projected = edgeByKey.get(key)
    if (!projected) {
      projected = {
        id: `nested:${containerId}:${key}:${result.length}`,
        sourceId,
        targetId,
        routeEdgeIds: [],
      }
      edgeByKey.set(key, projected)
      result.push(projected)
    }
    if (edge.sourceId === sourceId && edge.targetId === targetId) {
      projected.routeEdgeIds.push(edge.id)
    }
  }
  return result
}

function directChildForEndpoint(endpointId, containerId, childSet, parentById, items) {
  let current = String(endpointId || '')
  const seen = new Set()
  while (current && items.has(current) && !seen.has(current)) {
    if (childSet.has(current) && (parentById.get(current) || ROOT_CONTAINER_ID) === containerId) return current
    seen.add(current)
    const parent = parentById.get(current) || ROOT_CONTAINER_ID
    if (parent === containerId && childSet.has(current)) return current
    if (parent === ROOT_CONTAINER_ID) return containerId === ROOT_CONTAINER_ID && childSet.has(current) ? current : null
    if (childSet.has(parent) && (parentById.get(parent) || ROOT_CONTAINER_ID) === containerId) return parent
    current = parent
  }
  return null
}

function applyFallbackPositions(childIds, positions, sizeById, direction) {
  let cursorX = 0
  let cursorY = 0
  for (const id of childIds) {
    if (positions.has(id)) continue
    positions.set(id, { x: cursorX, y: cursorY })
    const size = sizeById.get(id) || { width: X6_NODE_WIDTH, height: X6_NODE_HEIGHT }
    if (direction === 'DOWN') cursorY += size.height + 24
    else cursorX += size.width + 64
  }
}

function manualContainerChildPositions(item, childIds, sizeById, projectedEdges) {
  if (!item || item.kind !== 'state' || projectedEdges.length || childIds.length < 2) return null
  const currentSize = containerSizeFromMetadataForLayout(item.node)
  if (!currentSize?.width) return null
  const layoutWidth = Math.min(currentSize.width, COMPACT_PARALLEL_CONTAINER_MAX_WIDTH)
  const availableRight = Math.max(
    CONTAINER_LEFT_RAIL_SPACE + X6_NODE_WIDTH,
    layoutWidth - CONTAINER_RIGHT_PADDING,
  )
  const positions = new Map()
  let x = CONTAINER_LEFT_RAIL_SPACE
  let y = Math.max(
    CONTAINER_WRAP_HEADER_SPACE,
    containerTitleHeightForLayout(item.node) + 50,
  )
  let rowHeight = 0
  for (const id of childIds) {
    const size = sizeById.get(id) || { width: X6_NODE_WIDTH, height: X6_NODE_HEIGHT }
    if (x > CONTAINER_LEFT_RAIL_SPACE && x + size.width > availableRight) {
      x = CONTAINER_LEFT_RAIL_SPACE
      y += Math.max(rowHeight, X6_NODE_HEIGHT + 12) + CONTAINER_WRAP_GAP_Y
      rowHeight = 0
    }
    positions.set(id, { x, y })
    x += size.width + CONTAINER_WRAP_GAP_X
    rowHeight = Math.max(rowHeight, size.height)
  }
  return positions
}

function compactParallelContainerPositions({
  containerItem,
  childIds,
  childPositions,
  projectedEdges,
  sizeById,
} = {}) {
  if (!containerItem || containerItem.kind !== 'state') return null
  if (!projectedEdges?.length || childIds.length < 2) return null
  const originalBounds = boundsForLayoutChildren(childIds, childPositions, sizeById)
  if (!originalBounds) return null
  const oversized = originalBounds.width > COMPACT_PARALLEL_CONTAINER_MAX_WIDTH
  if (!oversized) return null

  const ranks = rankContainerChildren(childIds, projectedEdges)
  const columns = Array.from(groupIdsByRank(childIds, ranks).entries())
    .sort(([rankA], [rankB]) => rankA - rankB)
    .map(([rank, ids]) => ({
      rank,
      ids: ids.sort((a, b) => layoutPositionSortKey(childPositions.get(a)) - layoutPositionSortKey(childPositions.get(b))),
      width: Math.max(...ids.map((id) => (sizeById.get(id) || { width: X6_NODE_WIDTH }).width)),
    }))
  if (!columns.length) return null

  const contentMaxWidth = Math.max(
    X6_NODE_WIDTH,
    COMPACT_PARALLEL_CONTAINER_MAX_WIDTH - CONTAINER_LEFT_RAIL_SPACE - CONTAINER_RIGHT_PADDING,
  )
  const positions = new Map()
  let segmentColumns = []
  let segmentWidth = 0
  let segmentY = Math.max(
    CONTAINER_WRAP_HEADER_SPACE,
    containerTitleHeightForLayout(containerItem.node) + 50,
  )

  function flushSegment() {
    if (!segmentColumns.length) return
    let x = CONTAINER_LEFT_RAIL_SPACE
    let segmentHeight = 0
    for (const column of segmentColumns) {
      let y = segmentY
      let columnHeight = 0
      for (const id of column.ids) {
        const size = sizeById.get(id) || { width: X6_NODE_WIDTH, height: X6_NODE_HEIGHT }
        positions.set(id, { x, y })
        y += size.height + COMPACT_PARALLEL_ROW_GAP
        columnHeight += size.height + COMPACT_PARALLEL_ROW_GAP
      }
      segmentHeight = Math.max(segmentHeight, Math.max(0, columnHeight - COMPACT_PARALLEL_ROW_GAP))
      x += column.width + COMPACT_PARALLEL_COLUMN_GAP
    }
    segmentY += Math.max(segmentHeight, X6_NODE_HEIGHT) + COMPACT_PARALLEL_SEGMENT_GAP_Y
    segmentColumns = []
    segmentWidth = 0
  }

  for (const column of columns) {
    const nextWidth = segmentColumns.length
      ? segmentWidth + COMPACT_PARALLEL_COLUMN_GAP + column.width
      : column.width
    if (segmentColumns.length && nextWidth > contentMaxWidth) flushSegment()
    segmentColumns.push(column)
    segmentWidth = segmentColumns.length === 1
      ? column.width
      : segmentWidth + COMPACT_PARALLEL_COLUMN_GAP + column.width
  }
  flushSegment()

  if (positions.size !== childIds.length) return null
  return {
    positions,
    oversized,
    originalWidth: originalBounds.width,
  }
}

function boundsForLayoutChildren(childIds, positions, sizeById) {
  let left = Infinity
  let top = Infinity
  let right = -Infinity
  let bottom = -Infinity
  for (const id of childIds || []) {
    const position = positions.get(id)
    if (!position) continue
    const size = sizeById.get(id) || { width: X6_NODE_WIDTH, height: X6_NODE_HEIGHT }
    left = Math.min(left, position.x)
    top = Math.min(top, position.y)
    right = Math.max(right, position.x + size.width)
    bottom = Math.max(bottom, position.y + size.height)
  }
  if (!Number.isFinite(left) || !Number.isFinite(top)) return null
  return {
    left,
    top,
    right,
    bottom,
    width: right - left,
    height: bottom - top,
  }
}

function rankContainerChildren(childIds, projectedEdges) {
  const childSet = new Set(childIds)
  const incomingCount = new Map(childIds.map((id) => [id, 0]))
  const outgoing = new Map(childIds.map((id) => [id, []]))
  const rank = new Map(childIds.map((id) => [id, 0]))
  for (const edge of projectedEdges || []) {
    if (!childSet.has(edge.sourceId) || !childSet.has(edge.targetId)) continue
    outgoing.get(edge.sourceId).push(edge.targetId)
    incomingCount.set(edge.targetId, (incomingCount.get(edge.targetId) || 0) + 1)
  }
  const queue = childIds.filter((id) => (incomingCount.get(id) || 0) === 0)
  const visited = new Set()
  while (queue.length) {
    const id = queue.shift()
    if (visited.has(id)) continue
    visited.add(id)
    for (const targetId of outgoing.get(id) || []) {
      rank.set(targetId, Math.max(rank.get(targetId) || 0, (rank.get(id) || 0) + 1))
      incomingCount.set(targetId, (incomingCount.get(targetId) || 0) - 1)
      if ((incomingCount.get(targetId) || 0) === 0) queue.push(targetId)
    }
  }
  let fallbackRank = Math.max(0, ...Array.from(rank.values()))
  for (const id of childIds) {
    if (visited.has(id)) continue
    fallbackRank += 1
    rank.set(id, fallbackRank)
  }
  return rank
}

function groupIdsByRank(childIds, ranks) {
  const groups = new Map()
  for (const id of childIds || []) {
    const rank = ranks.get(id) || 0
    if (!groups.has(rank)) groups.set(rank, [])
    groups.get(rank).push(id)
  }
  return groups
}

function layoutPositionSortKey(position) {
  if (!position) return 0
  return (finiteNumber(position.y) ?? 0) * 10000 + (finiteNumber(position.x) ?? 0)
}

function containerSizeFromChildren(item, childIds, positions, sizeById, { preserveCurrentWidth = false } = {}) {
  const titleHeight = containerTitleHeightForLayout(item?.node)
  const headerSpace = Math.max(CONTAINER_HEADER_SPACE, titleHeight + 30)
  const currentSize = preserveCurrentWidth ? containerSizeFromMetadataForLayout(item?.node) : null
  const preservedWidth = currentSize?.width
    ? Math.min(currentSize.width, COMPACT_PARALLEL_CONTAINER_MAX_WIDTH)
    : 0
  let maxRight = CONTAINER_LEFT_RAIL_SPACE
  let maxBottom = headerSpace
  for (const id of childIds) {
    const position = positions.get(id) || { x: 0, y: 0 }
    const size = sizeById.get(id) || { width: X6_NODE_WIDTH, height: X6_NODE_HEIGHT }
    maxRight = Math.max(maxRight, position.x + size.width)
    maxBottom = Math.max(maxBottom, position.y + size.height)
  }
  return {
    width: Math.max(
      CONTAINER_MIN_WIDTH,
      Math.ceil(preservedWidth),
      Math.ceil(maxRight + CONTAINER_RIGHT_PADDING),
    ),
    height: Math.max(
      CONTAINER_MIN_HEIGHT,
      Math.ceil(maxBottom + CONTAINER_BOTTOM_PADDING),
    ),
  }
}

function containerSizeFromMetadataForLayout(node) {
  const size = node?.metadata_json?._network_editor_container
  if (!size || typeof size !== 'object') return null
  const width = finiteNumber(size.width)
  const height = finiteNumber(size.height)
  if (width === null || height === null) return null
  return { width, height }
}

function rootLayoutOffset(rootChildIds, positions, baseX, baseY) {
  if (!rootChildIds.length) return { x: baseX, y: baseY }
  const xs = rootChildIds.map((id) => positions.get(id)?.x).filter((value) => Number.isFinite(value))
  const ys = rootChildIds.map((id) => positions.get(id)?.y).filter((value) => Number.isFinite(value))
  const minX = xs.length ? Math.min(...xs) : 0
  const minY = ys.length ? Math.min(...ys) : 0
  return {
    x: Math.round(baseX - minX),
    y: Math.round(baseY - minY),
  }
}

function nodeDimensionsForLayout(node, kind) {
  if (kind === 'relay' || isTransitionRelayNode(node)) {
    return { width: DEFAULT_RELAY_SIZE, height: DEFAULT_RELAY_SIZE }
  }
  const label = String(node?.name || node?.code || node?.id || '')
  const transition = stateTransitionSummaryForLayout(node)
  const warningText = stateTransitionWarningTextForLayout(node)
  const longestUnits = Math.max(
    Math.min(28, textUnits(label)),
    Math.min(24, textUnits(transition)),
  )
  const width = Math.min(
    X6_NODE_MAX_WIDTH,
    Math.max(X6_NODE_WIDTH, Math.ceil(X6_NODE_TEXT_SIDE_SPACE + longestUnits * 6)),
  )
  const summaryLines = transition ? 1 : 0
  const warningLines = warningText ? 1 : 0
  const height = Math.max(
    X6_NODE_HEIGHT,
    X6_NODE_VERTICAL_SPACE +
      X6_NODE_NAME_LINE_HEIGHT +
      summaryLines * X6_NODE_SUMMARY_LINE_HEIGHT +
      warningLines * X6_NODE_WARNING_HEIGHT,
  )
  return { width, height }
}

function stateTransitionSummaryForLayout(node) {
  const transition = node?.stateTransition
  if (!transition) return ''
  const realizer = shortRealizerLabel(transition.realizerLabel)
  if (transition.isInitialSource || realizer === '起始条件') return '起始条件'
  const preconditionCount = Number(transition.preconditionCount || 0)
  return `${realizer} / pre ${preconditionCount}`
}

function stateTransitionWarningTextForLayout(node) {
  const warnings = node?.stateTransition?.warnings
  return Array.isArray(warnings) && warnings.length ? warnings.join(' / ') : ''
}

function shortRealizerLabel(label) {
  const value = String(label || '').trim()
  if (!value || value === '待补达成活动') return '待补'
  return value
}

function containerTitleHeightForLayout(node) {
  return stateTransitionWarningTextForLayout(node) ? 52 : 42
}

function isTransitionRelayNode(node) {
  return !!node?._network_editor_transition_relay ||
    node?.activity_type === 'transition_relay' ||
    !!node?.metadata_json?._network_editor_transition_relay
}

function textUnits(value) {
  return Array.from(String(value ?? '')).reduce((total, char) => {
    const code = char.codePointAt(0) || 0
    return total + (code > 255 ? 2 : 1)
  }, 0)
}

function finiteNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}
