<template>
  <div
    ref="hostRef"
    class="x6-network-canvas"
    data-testid="network-editor-x6-canvas"
    :style="canvasHostStyle"
  />
</template>

<script setup>
import { Graph, Shape } from '@antv/x6'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  NETWORK_EDITOR_NODE_MAX_WIDTH,
  STATE_TRANSITION_COLUMN_CLEARANCE,
  STATE_TRANSITION_PROXY_LABEL_OFFSET,
  STATE_TRANSITION_PROXY_OBSTACLE_PADDING,
  STATE_TRANSITION_ROW_CLEARANCE,
} from '../networkEditorLayoutMetrics'

const NODE_WIDTH = 168
const NODE_HEIGHT = 44
const RELAY_NODE_WIDTH = 132
const RELAY_NODE_HEIGHT = 44
const NODE_MAX_WIDTH = NETWORK_EDITOR_NODE_MAX_WIDTH
const NODE_TEXT_SIDE_SPACE = 54
const NODE_NAME_LINE_HEIGHT = 16
const NODE_SUMMARY_LINE_HEIGHT = 14
const NODE_WARNING_HEIGHT = 16
const NODE_VERTICAL_SPACE = 14
const CONTAINER_MIN_WIDTH = 220
const CONTAINER_MIN_HEIGHT = 104
const CONTAINER_HEADER_SPACE = 66
const CONTAINER_LEFT_RAIL_SPACE = 62
const CONTAINER_RIGHT_PADDING = 34
const CONTAINER_BOTTOM_PADDING = 28
const CONTAINER_TITLE_CHILD_GAP = 40
const CONTAINER_NODE_GAP = 28
const CONTAINER_OVERLAP_GAP = 36
const WRAPPED_FLOW_MAX_COLUMNS = 3
const WRAPPED_FLOW_COLUMN_GAP = 34
const WRAPPED_FLOW_ROW_GAP = 42
const WRAPPED_FLOW_ROW_TOLERANCE = 34
const EDGE_RAIL_GAP = 28
const EDGE_BUS_STUB_GAP = 16
const EDGE_LONG_ROUTE_DELTA = 86
const EDGE_SHORT_ROUTE_GAP = 18
const EDGE_MAX_AUTO_VERTICES = 4
const EDGE_ROUTE_STALE_TOLERANCE = 42
const RELAY_COLLISION_PADDING = 10
const RELAY_COLLISION_STEP = 56
const RELAY_COLLISION_MAX_STEPS = 80
const STATE_DEFAULT_X = 80
const ACTIVITY_DEFAULT_X = 520
const TOP_PADDING = 48
const ROW_GAP = 70
const CANVAS_MIN_WIDTH = 980
const CANVAS_MIN_HEIGHT = 640
const CANVAS_CONTENT_PADDING_X = 320
const CANVAS_CONTENT_PADDING_Y = 260
const INPUT_PORT_ID = 'input'
const OUTPUT_PORT_ID = 'output'
const NODE_ACTION_EVENT_HANDLED = '__networkEditorNodeActionHandled'
const NODE_ACTION_BOUND_ATTR = 'data-network-editor-action-bound'
const TEMP_CONNECTION_EDGE_ID = 'temporary-connection-preview'
const POINTER_CONTROL_SELECTOR = '[data-action], button, input, textarea, select, a[href], [contenteditable="true"]'

let shapesRegistered = false
let hostResizeObserver = null
let lastNodeAction = null

const props = defineProps({
  stateNodes: {
    type: Array,
    default: () => [],
  },
  activityNodes: {
    type: Array,
    default: () => [],
  },
  edges: {
    type: Array,
    default: () => [],
  },
  selectedStateId: {
    type: [Number, String],
    default: null,
  },
  selectedActivityGraphId: {
    type: [Number, String],
    default: null,
  },
  isEditMode: {
    type: Boolean,
    default: false,
  },
  canMutate: {
    type: Boolean,
    default: false,
  },
  canvasZoom: {
    type: Number,
    default: 1,
  },
  stateRootIds: {
    type: Array,
    default: () => [],
  },
  stateDepth: {
    type: Number,
    default: 1,
  },
  expandedStateGraphIds: {
    type: Array,
    default: () => [],
  },
  activityScopeIds: {
    type: Array,
    default: () => [],
  },
  activityDepth: {
    type: Number,
    default: 1,
  },
  viewportResetToken: {
    type: Number,
    default: 0,
  },
  showEditActions: {
    type: Boolean,
    default: true,
  },
})

const emit = defineEmits([
  'select-state',
  'select-activity',
  'toggle-state-expansion',
  'toggle-activity-expansion',
  'edit-state',
  'edit-activity',
  'create-state-inside',
  'create-activity-inside',
  'layout-change',
  'container-resize',
  'blank-dblclick',
  'blank-contextmenu',
  'proxy-edge-click',
  'proxy-edge-dblclick',
  'node-hover-change',
])

const hostRef = ref(null)
const graphRef = ref(null)
const graphCanvasSize = ref({ width: CANVAS_MIN_WIDTH, height: CANVAS_MIN_HEIGHT })
const rendering = ref(false)
const resizing = ref(null)
const movingContainer = ref(null)
const movingNode = ref(null)
const canvasPan = ref(null)

const stateIndex = computed(() => new Map(props.stateNodes.map((node, index) => [node.id, index])))
const activityIndex = computed(() => new Map(props.activityNodes.map((node, index) => [node.id, index])))
const canvasHostStyle = computed(() => ({
  minWidth: `${graphCanvasSize.value.width}px`,
  minHeight: `${graphCanvasSize.value.height}px`,
}))

onMounted(async () => {
  registerShapes()
  await nextTick()
  hostRef.value?.addEventListener('click', handleHtmlActionClick, true)
  document.addEventListener('click', handleHtmlActionClick, true)
  hostRef.value?.addEventListener('pointerdown', handleCanvasPointerDown, true)
  hostRef.value?.addEventListener('mousedown', handleCanvasPointerDown, true)
  hostRef.value?.addEventListener('contextmenu', handleHostContextMenu, true)
  hostRef.value?.addEventListener('dragstart', suppressCanvasPanDefault, true)
  hostRef.value?.addEventListener('selectstart', suppressCanvasPanDefault, true)
  createGraph()
  renderGraph()
  observeHostResize()
  window.addEventListener('resize', resizeGraph)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeGraph)
  hostResizeObserver?.disconnect()
  hostResizeObserver = null
  hostRef.value?.removeEventListener('click', handleHtmlActionClick, true)
  document.removeEventListener('click', handleHtmlActionClick, true)
  hostRef.value?.removeEventListener('pointerdown', handleCanvasPointerDown, true)
  hostRef.value?.removeEventListener('mousedown', handleCanvasPointerDown, true)
  hostRef.value?.removeEventListener('contextmenu', handleHostContextMenu, true)
  hostRef.value?.removeEventListener('dragstart', suppressCanvasPanDefault, true)
  hostRef.value?.removeEventListener('selectstart', suppressCanvasPanDefault, true)
  stopResizeListeners()
  stopContainerMoveListeners()
  stopNodeMoveListeners()
  stopCanvasPanListeners()
  stopCanvasPanGlobalSuppression()
  graphRef.value?.dispose()
  graphRef.value = null
})

watch(
  () => [
    props.stateNodes,
    props.activityNodes,
    props.edges,
    props.selectedStateId,
    props.selectedActivityGraphId,
    props.isEditMode,
    props.canMutate,
    props.stateRootIds,
    props.stateDepth,
    props.expandedStateGraphIds,
    props.activityScopeIds,
    props.activityDepth,
  ],
  () => renderGraph(),
  { deep: true },
)

watch(
  () => props.canvasZoom,
  (zoom) => {
    graphRef.value?.zoomTo(normalizeZoom(zoom))
  },
)

watch(
  () => props.viewportResetToken,
  async () => {
    await nextTick()
    resetViewportToContentOrigin()
  },
)

function registerShapes() {
  if (shapesRegistered) return
  shapesRegistered = true

  Shape.HTML.register({
    shape: 'network-state-node',
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
    html: (cell) => renderNodeHtml(cell.getData()),
    effect: ['data'],
  })

  Shape.HTML.register({
    shape: 'network-activity-node',
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
    html: (cell) => renderNodeHtml(cell.getData()),
    effect: ['data'],
  })

  Shape.HTML.register({
    shape: 'network-state-container',
    width: CONTAINER_MIN_WIDTH,
    height: CONTAINER_MIN_HEIGHT,
    html: (cell) => renderContainerBodyHtml(cell.getData()),
    effect: ['data', 'size'],
  })

  Shape.HTML.register({
    shape: 'network-activity-container',
    width: CONTAINER_MIN_WIDTH,
    height: CONTAINER_MIN_HEIGHT,
    html: (cell) => renderContainerBodyHtml(cell.getData()),
    effect: ['data', 'size'],
  })

  Shape.HTML.register({
    shape: 'network-container-title',
    width: CONTAINER_MIN_WIDTH,
    height: 42,
    html: (cell) => renderContainerTitleHtml(cell.getData()),
    effect: ['data', 'size'],
  })
}

function createGraph() {
  if (!hostRef.value) return
  graphRef.value = new Graph({
    container: hostRef.value,
    width: hostRef.value.clientWidth || CANVAS_MIN_WIDTH,
    height: hostRef.value.clientHeight || CANVAS_MIN_HEIGHT,
    background: { color: '#f8fafc' },
    grid: {
      size: 20,
      visible: true,
      type: 'mesh',
      args: [
        { color: '#e5edf7', thickness: 1 },
        { color: '#d6e0ee', thickness: 1, factor: 5 },
      ],
    },
    panning: {
      enabled: true,
      modifiers: ['alt'],
    },
    mousewheel: {
      enabled: true,
      modifiers: ['ctrl', 'meta'],
      minScale: 0.65,
      maxScale: 1.6,
    },
    connecting: {
      allowBlank: false,
      allowLoop: false,
      allowNode: false,
      allowEdge: false,
      highlight: true,
      snap: {
        radius: 24,
      },
      createEdge: createTemporaryEdge,
      validateMagnet,
      validateConnection,
    },
    embedding: {
      enabled: true,
    },
    interacting: () => ({
      nodeMovable: false,
      edgeMovable: false,
      arrowheadMovable: false,
      vertexMovable: false,
      vertexAddable: false,
      vertexDeletable: false,
    }),
  })

  graphRef.value.on('node:click', handleNodeClick)
  graphRef.value.on('node:mouseenter', handleNodeMouseEnter)
  graphRef.value.on('node:mouseleave', handleNodeMouseLeave)
  graphRef.value.on('node:mousedown', handleNodeMouseDown)
  graphRef.value.on('node:dblclick', handleNodeDoubleClick)
  graphRef.value.on('node:contextmenu', handleNodeContextMenu)
  graphRef.value.on('edge:click', handleEdgeClick)
  graphRef.value.on('edge:dblclick', handleEdgeDoubleClick)
  graphRef.value.on('blank:dblclick', ({ e, x, y }) => {
    emit('blank-dblclick', { x, y, event: e })
  })
  graphRef.value.on('blank:contextmenu', ({ e, x, y }) => {
    e?.preventDefault?.()
    e?.stopPropagation?.()
    const point = e ? clientPointToLocal(e.clientX, e.clientY) : { x, y }
    emit('blank-contextmenu', { x: point?.x, y: point?.y, event: e })
  })
  graphRef.value.on('node:moved', ({ node }) => emitNodeMove(node))
}

function createTemporaryEdge() {
  return new Shape.Edge({
    id: TEMP_CONNECTION_EDGE_ID,
    zIndex: 30,
    attrs: {
      line: {
        stroke: '#64748b',
        strokeWidth: 2,
        strokeDasharray: '5 4',
        targetMarker: {
          name: 'block',
          width: 8,
          height: 6,
        },
      },
    },
    router: {
      name: 'manhattan',
      args: { padding: 16 },
    },
    connector: {
      name: 'rounded',
      args: { radius: 8 },
    },
  })
}

function nodePorts() {
  return {
    groups: {
      in: {
        position: 'left',
        attrs: {
          circle: {
            r: 1,
            magnet: false,
            stroke: 'transparent',
            strokeWidth: 0,
            fill: 'transparent',
            opacity: 0,
            cursor: 'default',
            style: { pointerEvents: 'none' },
          },
        },
      },
      out: {
        position: 'right',
        attrs: {
          circle: {
            r: 1,
            magnet: false,
            stroke: 'transparent',
            strokeWidth: 0,
            fill: 'transparent',
            opacity: 0,
            cursor: 'default',
            style: { pointerEvents: 'none' },
          },
        },
      },
    },
    items: [
      { id: INPUT_PORT_ID, group: 'in' },
      { id: OUTPUT_PORT_ID, group: 'out' },
    ],
  }
}

function validateMagnet() {
  return false
}

function validateConnection() {
  return false
}

function renderGraph() {
  const graph = graphRef.value
  if (!graph) return

  rendering.value = true
  const { cells, canvasSize } = buildCells()
  graph.clearCells()
  graph.fromJSON({ cells })

  const nextSize = graphSizeFor(canvasSize)
  graph.resize(nextSize.width, nextSize.height)
  graphCanvasSize.value = nextSize
  graph.zoomTo(normalizeZoom(props.canvasZoom))
  rendering.value = false
  queueHtmlActionBinding()
}

function queueHtmlActionBinding() {
  nextTick(() => {
    bindHtmlActionHandlers()
    window.setTimeout(bindHtmlActionHandlers, 0)
  })
}

function bindHtmlActionHandlers() {
  const host = hostRef.value
  if (!host) return
  host.querySelectorAll('[data-action]').forEach((element) => {
    if (element.getAttribute(NODE_ACTION_BOUND_ATTR) === '1') return
    element.setAttribute(NODE_ACTION_BOUND_ATTR, '1')
    element.addEventListener('click', handleHtmlActionClick, true)
  })
}

function buildCells() {
  const nodeCells = []
  const nodeCellIds = new Set()
  const containerRoots = new Set()
  const displayLayout = buildExpandedDisplayLayout()
  const stateContainers = displayLayout.stateContainers
  const activityContainers = displayLayout.activityContainers
  const edgeRouteContext = buildEdgeRouteContext(displayLayout, props.edges)

  for (const container of stateContainers) {
    containerRoots.add(container.node.id)
    nodeCells.push(createContainerCell(container, 'state'))
    nodeCells.push(createContainerTitleCell(container, 'state'))
  }
  for (const container of activityContainers) {
    containerRoots.add(container.node.id)
    nodeCells.push(createContainerCell(container, 'activity'))
    nodeCells.push(createContainerTitleCell(container, 'activity'))
  }

  for (const node of displayLayout.stateNodes) {
    if (!containerRoots.has(node.id)) {
      nodeCells.push(createNodeCell(node, 'state'))
    }
    nodeCellIds.add(node.id)
  }

  for (const node of displayLayout.activityNodes) {
    if (!containerRoots.has(node.id)) {
      nodeCells.push(createNodeCell(node, 'activity'))
    }
    nodeCellIds.add(node.id)
  }

  const edgeCells = props.edges
    .map((edge) => createEdgeCell(edge, edgeRouteContext))
    .filter(Boolean)
    .filter((edge) => nodeCellIds.has(edge.source.cell) && nodeCellIds.has(edge.target.cell))
  const cells = [...edgeCells, ...nodeCells]

  const canvasSize = cells.reduce(
    (size, cell) => {
      if (cell.shape === 'edge') return size
      const x = finiteNumber(cell.x) ?? finiteNumber(cell.position?.x) ?? 0
      const y = finiteNumber(cell.y) ?? finiteNumber(cell.position?.y) ?? 0
      const width = finiteNumber(cell.width) ?? finiteNumber(cell.size?.width) ?? NODE_WIDTH
      const height = finiteNumber(cell.height) ?? finiteNumber(cell.size?.height) ?? NODE_HEIGHT
      return {
        width: Math.max(size.width, Math.ceil(x + width + CANVAS_CONTENT_PADDING_X)),
        height: Math.max(size.height, Math.ceil(y + height + CANVAS_CONTENT_PADDING_Y)),
      }
    },
    { width: CANVAS_MIN_WIDTH, height: CANVAS_MIN_HEIGHT },
  )

  return { cells, canvasSize }
}

function buildExpandedDisplayLayout() {
  const innerShifts = expandedContainerInnerDisplayShifts([
    ...buildStateContainers(props.stateNodes, props.activityNodes).map((container) => containerGroup(container, 'state')),
    ...buildActivityContainers(props.activityNodes).map((container) => containerGroup(container, 'activity')),
  ])
  const compactStateNodes = props.stateNodes.map((node) => nodeWithDisplayShift(node, 'state', innerShifts))
  const compactActivityNodes = props.activityNodes.map((node) => nodeWithDisplayShift(node, 'activity', innerShifts))
  const targetAlignedActivityNodes = alignTransitionRelaysToTargets(compactStateNodes, compactActivityNodes)
  const baseStateContainers = buildStateContainers(compactStateNodes, targetAlignedActivityNodes)
  const baseActivityContainers = buildActivityContainers(compactActivityNodes)
  const shifts = expandedContainerDisplayShifts([
    ...baseStateContainers.map((container) => containerGroup(container, 'state')),
    ...baseActivityContainers.map((container) => containerGroup(container, 'activity')),
  ])
  const siblingShifts = expandedStateContainerSiblingDisplayShifts(
    baseStateContainers.map((container) => containerGroup(container, 'state')),
    compactStateNodes,
  )
  const nodeShifts = mergeNodeShifts(
    innerShifts,
    nodeShiftsForContainerShifts(shifts, compactActivityNodes),
    siblingShifts,
  )
  const stateNodes = props.stateNodes.map((node) => nodeWithDisplayShift(node, 'state', nodeShifts))
  const activityNodes = avoidTransitionRelayDisplayCollisions(
    stateNodes,
    props.activityNodes.map((node) => nodeWithDisplayShift(node, 'activity', nodeShifts)),
  )
  const stateContainers = expandStateContainerAncestorsForNestedBounds(
    buildStateContainers(stateNodes, activityNodes),
  )
  return {
    stateNodes,
    activityNodes,
    stateContainers,
    activityContainers: buildActivityContainers(activityNodes),
  }
}

function avoidTransitionRelayDisplayCollisions(stateNodes, activityNodes) {
  const occupiedRects = [
    ...stateNodes.map((node) => inflateRect(currentNodeRect(node, 'state', new Map()), RELAY_COLLISION_PADDING)),
    ...buildStateContainers(stateNodes, activityNodes).map((container) => inflateRect(containerTitleRect(container), RELAY_COLLISION_PADDING)),
  ]
  const placedRelayRects = []

  return activityNodes.map((node) => {
    if (!isTransitionRelayNode(node)) return node
    if (node?._network_editor_preserve_relay_layout) return node
    if (transitionRelayHasAutoRoute(node)) return node
    const start = transitionRelayTargetPosition(node, stateNodes) || nodePosition(node, 'activity')
    const size = nodeDimensions(node, 'activity')
    let position = { ...start }

    for (let step = 0; step < RELAY_COLLISION_MAX_STEPS; step += 1) {
      const rect = inflateRect(rectForPosition(position, size), RELAY_COLLISION_PADDING)
      const collides = occupiedRects.some((item) => rectsOverlap(rect, item)) ||
        placedRelayRects.some((item) => rectsOverlap(rect, item))
      if (!collides) {
        placedRelayRects.push(rect)
        return nodeWithDisplayPosition(node, position)
      }
      position = {
        x: start.x,
        y: start.y + (step + 1) * RELAY_COLLISION_STEP,
      }
    }

    const fallbackRect = inflateRect(rectForPosition(position, size), RELAY_COLLISION_PADDING)
    placedRelayRects.push(fallbackRect)
    return nodeWithDisplayPosition(node, position)
  })
}

function alignTransitionRelaysToTargets(stateNodes, activityNodes) {
  return (activityNodes || []).map((node) => {
    if (!isTransitionRelayNode(node) || transitionRelayHasAutoRoute(node)) return node
    if (node?._network_editor_preserve_relay_layout) return node
    const position = transitionRelayTargetPosition(node, stateNodes)
    return position ? nodeWithDisplayPosition(node, position) : node
  })
}

function transitionRelayTargetPosition(node, stateNodes) {
  const relayId = String(node?.id || '')
  if (!relayId) return null
  const stateById = new Map((stateNodes || []).map((state) => [String(state.id || ''), state]))
  const targetRects = (props.edges || [])
    .filter((edge) =>
      edge?.type === 'ACTIVITY_TO_STATE' &&
      String(edge.source_id || '') === relayId,
    )
    .map((edge) => stateById.get(String(edge.target_id || '')))
    .filter(Boolean)
    .map((target) => currentNodeRect(target, 'state', new Map()))
  if (!targetRects.length) return null
  const targetLeft = Math.min(...targetRects.map((rect) => rect.left))
  const targetCenterY = targetRects.reduce(
    (total, rect) => total + rect.top + rect.height / 2,
    0,
  ) / targetRects.length
  return {
    x: Math.round(targetLeft - EDGE_SHORT_ROUTE_GAP - RELAY_NODE_WIDTH),
    y: Math.round(targetCenterY - RELAY_NODE_HEIGHT / 2),
  }
}

function transitionRelayHasAutoRoute(node) {
  const relayId = String(node?.id || '')
  if (!relayId) return false
  return (props.edges || []).some((edge) =>
    edge?.autoRoute &&
    (String(edge.source_id || '') === relayId || String(edge.target_id || '') === relayId),
  )
}

function rectForPosition(position, size) {
  return {
    left: position.x,
    top: position.y,
    right: position.x + size.width,
    bottom: position.y + size.height,
    width: size.width,
    height: size.height,
  }
}

function inflateRect(rect, padding) {
  return {
    left: rect.left - padding,
    top: rect.top - padding,
    right: rect.right + padding,
    bottom: rect.bottom + padding,
    width: rect.width + padding * 2,
    height: rect.height + padding * 2,
  }
}

function containerTitleRect(container) {
  const left = finiteNumber(container?.left) ?? finiteNumber(container?.x) ?? 0
  const top = finiteNumber(container?.top) ?? finiteNumber(container?.y) ?? 0
  return {
    left,
    top,
    right: left + container.width,
    bottom: top + container.titleHeight,
    width: container.width,
    height: container.titleHeight,
  }
}

function expandedContainerInnerDisplayShifts(groups) {
  const nodeShifts = new Map()
  const groupByRoot = new Map(groups.map((group) => [displayNodeKey(group.kind, group.container.node.id), group]))
  const ordered = [...groups].sort((a, b) =>
    containerGroupDepth(b) - containerGroupDepth(a) ||
    a.rect.top - b.rect.top ||
    a.rect.left - b.rect.left,
  )
  for (const group of ordered) {
    const items = expandedContainerLayoutItems(group, groupByRoot, nodeShifts)
    if (!items.length) continue
    if (items.length === 1) continue
    if (items.some((item) => layoutItemHasDraft(item))) continue
    const placements = expandedContainerFlowLayoutPlacements(
      items,
      currentContainerGroupRect(group, nodeShifts),
      group.container.titleHeight,
      group.kind,
    )
    for (const { item, left, top } of placements) {
      const dx = left - item.rect.left
      const dy = top - item.rect.top
      if (Math.abs(dx) >= 0.5 || Math.abs(dy) >= 0.5) {
        applyLayoutItemShift(nodeShifts, group.kind, item, dx, dy)
      }
    }
  }
  return nodeShifts
}

function expandedContainerFlowLayoutPlacements(items, rect, titleHeight, kind) {
  const spacing = expandedContainerFlowSpacing(kind)
  const graph = expandedContainerItemFlowGraph(items)
  if (!graph.edges.length) {
    return linearWrappedFlowPlacements(graph.stableItems, rect, titleHeight, spacing)
  }
  const ranks = expandedContainerItemRanks(graph)
  const byRank = new Map()
  for (const item of graph.orderedItems) {
    const rank = ranks.get(String(item.node.id)) || 0
    if (!byRank.has(rank)) byRank.set(rank, [])
    byRank.get(rank).push(item)
  }
  const maxRank = Math.max(...Array.from(byRank.keys()))
  const placements = []
  let blockY = rect.top + titleHeight + CONTAINER_TITLE_CHILD_GAP

  for (let blockStart = 0; blockStart <= maxRank; blockStart += WRAPPED_FLOW_MAX_COLUMNS) {
    const blockRanks = Array.from({ length: WRAPPED_FLOW_MAX_COLUMNS }, (_, offset) => blockStart + offset)
    const columnWidths = blockRanks.map((rank) =>
      Math.max(NODE_WIDTH, ...(byRank.get(rank) || []).map((item) => item.rect.width)),
    )
    const stackHeights = blockRanks.map((rank) => stackHeight(byRank.get(rank) || [], spacing.nodeGap))
    const blockHeight = Math.max(...stackHeights, NODE_HEIGHT)
    let columnX = rect.left + CONTAINER_LEFT_RAIL_SPACE
    for (let index = 0; index < blockRanks.length; index += 1) {
      const rank = blockRanks[index]
      const stack = byRank.get(rank) || []
      const columnWidth = columnWidths[index]
      const stackTop = blockY + Math.round((blockHeight - stackHeights[index]) / 2)
      let itemY = stackTop
      for (const item of stack) {
        placements.push({
          item,
          left: columnX + Math.round((columnWidth - item.rect.width) / 2),
          top: itemY,
        })
        itemY += item.rect.height + spacing.nodeGap
      }
      columnX += columnWidth + spacing.columnGap
    }
    blockY += blockHeight + spacing.rowGap
  }
  return placements
}

function expandedContainerFlowSpacing(kind) {
  if (kind === 'state') {
    return {
      columnGap: STATE_TRANSITION_COLUMN_CLEARANCE,
      rowGap: STATE_TRANSITION_ROW_CLEARANCE,
      nodeGap: STATE_TRANSITION_ROW_CLEARANCE,
    }
  }
  return {
    columnGap: WRAPPED_FLOW_COLUMN_GAP,
    rowGap: WRAPPED_FLOW_ROW_GAP,
    nodeGap: CONTAINER_NODE_GAP,
  }
}

function linearWrappedFlowPlacements(items, rect, titleHeight, spacing) {
  const placements = []
  let cursorY = rect.top + titleHeight + CONTAINER_TITLE_CHILD_GAP
  for (const row of wrappedFlowRows(items)) {
    const rowHeight = Math.max(...row.map((item) => item.rect.height))
    let cursorX = rect.left + CONTAINER_LEFT_RAIL_SPACE
    for (const item of row) {
      placements.push({
        item,
        left: cursorX,
        top: cursorY + Math.round((rowHeight - item.rect.height) / 2),
      })
      cursorX += item.rect.width + spacing.columnGap
    }
    cursorY += rowHeight + spacing.rowGap
  }
  return placements
}

function stackHeight(items, nodeGap = CONTAINER_NODE_GAP) {
  if (!items.length) return 0
  return items.reduce((height, item, index) =>
    height + item.rect.height + (index > 0 ? nodeGap : 0), 0)
}

function expandedContainerItemFlowGraph(items) {
  const stableItems = [...items].sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left)
  const graphIdsByItemId = new Map()
  for (const item of stableItems) {
    const ids = new Set([String(item.node.id), ...(item.nodeIds || []).map((id) => String(id))])
    graphIdsByItemId.set(String(item.node.id), ids)
  }

  const itemIdByGraphId = new Map()
  for (const [itemId, graphIds] of graphIdsByItemId) {
    for (const graphId of graphIds) itemIdByGraphId.set(graphId, itemId)
  }

  const edges = []
  const relayInputs = new Map()
  const relayOutputs = new Map()
  for (const edge of props.edges || []) {
    if (edge?.isTransitionRelayEdge || edge?.source_kind === 'state_transition_relay') {
      if (edge.type === 'STATE_TO_ACTIVITY') {
        const sourceId = itemIdByGraphId.get(String(edge.source_id || ''))
        if (sourceId) {
          const relayId = String(edge.target_id || '')
          if (!relayInputs.has(relayId)) relayInputs.set(relayId, new Set())
          relayInputs.get(relayId).add(sourceId)
        }
      } else if (edge.type === 'ACTIVITY_TO_STATE') {
        const targetId = itemIdByGraphId.get(String(edge.target_id || ''))
        if (targetId) {
          const relayId = String(edge.source_id || '')
          if (!relayOutputs.has(relayId)) relayOutputs.set(relayId, new Set())
          relayOutputs.get(relayId).add(targetId)
        }
      }
      continue
    }
    const sourceId = itemIdByGraphId.get(String(edge.source_id || ''))
    const targetId = itemIdByGraphId.get(String(edge.target_id || ''))
    if (!sourceId || !targetId || sourceId === targetId) continue
    edges.push([sourceId, targetId])
  }
  for (const [relayId, sourceIds] of relayInputs.entries()) {
    for (const sourceId of sourceIds) {
      for (const targetId of relayOutputs.get(relayId) || []) {
        if (!sourceId || !targetId || sourceId === targetId) continue
        edges.push([sourceId, targetId])
      }
    }
  }

  const order = new Map(stableItems.map((item, index) => [String(item.node.id), index]))
  const byId = new Map(stableItems.map((item) => [String(item.node.id), item]))
  const outgoing = new Map(stableItems.map((item) => [String(item.node.id), new Set()]))
  const indegree = new Map(stableItems.map((item) => [String(item.node.id), 0]))

  for (const [sourceId, targetId] of edges) {
    const targets = outgoing.get(sourceId)
    if (!targets || targets.has(targetId)) continue
    targets.add(targetId)
    indegree.set(targetId, (indegree.get(targetId) || 0) + 1)
  }

  const graph = { stableItems, edges, order, byId, outgoing, indegree }
  return {
    ...graph,
    orderedItems: topologicalExpandedContainerItems(graph),
  }
}

function topologicalExpandedContainerItems(graph) {
  const indegree = new Map(graph.indegree)
  const queue = graph.stableItems
    .filter((item) => (indegree.get(String(item.node.id)) || 0) === 0)
    .sort((a, b) => (graph.order.get(String(a.node.id)) || 0) - (graph.order.get(String(b.node.id)) || 0))
  const result = []
  const emitted = new Set()

  while (queue.length) {
    const item = queue.shift()
    const itemId = String(item.node.id)
    if (emitted.has(itemId)) continue
    emitted.add(itemId)
    result.push(item)
    const targets = [...(graph.outgoing.get(itemId) || [])]
      .sort((a, b) => (graph.order.get(a) || 0) - (graph.order.get(b) || 0))
    for (const targetId of targets) {
      indegree.set(targetId, (indegree.get(targetId) || 0) - 1)
      if ((indegree.get(targetId) || 0) === 0 && graph.byId.has(targetId)) {
        queue.push(graph.byId.get(targetId))
        queue.sort((a, b) => (graph.order.get(String(a.node.id)) || 0) - (graph.order.get(String(b.node.id)) || 0))
      }
    }
  }

  if (result.length === graph.stableItems.length) return result
  return [
    ...result,
    ...graph.stableItems.filter((item) => !emitted.has(String(item.node.id))),
  ]
}

function expandedContainerItemRanks(graph) {
  const ranks = new Map(graph.stableItems.map((item) => [String(item.node.id), 0]))
  for (const item of graph.orderedItems) {
    const itemId = String(item.node.id)
    const rank = ranks.get(itemId) || 0
    for (const targetId of graph.outgoing.get(itemId) || []) {
      ranks.set(targetId, Math.max(ranks.get(targetId) || 0, rank + 1))
    }
  }
  return ranks
}

function wrappedFlowRows(items) {
  const rows = []
  for (let index = 0; index < items.length; index += WRAPPED_FLOW_MAX_COLUMNS) {
    rows.push(items.slice(index, index + WRAPPED_FLOW_MAX_COLUMNS))
  }
  return rows
}

function expandedContainerLayoutItems(group, groupByRoot, shifts) {
  return directContainerChildren(group)
    .map((child) => {
      const childGroup = groupByRoot.get(displayNodeKey(group.kind, child.id))
      if (childGroup && childGroup.key !== group.key) {
        const nodeRect = currentNodeRect(child, group.kind, shifts)
        return {
          node: child,
          group: childGroup,
          nodes: containerGroupNodes(childGroup),
          nodeIds: Array.from(childGroup.nodeIds || []),
          rect: nodeRect,
        }
      }
      return {
        node: child,
        group: null,
        nodes: [child],
        nodeIds: [child.id],
        rect: currentNodeRect(child, group.kind, shifts),
      }
    })
    .filter((item) => item.rect && Number.isFinite(item.rect.top) && Number.isFinite(item.rect.left))
    .sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left)
}

function directContainerChildren(group) {
  const children = group.container.children || []
  const direct = children.filter((child) => isDirectContainerChild(group.container.node, child, group.kind, children))
  return direct.length ? direct : children
}

function isDirectContainerChild(parent, child, kind, siblings) {
  if (kind === 'state') {
    if (String(child.parent_id || '') === String(parent.state_node_id || '')) return true
    if (String(child.parent_state_node_id || '') === String(parent.state_node_id || '')) return true
    if (String(child.primary_parent_graph_id || '') === String(parent.id || '')) return true
    if ((child.reference_parent_ids || []).some((id) => String(id) === String(parent.state_node_id || ''))) return true
    return !siblings.some((candidate) =>
      candidate.id !== child.id &&
      candidate.state_node_id !== parent.state_node_id &&
      candidate.state_node_id !== child.state_node_id &&
      statePathContains(child, candidate.state_node_id),
    )
  }
  if (String(child.parent_id || '') === String(parent.activity_node_id || '')) return true
  if (String(child.parent_graph_id || '') === String(parent.id || '')) return true
  return !siblings.some((candidate) =>
    candidate.id !== child.id &&
    candidate.activity_node_id !== parent.activity_node_id &&
    candidate.activity_node_id !== child.activity_node_id &&
    activityPathContains(child, candidate.activity_node_id),
  )
}

function layoutItemHasDraft(item) {
  return !!item.node?._network_editor_has_layout_draft
}

function applyLayoutItemShift(shifts, kind, item, dx, dy) {
  for (const nodeId of item.nodeIds || []) {
    addNodeShift(shifts, kind, nodeId, { dx, dy })
  }
}

function containerGroupNodes(group) {
  return [group.container.node, ...(group.container.children || [])]
}

function currentNodeRect(node, kind, shifts) {
  const position = shiftedNodePosition(node, kind, shifts)
  const size = nodeDimensions(node, kind)
  return {
    left: position.x,
    top: position.y,
    right: position.x + size.width,
    bottom: position.y + size.height,
    width: size.width,
    height: size.height,
  }
}

function currentContainerGroupRect(group, shifts) {
  return containerRect(buildContainerModel(group.container.node, group.container.children, group.kind, shifts))
}

function shiftedNodePosition(node, kind, shifts) {
  const position = nodePosition(node, kind)
  const shift = shifts.get(displayNodeKey(kind, node.id)) || { dx: 0, dy: 0 }
  return {
    x: position.x + shift.dx,
    y: position.y + shift.dy,
  }
}

function containerGroupDepth(group) {
  return Number(group?.container?.node?.level || 1)
}

function buildStateContainers(nodes = props.stateNodes, activityNodes = props.activityNodes) {
  return nodes
    .filter((node) => !node.is_leaf && isExpandedNode(node, 'state'))
    .map((node) => {
      const children = nodes.filter((candidate) => (
        candidate.id !== node.id &&
        candidate.state_node_id !== node.state_node_id &&
        statePathContains(candidate, node.state_node_id)
      ))
      if (!children.length) return null
      const container = buildContainerModel(node, children, 'state')
      return expandStateContainerForOwnedRelays(container, activityNodes)
    })
    .filter(Boolean)
}

function expandStateContainerForOwnedRelays(container, activityNodes = []) {
  const ownerId = String(container?.node?.id || '')
  if (!ownerId) return container
  const ownedRelays = (activityNodes || []).filter((node) =>
    isTransitionRelayNode(node) && String(node.parent_graph_id || '') === ownerId,
  )
  if (!ownedRelays.length) return container
  const right = Math.max(container.x + container.width, ...ownedRelays.map((node) => {
    const rect = currentNodeRect(node, 'activity', new Map())
    return rect.right + CONTAINER_RIGHT_PADDING
  }))
  const bottom = Math.max(container.y + container.height, ...ownedRelays.map((node) => {
    const rect = currentNodeRect(node, 'activity', new Map())
    return rect.bottom + CONTAINER_BOTTOM_PADDING
  }))
  return {
    ...container,
    width: Math.ceil(right - container.x),
    height: Math.ceil(bottom - container.y),
  }
}

function expandStateContainerAncestorsForNestedBounds(containers = []) {
  const resolved = new Map(
    (containers || []).map((container) => [String(container?.node?.id || ''), container]),
  )
  const deepestFirst = [...(containers || [])].sort((a, b) =>
    Number(b?.node?.level || 1) - Number(a?.node?.level || 1),
  )

  for (const originalChild of deepestFirst) {
    const childId = String(originalChild?.node?.id || '')
    let nestedBounds = containerRect(resolved.get(childId) || originalChild)
    const ancestors = (containers || [])
      .filter((candidate) =>
        String(candidate?.node?.id || '') !== childId &&
        statePathContains(originalChild.node, candidate?.node?.state_node_id),
      )
      .sort((a, b) => Number(b?.node?.level || 1) - Number(a?.node?.level || 1))

    for (const originalAncestor of ancestors) {
      const ancestorId = String(originalAncestor?.node?.id || '')
      const ancestor = resolved.get(ancestorId) || originalAncestor
      const expanded = expandContainerToContainNestedBounds(ancestor, nestedBounds)
      resolved.set(ancestorId, expanded)
      nestedBounds = containerRect(expanded)
    }
  }

  return (containers || []).map((container) =>
    resolved.get(String(container?.node?.id || '')) || container,
  )
}

function expandContainerToContainNestedBounds(container, nestedBounds) {
  if (!container || !nestedBounds) return container
  const right = Math.max(
    container.x + container.width,
    nestedBounds.right + CONTAINER_RIGHT_PADDING,
  )
  const bottom = Math.max(
    container.y + container.height,
    nestedBounds.bottom + CONTAINER_BOTTOM_PADDING,
  )
  return {
    ...container,
    width: Math.ceil(right - container.x),
    height: Math.ceil(bottom - container.y),
  }
}

function buildActivityContainers(nodes = props.activityNodes) {
  return nodes
    .filter((node) => node.activity_type === 'activity_package' && node.activity_node_id && isExpandedNode(node, 'activity'))
    .map((node) => {
      const children = nodes.filter((candidate) => (
        candidate.id !== node.id &&
        activityPathContains(candidate, node.activity_node_id)
      ))
      if (!children.length) return null
      return buildContainerModel(node, children, 'activity')
    })
    .filter(Boolean)
}

function nodeDimensions(node, kind) {
  if (isTransitionRelayNode(node)) {
    return { width: RELAY_NODE_WIDTH, height: RELAY_NODE_HEIGHT }
  }
  const label = String(node?.name || node?.code || node?.id || '')
  const transition = stateTransitionSummary(node)
  const warningText = stateTransitionWarningText(node)
  const longestUnits = Math.max(
    Math.min(28, textUnits(label)),
    Math.min(24, textUnits(transition)),
  )
  const width = Math.min(
    NODE_MAX_WIDTH,
    Math.max(NODE_WIDTH, Math.ceil(NODE_TEXT_SIDE_SPACE + longestUnits * 6)),
  )
  const summaryLines = transition ? 1 : 0
  const warningLines = warningText ? 1 : 0
  const height = Math.max(
    NODE_HEIGHT,
    NODE_VERTICAL_SPACE +
      NODE_NAME_LINE_HEIGHT +
      summaryLines * NODE_SUMMARY_LINE_HEIGHT +
      warningLines * NODE_WARNING_HEIGHT,
  )
  return { width, height }
}

function isTransitionRelayNode(node) {
  return !!node?._network_editor_transition_relay ||
    node?.activity_type === 'transition_relay' ||
    !!node?.metadata_json?._network_editor_transition_relay
}

function transitionRelayActivityGraphId(node) {
  return node?.transitionRelayActivityGraphId ||
    node?.metadata_json?._network_editor_transition_relay?.activityGraphId ||
    null
}

function textUnits(value) {
  return Array.from(String(value ?? '')).reduce((total, char) => {
    const code = char.codePointAt(0) || 0
    return total + (code > 255 ? 2 : 1)
  }, 0)
}

function buildContainerModel(node, children, kind, shifts = null) {
  const members = [node, ...children]
  const bounds = memberBounds(members, kind, shifts)
  const titleHeight = containerTitleHeight(node, kind)
  const headerSpace = Math.max(CONTAINER_HEADER_SPACE, titleHeight + 30)
  const savedSize = savedContainerSizeFor(node, kind) || {}
  const anchor = shiftedNodePosition(node, kind, shifts || new Map())
  const anchorsAtCollapsedNode = kind === 'state' && Number(node.level || 1) > 1
  const x = anchorsAtCollapsedNode
    ? Math.max(8, anchor.x)
    : Math.max(8, bounds.x - CONTAINER_LEFT_RAIL_SPACE)
  const y = anchorsAtCollapsedNode
    ? Math.max(8, anchor.y)
    : Math.max(8, bounds.y - headerSpace)
  const width = Math.max(
    CONTAINER_MIN_WIDTH,
    anchorsAtCollapsedNode
      ? bounds.x + bounds.width - x + CONTAINER_RIGHT_PADDING
      : bounds.width + CONTAINER_LEFT_RAIL_SPACE + CONTAINER_RIGHT_PADDING,
    Number(savedSize.width || 0),
  )
  const height = Math.max(
    CONTAINER_MIN_HEIGHT,
    anchorsAtCollapsedNode
      ? bounds.y + bounds.height - y + CONTAINER_BOTTOM_PADDING
      : bounds.height + headerSpace + CONTAINER_BOTTOM_PADDING,
    Number(savedSize.height || 0),
  )
  return {
    node,
    children,
    x,
    y,
    width,
    height,
    titleHeight,
  }
}

function savedContainerSizeFor(node, kind) {
  const savedSize = metadataContainer(node)
  if (!savedSize) return null
  // Focused expansion intentionally ignores stale persisted container sizes,
  // but a size supplied by the active edit session/submitted overlay is the
  // current source of truth and must remain visible immediately.
  if (node?._network_editor_has_container_draft) return savedSize
  if (kind === 'state' && Number(props.stateDepth) !== 0 && props.stateRootIds.length) return null
  if (kind === 'activity' && Number(props.activityDepth) !== 0 && props.activityScopeIds.length) return null
  return savedSize
}

function containerGroup(container, kind) {
  return {
    key: containerGroupKey(container, kind),
    kind,
    container,
    nodeIds: new Set([container.node.id, ...container.children.map((child) => child.id)]),
    rect: containerRect(container),
  }
}

function containerGroupKey(container, kind) {
  return `${kind}:${container.node.id}`
}

function containerRect(container) {
  return {
    left: container.x,
    top: container.y,
    right: container.x + container.width,
    bottom: container.y + container.height,
    width: container.width,
    height: container.height,
  }
}

function expandedContainerDisplayShifts(groups) {
  const ordered = [...groups].sort((a, b) =>
    a.rect.top - b.rect.top ||
    a.rect.left - b.rect.left ||
    String(a.key).localeCompare(String(b.key)),
  )
  const placed = []
  const shifts = new Map()
  for (const group of ordered) {
    let dy = 0
    let shifted = shiftedRect(group.rect, 0, dy)
    let changed = true
    while (changed) {
      changed = false
      for (const previous of placed) {
        if (containerGroupsAreNested(group, previous.group)) continue
        if (!rectsOverlap(shifted, previous.rect, CONTAINER_OVERLAP_GAP)) continue
        dy += previous.rect.bottom + CONTAINER_OVERLAP_GAP - shifted.top
        shifted = shiftedRect(group.rect, 0, dy)
        changed = true
      }
    }
    shifts.set(group.key, { group, dx: 0, dy })
    placed.push({ group, rect: shifted })
  }
  return shifts
}

function expandedStateContainerSiblingDisplayShifts(groups, stateNodes) {
  const shifts = new Map()
  const groupByRoot = new Map(groups.map((group) => [String(group.container.node.id || ''), group]))
  const ordered = [...groups]
    .filter((group) => containerGroupDepth(group) > 1)
    .sort((a, b) => containerGroupDepth(b) - containerGroupDepth(a))

  for (const group of ordered) {
    const owner = group.container.node
    const ownerParent = stateNodeDisplayParentKey(owner)
    if (!ownerParent) continue
    const container = containerRect(group.container)
    const anchor = currentNodeRect(owner, 'state', new Map())
    const handledGroups = new Set()

    for (const sibling of stateNodes || []) {
      const siblingId = String(sibling.id || '')
      if (!siblingId || group.nodeIds.has(sibling.id)) continue
      if (Number(sibling.level || 1) !== Number(owner.level || 1)) continue
      if (stateNodeDisplayParentKey(sibling) !== ownerParent) continue

      const siblingGroup = groupByRoot.get(siblingId)
      if (siblingGroup && handledGroups.has(siblingGroup.key)) continue
      const nodeIds = siblingGroup ? [...siblingGroup.nodeIds] : [sibling.id]
      const rect = siblingGroup
        ? currentContainerGroupRect(siblingGroup, shifts)
        : currentNodeRect(sibling, 'state', shifts)
      if (!rectsOverlap(container, rect, CONTAINER_OVERLAP_GAP)) continue

      const sameRow = Math.abs(
        (rect.top + rect.height / 2) - (anchor.top + anchor.height / 2),
      ) <= Math.max(anchor.height, rect.height)
      const shift = sameRow
        ? { dx: container.right + CONTAINER_OVERLAP_GAP - rect.left, dy: 0 }
        : { dx: 0, dy: container.bottom + CONTAINER_OVERLAP_GAP - rect.top }
      for (const nodeId of nodeIds) addNodeShift(shifts, 'state', nodeId, shift)
      if (siblingGroup) handledGroups.add(siblingGroup.key)
    }
  }
  return shifts
}

function stateNodeDisplayParentKey(node) {
  return String(
    node?.primary_parent_graph_id ||
    node?.reference_parent_graph_id ||
    node?.parent_graph_id ||
    node?.parent_state_node_id ||
    node?.parent_id ||
    '',
  )
}

function shiftedRect(rect, dx, dy) {
  return {
    left: rect.left + dx,
    top: rect.top + dy,
    right: rect.right + dx,
    bottom: rect.bottom + dy,
    width: rect.width,
    height: rect.height,
  }
}

function rectsOverlap(a, b, gap = 0) {
  return a.left < b.right + gap &&
    a.right + gap > b.left &&
    a.top < b.bottom + gap &&
    a.bottom + gap > b.top
}

function containerGroupsAreNested(a, b) {
  if (!a || !b || a.kind !== b.kind) return false
  return a.nodeIds.has(b.container.node.id) || b.nodeIds.has(a.container.node.id)
}

function nodeShiftsForContainerShifts(shifts, activityNodes = []) {
  const nodeShifts = new Map()
  for (const { group, dx, dy } of shifts.values()) {
    if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) continue
    for (const nodeId of group.nodeIds) {
      addNodeShift(nodeShifts, group.kind, nodeId, { dx, dy })
    }
    if (group.kind === 'state') {
      const ownerId = String(group.container.node.id || '')
      for (const node of activityNodes || []) {
        if (!isTransitionRelayNode(node) || String(node.parent_graph_id || '') !== ownerId) continue
        addNodeShift(nodeShifts, 'activity', node.id, { dx, dy })
      }
    }
  }
  return nodeShifts
}

function mergeNodeShifts(...shiftMaps) {
  const merged = new Map()
  for (const shifts of shiftMaps) {
    for (const [key, shift] of shifts.entries()) {
      const current = merged.get(key) || { dx: 0, dy: 0, persistDx: 0, persistDy: 0 }
      merged.set(key, {
        dx: current.dx + shift.dx,
        dy: current.dy + shift.dy,
        persistDx: current.persistDx + Number(shift.persistDx || 0),
        persistDy: current.persistDy + Number(shift.persistDy || 0),
      })
    }
  }
  return merged
}

function addNodeShift(shifts, kind, nodeId, shift) {
  const key = displayNodeKey(kind, nodeId)
  const current = shifts.get(key) || { dx: 0, dy: 0, persistDx: 0, persistDy: 0 }
  shifts.set(key, {
    dx: current.dx + shift.dx,
    dy: current.dy + shift.dy,
    persistDx: current.persistDx + Number(shift.persistDx ?? shift.dx ?? 0),
    persistDy: current.persistDy + Number(shift.persistDy ?? shift.dy ?? 0),
  })
}

function nodeWithDisplayShift(node, kind, nodeShifts) {
  const shift = nodeShifts.get(displayNodeKey(kind, node.id))
  if (!shift || (Math.abs(shift.dx) < 0.5 && Math.abs(shift.dy) < 0.5)) return node
  const position = nodePosition(node, kind)
  return {
    ...node,
    _network_editor_display_shift: {
      dx: Math.round(shift.dx),
      dy: Math.round(shift.dy),
      persistDx: Math.round(Number(shift.persistDx || 0)),
      persistDy: Math.round(Number(shift.persistDy || 0)),
    },
    metadata_json: {
      ...(node.metadata_json || {}),
      _network_editor_layout: {
        x: Math.round(position.x + shift.dx),
        y: Math.round(position.y + shift.dy),
      },
    },
  }
}

function nodeWithDisplayPosition(node, position) {
  const current = nodePosition(node, isTransitionRelayNode(node) ? 'activity' : graphIdKind(node?.id))
  if (
    Math.abs(Number(position.x || 0) - Number(current.x || 0)) < 0.5 &&
    Math.abs(Number(position.y || 0) - Number(current.y || 0)) < 0.5
  ) {
    return node
  }
  return {
    ...node,
    metadata_json: {
      ...(node.metadata_json || {}),
      _network_editor_layout: {
        x: Math.round(position.x),
        y: Math.round(position.y),
      },
    },
  }
}

function displayNodeKey(kind, nodeId) {
  return `${kind}:${nodeId}`
}

function containerTitleHeight(node, kind) {
  const hasWarnings = !!stateTransitionWarningText(node)
  return hasWarnings ? 52 : 42
}

function memberBounds(nodes, kind, shifts = null) {
  const members = nodes.map((node) => {
    const position = shifts ? shiftedNodePosition(node, kind, shifts) : nodePosition(node, kind)
    const size = nodeDimensions(node, kind)
    return { position, size }
  })
  const minX = Math.min(...members.map((member) => member.position.x))
  const minY = Math.min(...members.map((member) => member.position.y))
  const maxX = Math.max(...members.map((member) => member.position.x + member.size.width))
  const maxY = Math.max(...members.map((member) => member.position.y + member.size.height))
  return {
    x: minX,
    y: minY,
    width: maxX - minX,
    height: maxY - minY,
  }
}

function createContainerCell(container, kind) {
  const node = container.node
  const isState = kind === 'state'
  const level = Math.max(1, Number(node.level || 1))
  const rootPosition = nodePosition(node, kind)
  return {
    id: node.id,
    shape: isState ? 'network-state-container' : 'network-activity-container',
    x: container.x,
    y: container.y,
    width: container.width,
    height: container.height,
    zIndex: level,
    data: {
      kind,
      role: 'container',
      skipLayout: true,
      node,
      canMutate: props.canMutate,
      selected: isSelected(node, kind),
      testId: isState
        ? `network-editor-state-package-container-${node.state_node_id}`
        : `network-editor-activity-package-container-${node.id}`,
      containerOrigin: {
        x: container.x,
        y: container.y,
      },
      rootOffset: {
        x: rootPosition.x - container.x,
        y: rootPosition.y - container.y,
      },
      childIds: container.children.map((child) => child.id),
    },
    ports: nodePorts(),
  }
}

function createContainerTitleCell(container, kind) {
  const node = container.node
  const isState = kind === 'state'
  const level = Math.max(1, Number(node.level || 1))
  const rootPosition = nodePosition(node, kind)
  const titleX = container.x + 10
  const titleY = container.y + 8
  const childIds = [
    node.id,
    ...container.children.flatMap((child) => [child.id, `${child.id}:container-title`]),
  ]
  return {
    id: `${node.id}:container-title`,
    shape: 'network-container-title',
    x: titleX,
    y: titleY,
    width: Math.max(120, container.width - 20),
    height: container.titleHeight,
    zIndex: Math.max(40, 80 - level),
    data: {
      kind,
      role: 'container',
      node,
      canMutate: props.canMutate,
      selected: isSelected(node, kind),
      titleTestId: isState
        ? `network-editor-state-node-${node.state_node_id}`
        : `network-editor-activity-node-${node.id}`,
      moveTestId: isState
        ? `network-editor-state-package-container-move-${node.state_node_id}`
        : `network-editor-activity-package-container-move-${node.id}`,
      label: node.name || node.code || node.id,
      code: node.code || node.id,
      meta: isState
        ? `${container.children.length} states`
        : `${container.children.length} activities`,
      collapsedRelationCounts: node.collapsedRelationCounts || null,
      flowState: node.flowState || 'neutral',
      actionLabel: '折叠',
      rootOffset: {
        x: rootPosition.x - titleX,
        y: rootPosition.y - titleY,
      },
      childIds,
    },
  }
}

function createNodeCell(node, kind) {
  const position = nodePosition(node, kind)
  const size = nodeDimensions(node, kind)
  const isRelay = isTransitionRelayNode(node)
  return {
    id: node.id,
    shape: kind === 'state' ? 'network-state-node' : 'network-activity-node',
    x: position.x,
    y: position.y,
    width: size.width,
    height: size.height,
    zIndex: 10,
    data: {
      kind,
      role: 'node',
      node,
      canMutate: props.canMutate,
      selected: isSelected(node, kind),
      testId: kind === 'state'
        ? `network-editor-state-node-${node.state_node_id}`
        : (isRelay ? 'network-editor-transition-relay-node' : `network-editor-activity-node-${node.id}`),
      label: node.name || node.code || node.id,
      code: node.code || node.id,
      meta: nodeMeta(node, kind),
      stateTransition: kind === 'state' ? (node.stateTransition || null) : null,
      size,
      collapsedRelationCounts: node.collapsedRelationCounts || null,
      flowState: node.flowState || 'neutral',
      canToggle: !isRelay && (kind === 'state' ? !node.is_leaf : node.activity_type === 'activity_package'),
      actionLabel: isExpandedNode(node, kind) ? '折叠' : '展开',
      isPackage: kind === 'activity' && node.activity_type === 'activity_package',
      isTransitionRelay: isRelay,
      relayActivityGraphId: transitionRelayActivityGraphId(node),
    },
    ports: nodePorts(),
  }
}

function buildEdgeRouteContext(displayLayout, edges = []) {
  const rects = new Map()
  const kinds = new Map()
  const obstacles = new Map()
  const containerRootIds = new Set([
    ...(displayLayout.stateContainers || []).map((container) => String(container.node.id)),
    ...(displayLayout.activityContainers || []).map((container) => String(container.node.id)),
  ])
  for (const node of displayLayout.stateNodes || []) {
    const rect = currentNodeRect(node, 'state', new Map())
    rects.set(node.id, rect)
    kinds.set(node.id, 'state')
    if (!containerRootIds.has(String(node.id))) obstacles.set(String(node.id), rect)
  }
  for (const node of displayLayout.activityNodes || []) {
    const rect = currentNodeRect(node, 'activity', new Map())
    rects.set(node.id, rect)
    kinds.set(node.id, 'activity')
    if (!containerRootIds.has(String(node.id))) obstacles.set(String(node.id), rect)
  }
  for (const container of displayLayout.stateContainers || []) {
    rects.set(container.node.id, containerRect(container))
    kinds.set(container.node.id, 'state')
    obstacles.set(`${container.node.id}:container-title`, containerTitleRect(container))
  }
  for (const container of displayLayout.activityContainers || []) {
    rects.set(container.node.id, containerRect(container))
    kinds.set(container.node.id, 'activity')
    obstacles.set(`${container.node.id}:container-title`, containerTitleRect(container))
  }
  return {
    rects,
    kinds,
    obstacles,
    ...buildEdgeBusRoutes(edges, rects, kinds),
  }
}

function buildEdgeBusRoutes(edges, rects, kinds) {
  const incoming = new Map()
  const outgoing = new Map()
  for (const edge of edges || []) {
    if (!edgeBusRouteCandidate(edge, rects, kinds)) continue
    if (!outgoing.has(edge.source_id)) outgoing.set(edge.source_id, [])
    if (!incoming.has(edge.target_id)) incoming.set(edge.target_id, [])
    outgoing.get(edge.source_id).push(edge)
    incoming.get(edge.target_id).push(edge)
  }

  const forkRails = new Map()
  for (const [sourceId, sourceEdges] of outgoing.entries()) {
    if (sourceEdges.length < 2) continue
    const source = rects.get(sourceId)
    if (!source) continue
    const targetLeft = Math.min(...sourceEdges.map((edge) => rects.get(edge.target_id)?.left ?? Infinity))
    const railOffset = edgeBusRailOffset(targetLeft - source.right)
    forkRails.set(sourceId, {
      railX: Math.round(source.right + railOffset),
      edgeIds: new Set(sourceEdges.map(edgeRouteKey)),
    })
  }

  const joinRails = new Map()
  for (const [targetId, targetEdges] of incoming.entries()) {
    if (targetEdges.length < 2) continue
    const target = rects.get(targetId)
    if (!target) continue
    const sourceRight = Math.max(...targetEdges.map((edge) => rects.get(edge.source_id)?.right ?? 0))
    const railOffset = edgeBusRailOffset(target.left - sourceRight)
    joinRails.set(targetId, {
      railX: Math.round(Math.max(18, target.left - railOffset)),
      edgeIds: new Set(targetEdges.map(edgeRouteKey)),
    })
  }

  return { forkRails, joinRails }
}

function edgeBusRailOffset(gap) {
  if (!Number.isFinite(gap) || gap <= 0) return EDGE_RAIL_GAP
  return Math.min(EDGE_RAIL_GAP, Math.max(EDGE_BUS_STUB_GAP, Math.round(gap * 0.35)))
}

function edgeBusRouteCandidate(edge, rects, kinds) {
  if (!edge?.source_id || !edge?.target_id) return false
  if (edge.isCollapsedProxy || edge.aggregate) return false
  const isRelayEdge = !!edge.isTransitionRelayEdge || edge.source_kind === 'state_transition_relay'
  if (edge.type !== 'STATE_FLOW' && !isRelayEdge) return false
  const source = rects.get(edge.source_id)
  const target = rects.get(edge.target_id)
  if (!source || !target || source.left >= target.left) return false
  if (isRelayEdge) return true
  const sourceKind = kinds.get(edge.source_id) || graphIdKind(edge.source_id)
  const targetKind = kinds.get(edge.target_id) || graphIdKind(edge.target_id)
  return sourceKind && sourceKind === targetKind
}

function edgeRouteKey(edge) {
  return String(edge?.id || `${edge?.source_id || ''}->${edge?.target_id || ''}:${edge?.type || ''}`)
}

function createEdgeCell(edge, routeContext = null) {
  if (!edge?.source_id || !edge?.target_id) return null
  const isInput = edge.type === 'STATE_TO_ACTIVITY'
  const label = edge.displayLabel || edge.aggregateLabel || ''
  const isProxy = !!edge.isCollapsedProxy
  const route = edgeRoute(edge, routeContext)
  const flow = edge.flow || {}
  const flowState = flow.state || 'backbone'
  const flowRole = flow.role || (isInput ? 'precondition' : 'realizer')
  const labelPosition = isProxy
    ? proxyLabelPosition(edge, route, routeContext, label)
    : {
        distance: 0.5,
        offset: 0,
        options: { keepGradient: false, ensureLegibility: true },
      }
  const active = flowState === 'active'
  const muted = flowState === 'muted'
  const stroke = active
    ? '#f59e0b'
    : isProxy ? '#4f6fae' : isInput ? '#2563eb' : '#0f9f6e'
  const strokeWidth = active ? 4 : (isProxy || edge.aggregate ? 3 : 2)
  const strokeOpacity = muted ? 0.14 : (active ? 0.95 : 0.34)
  const dash = active
    ? '12 8'
    : isProxy ? '8 5' : (edge.aggregate ? '6 5' : ((edge.is_draft || edge.is_pending) ? '4 4' : ''))
  const cell = {
    id: String(edge.id),
    shape: 'edge',
    source: { cell: edge.source_id, port: route.sourcePort },
    target: { cell: edge.target_id, port: route.targetPort },
    vertices: route.vertices.length ? route.vertices : undefined,
    zIndex: 0,
    labels: label ? [{
      position: labelPosition,
      attrs: {
        body: isProxy ? {
          fill: '#f8fafc',
          fillOpacity: 0.96,
          stroke: '#d6dfec',
          strokeWidth: 1,
          rx: 4,
          ry: 4,
          refWidth: '118%',
          refHeight: '150%',
          refX: '-9%',
          refY: '-25%',
        } : undefined,
        label: {
          text: label,
          fill: isProxy ? '#0f172a' : undefined,
          fontSize: isProxy ? 12 : undefined,
          fontWeight: isProxy ? 700 : undefined,
          opacity: muted ? 0.28 : 1,
        },
      },
    }] : undefined,
    attrs: {
      line: {
        stroke,
        strokeWidth,
        strokeOpacity,
        strokeDasharray: dash,
        class: [
          'network-flow-edge-line',
          `flow-${flowState}`,
          `flow-${flowRole}`,
          `route-${route.kind}`,
          isProxy ? 'flow-proxy' : '',
          edge.aggregate ? 'flow-aggregate' : '',
        ].filter(Boolean).join(' '),
        'data-testid': 'network-editor-flow-edge-line',
        'data-flow-state': flowState,
        'data-flow-role': flowRole,
        'data-flow-route': route.kind,
        'data-source-port': route.sourcePort,
        'data-target-port': route.targetPort,
        'data-source-id': edge.source_id,
        'data-target-id': edge.target_id,
        'data-source-side': 'right',
        'data-target-side': 'left',
        'data-route-rail-x': route.railX === null ? undefined : String(Math.round(route.railX)),
        'data-transition-count': edge.transitionCount === undefined ? undefined : String(edge.transitionCount),
        'data-dependency-count': edge.dependencyCount === undefined ? undefined : String(edge.dependencyCount),
        'data-package-binding-count': edge.packageBindingCount === undefined ? undefined : String(edge.packageBindingCount),
        'data-coverage-status': edge.coverage_status || undefined,
        sourceMarker: {
          name: 'circle',
          r: active ? 4 : 3,
          fill: active ? '#fef3c7' : '#ffffff',
          stroke,
          strokeWidth: active ? 2 : 1.5,
        },
        targetMarker: {
          name: 'block',
          width: active ? 12 : 9,
          height: active ? 9 : 7,
          fill: stroke,
          stroke,
        },
      },
    },
    connector: {
      name: 'rounded',
      args: { radius: route.kind === 'direct' ? 8 : 12 },
    },
    data: { edge },
  }
  if (route.useRouter !== false) {
    cell.router = {
      name: 'manhattan',
      args: route.routerArgs || { padding: route.kind === 'direct' ? 18 : 10 },
    }
  }
  return cell
}

function proxyLabelPosition(edge, route, routeContext, label) {
  const fallback = {
    distance: 0.5,
    offset: -STATE_TRANSITION_PROXY_LABEL_OFFSET,
    options: { keepGradient: false, ensureLegibility: true },
  }
  if (route.useRouter) return fallback
  const source = routeContext?.rects?.get(edge.source_id)
  const target = routeContext?.rects?.get(edge.target_id)
  if (!source || !target) return fallback
  const points = simplifyRouteVertices([
    edgeAnchor(source, 'right'),
    ...(route.vertices || []),
    edgeAnchor(target, 'left'),
  ])
  const segments = routeLabelSegments(points)
  if (!segments.length) return fallback
  const labelWidth = Math.max(56, Math.min(260, textUnits(label) * 6 + 24))
  const labelHeight = 28
  const obstacles = Array.from(routeContext?.obstacles?.values?.() || [])
  const offsets = [
    -STATE_TRANSITION_PROXY_LABEL_OFFSET,
    STATE_TRANSITION_PROXY_LABEL_OFFSET,
    -STATE_TRANSITION_PROXY_LABEL_OFFSET * 2,
    STATE_TRANSITION_PROXY_LABEL_OFFSET * 2,
    -STATE_TRANSITION_PROXY_LABEL_OFFSET * 3,
    STATE_TRANSITION_PROXY_LABEL_OFFSET * 3,
    -STATE_TRANSITION_PROXY_LABEL_OFFSET * 4,
    STATE_TRANSITION_PROXY_LABEL_OFFSET * 4,
  ]

  for (const segment of segments) {
    for (const offset of offsets) {
      const center = offsetRoutePoint(segment.midpoint, segment, offset)
      const labelRect = {
        left: center.x - labelWidth / 2,
        right: center.x + labelWidth / 2,
        top: center.y - labelHeight / 2,
        bottom: center.y + labelHeight / 2,
      }
      if (obstacles.some((obstacle) => rectsOverlap(labelRect, obstacle, 4))) continue
      return {
        distance: segment.distance,
        offset,
        options: { keepGradient: false, ensureLegibility: true },
      }
    }
  }
  return fallback
}

function routeLabelSegments(points) {
  const raw = []
  let total = 0
  for (let index = 1; index < points.length; index += 1) {
    const start = points[index - 1]
    const end = points[index]
    const length = Math.abs(end.x - start.x) + Math.abs(end.y - start.y)
    if (!length) continue
    raw.push({ start, end, length, startDistance: total })
    total += length
  }
  if (!total) return []
  return raw
    .map((segment) => ({
      ...segment,
      midpoint: {
        x: Math.round((segment.start.x + segment.end.x) / 2),
        y: Math.round((segment.start.y + segment.end.y) / 2),
      },
      distance: (segment.startDistance + segment.length / 2) / total,
      horizontal: segment.start.y === segment.end.y,
    }))
    .sort((left, right) =>
      Number(right.horizontal) - Number(left.horizontal) ||
      right.length - left.length ||
      Math.abs(left.distance - 0.5) - Math.abs(right.distance - 0.5),
    )
}

function offsetRoutePoint(point, segment, offset) {
  if (segment.horizontal) {
    const direction = Math.sign(segment.end.x - segment.start.x) || 1
    return { x: point.x, y: point.y + offset * direction }
  }
  const direction = Math.sign(segment.end.y - segment.start.y) || 1
  return { x: point.x - offset * direction, y: point.y }
}

function edgeRoute(edge, context) {
  const direct = {
    kind: 'direct',
    sourcePort: OUTPUT_PORT_ID,
    targetPort: INPUT_PORT_ID,
    vertices: [],
    railX: null,
    useRouter: true,
  }
  const source = context?.rects?.get(edge.source_id)
  const target = context?.rects?.get(edge.target_id)
  if (!source || !target) return direct
  const autoRoute = normalizedAutoRoute(edge.autoRoute, source, target, edge)
  if (autoRoute && !routeIntersectsVisibleObstacle(autoRoute, edge, source, target, context)) return autoRoute
  if (autoRoute || edge.isCollapsedProxy) return buildObstacleRoute(autoRoute?.kind || 'obstacle')
  if (edge.autoRouteHint || edge.aggregate) {
    return buildDisplayedShortRoute(edge, source, target, edge.autoRouteHint || { kind: 'short' })
  }

  const sourceKind = context?.kinds?.get(edge.source_id) || graphIdKind(edge.source_id)
  const targetKind = context?.kinds?.get(edge.target_id) || graphIdKind(edge.target_id)
  const sameKind = sourceKind && sourceKind === targetKind
  const isRelayEdge = !!edge.isTransitionRelayEdge || edge.source_kind === 'state_transition_relay'
  const sourceY = Math.round(source.top + source.height / 2)
  const targetY = Math.round(target.top + target.height / 2)
  const needsRail = sameKind ||
    edge.type === 'STATE_FLOW' ||
    isRelayEdge ||
    edge.isCollapsedProxy ||
    edge.aggregate ||
    Math.abs(sourceY - targetY) >= EDGE_LONG_ROUTE_DELTA
  if (!needsRail) return direct
  if (sameKind || edge.type === 'STATE_FLOW' || isRelayEdge || edge.isCollapsedProxy || edge.aggregate || Math.abs(sourceY - targetY) >= EDGE_LONG_ROUTE_DELTA) {
    return buildDisplayedShortRoute(edge, source, target, { kind: 'short' })
  }

  if (sameKind || edge.type === 'STATE_FLOW' || isRelayEdge || edge.isCollapsedProxy || edge.aggregate) {
    const routeKey = edgeRouteKey(edge)
    const sourceBeforeTarget = source.left < target.left
    const joinRail = context?.joinRails?.get(edge.target_id)
    if (
      sourceBeforeTarget &&
      joinRail?.edgeIds?.has(routeKey) &&
      joinRail.railX > source.right + EDGE_BUS_STUB_GAP &&
      !edge.isCollapsedProxy &&
      !edge.aggregate
    ) {
      return {
        kind: 'join',
        sourcePort: OUTPUT_PORT_ID,
        targetPort: INPUT_PORT_ID,
        vertices: [
          { x: Math.round(source.right + EDGE_BUS_STUB_GAP), y: sourceY },
          { x: joinRail.railX, y: sourceY },
          { x: joinRail.railX, y: targetY },
        ],
        railX: joinRail.railX,
        useRouter: true,
      }
    }

    const forkRail = context?.forkRails?.get(edge.source_id)
    if (
      sourceBeforeTarget &&
      forkRail?.edgeIds?.has(routeKey) &&
      forkRail.railX < target.left - EDGE_BUS_STUB_GAP &&
      !edge.isCollapsedProxy &&
      !edge.aggregate
    ) {
      return {
        kind: 'fork',
        sourcePort: OUTPUT_PORT_ID,
        targetPort: INPUT_PORT_ID,
        vertices: [
          { x: forkRail.railX, y: sourceY },
          { x: forkRail.railX, y: targetY },
          { x: Math.round(target.left - EDGE_BUS_STUB_GAP), y: targetY },
        ],
        railX: forkRail.railX,
        useRouter: true,
      }
    }

    const rowTolerance = Math.max(WRAPPED_FLOW_ROW_TOLERANCE, Math.min(64, Math.max(source.height, target.height)))
    const sameRow = Math.abs(sourceY - targetY) <= rowTolerance
    if (sameRow && sourceBeforeTarget && !edge.isCollapsedProxy && !edge.aggregate) {
      return direct
    }
    const sourceRailX = Math.round(source.right + EDGE_RAIL_GAP)
    const targetRailX = Math.round(Math.max(18, target.left - EDGE_RAIL_GAP))
    const midY = Math.round((sourceY + targetY) / 2)
    return {
      kind: 'corridor',
      sourcePort: OUTPUT_PORT_ID,
      targetPort: INPUT_PORT_ID,
      vertices: [
        { x: sourceRailX, y: sourceY },
        { x: sourceRailX, y: midY },
        { x: targetRailX, y: midY },
        { x: targetRailX, y: targetY },
      ],
      railX: sourceRailX,
      useRouter: true,
    }
  }

  const railX = crossKindRailX(source, target)
  return {
    kind: 'channel',
    sourcePort: OUTPUT_PORT_ID,
    targetPort: INPUT_PORT_ID,
    vertices: [
      { x: railX, y: sourceY },
      { x: railX, y: targetY },
    ],
    railX,
    useRouter: true,
  }
}

function buildObstacleRoute(kind = 'obstacle') {
  return {
    kind: kind.startsWith('elk') ? 'elk-obstacle' : 'obstacle',
    sourcePort: OUTPUT_PORT_ID,
    targetPort: INPUT_PORT_ID,
    vertices: [],
    railX: null,
    useRouter: true,
    routerArgs: {
      padding: STATE_TRANSITION_PROXY_OBSTACLE_PADDING,
      step: 8,
      maxLoopCount: 5000,
      startDirections: ['right'],
      endDirections: ['left'],
      excludeShapes: ['network-state-container', 'network-activity-container'],
    },
  }
}

function routeIntersectsVisibleObstacle(route, edge, source, target, context) {
  if (!route || !context?.obstacles?.size) return false
  const points = [edgeAnchor(source, 'right'), ...(route.vertices || []), edgeAnchor(target, 'left')]
  if (points.length < 2) return false
  const endpointIds = new Set([String(edge.source_id || ''), String(edge.target_id || '')])
  for (const [id, rect] of context.obstacles.entries()) {
    if (endpointIds.has(String(id))) continue
    const obstacle = inflateRect(rect, 6)
    for (let index = 1; index < points.length; index += 1) {
      if (orthogonalSegmentIntersectsRect(points[index - 1], points[index], obstacle)) return true
    }
  }
  return false
}

function orthogonalSegmentIntersectsRect(start, end, rect) {
  if (!start || !end || !rect) return false
  const minX = Math.min(start.x, end.x)
  const maxX = Math.max(start.x, end.x)
  const minY = Math.min(start.y, end.y)
  const maxY = Math.max(start.y, end.y)
  if (start.y === end.y) {
    return start.y > rect.top && start.y < rect.bottom && maxX > rect.left && minX < rect.right
  }
  if (start.x === end.x) {
    return start.x > rect.left && start.x < rect.right && maxY > rect.top && minY < rect.bottom
  }
  return maxX > rect.left && minX < rect.right && maxY > rect.top && minY < rect.bottom
}

function normalizedAutoRoute(route, source, target, edge) {
  if (!route) return null
  const routePoints = Array.isArray(route.points)
    ? normalizeRoutePoints(route.points)
    : []
  const vertices = normalizeRoutePoints(route.vertices || [])
  const sourceAnchor = edgeAnchor(source, 'right')
  const targetAnchor = edgeAnchor(target, 'left')
  const points = routePoints.length >= 2
    ? routePoints
    : [sourceAnchor, ...vertices, targetAnchor]
  if (
    points.length < 2 ||
    vertices.length > EDGE_MAX_AUTO_VERTICES ||
    routeLooksStale(points, sourceAnchor, targetAnchor) ||
    routeBacktracks(points, sourceAnchor, targetAnchor)
  ) {
    return buildDisplayedShortRoute(edge, source, target, { kind: route.kind || 'elk' })
  }
  const calibrated = simplifyRouteVertices([
    sourceAnchor,
    ...vertices,
    targetAnchor,
  ])
  const calibratedVertices = applyRouteLaneOffset(calibrated.slice(1, -1), edge, sourceAnchor, targetAnchor)
  return {
    kind: route.kind?.startsWith?.('elk') ? 'elk-short' : (route.kind || 'short'),
    sourcePort: OUTPUT_PORT_ID,
    targetPort: INPUT_PORT_ID,
    vertices: calibratedVertices,
    railX: null,
    useRouter: false,
  }
}

function buildDisplayedShortRoute(edge, source, target, routeHint = {}) {
  const sourceAnchor = edgeAnchor(source, 'right')
  const targetAnchor = edgeAnchor(target, 'left')
  const sameRow = Math.abs(sourceAnchor.y - targetAnchor.y) <= WRAPPED_FLOW_ROW_TOLERANCE
  const sourceBeforeTarget = source.right <= target.left
  let points
  if (sourceBeforeTarget && sameRow) {
    points = [sourceAnchor, targetAnchor]
  } else if (sourceBeforeTarget) {
    const midX = Math.round(source.right + Math.max(EDGE_SHORT_ROUTE_GAP, (target.left - source.right) / 2))
    points = [
      sourceAnchor,
      { x: midX, y: sourceAnchor.y },
      { x: midX, y: targetAnchor.y },
      targetAnchor,
    ]
  } else {
    const outsideX = Math.round(Math.max(source.right, target.right) + EDGE_SHORT_ROUTE_GAP)
    points = [
      sourceAnchor,
      { x: outsideX, y: sourceAnchor.y },
      { x: outsideX, y: targetAnchor.y },
      targetAnchor,
    ]
  }
  const simplified = simplifyRouteVertices(points)
  return {
    kind: routeHint.kind?.startsWith?.('elk') ? 'elk-short' : 'short',
    sourcePort: OUTPUT_PORT_ID,
    targetPort: INPUT_PORT_ID,
    vertices: applyRouteLaneOffset(simplified.slice(1, -1), edge, sourceAnchor, targetAnchor),
    railX: null,
    useRouter: false,
  }
}

function edgeAnchor(rect, side) {
  return {
    x: Math.round(side === 'right' ? rect.right : rect.left),
    y: Math.round(rect.top + rect.height / 2),
  }
}

function normalizeRoutePoints(points) {
  return (points || [])
    .map((point) => ({
      x: finiteNumber(point?.x),
      y: finiteNumber(point?.y),
    }))
    .filter((point) => point.x !== null && point.y !== null)
    .map((point) => ({ x: Math.round(point.x), y: Math.round(point.y) }))
}

function routeLooksStale(points, sourceAnchor, targetAnchor) {
  const first = points[0]
  const last = points[points.length - 1]
  if (!first || !last) return true
  return pointDistance(first, sourceAnchor) > EDGE_ROUTE_STALE_TOLERANCE ||
    pointDistance(last, targetAnchor) > EDGE_ROUTE_STALE_TOLERANCE
}

function routeBacktracks(points, sourceAnchor, targetAnchor) {
  if (targetAnchor.x >= sourceAnchor.x) {
    return points.some((point) => point.x < sourceAnchor.x - EDGE_BUS_STUB_GAP || point.x > targetAnchor.x + EDGE_RAIL_GAP * 3)
  }
  return points.some((point) => point.x < Math.min(sourceAnchor.x, targetAnchor.x) - EDGE_RAIL_GAP * 3)
}

function pointDistance(a, b) {
  return Math.abs((a?.x || 0) - (b?.x || 0)) + Math.abs((a?.y || 0) - (b?.y || 0))
}

function simplifyRouteVertices(points) {
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
      if (!((a.x === b.x && b.x === c.x) || (a.y === b.y && b.y === c.y))) break
      simplified.splice(simplified.length - 2, 1)
    }
  }
  return simplified
}

function applyRouteLaneOffset(vertices, edge, sourceAnchor, targetAnchor) {
  const offset = finiteNumber(edge?.renderLaneOffset) ?? finiteNumber(edge?.autoRouteHint?.laneOffset) ?? 0
  if (!offset || !vertices.length) return vertices
  const horizontal = Math.abs(sourceAnchor.x - targetAnchor.x) >= Math.abs(sourceAnchor.y - targetAnchor.y)
  return vertices.map((point) => horizontal
    ? { ...point, y: point.y + offset }
    : { ...point, x: point.x + offset })
}

function crossKindRailX(source, target) {
  if (source.right < target.left) {
    return Math.round(source.right + (target.left - source.right) * 0.42)
  }
  if (target.right < source.left) {
    return Math.round(target.right + (source.left - target.right) * 0.58)
  }
  return Math.round(Math.max(source.right, target.right) + EDGE_RAIL_GAP)
}

function graphIdKind(graphId) {
  const id = String(graphId || '')
  if (id.startsWith('state_node:')) return 'state'
  if (id.startsWith('activity_node:') || id.startsWith('atomic_activity:') || id.startsWith('transition_relay:')) return 'activity'
  return ''
}

function renderNodeHtml(data) {
  const nodeClass = data.kind === 'state' ? 'x6-state-node' : 'x6-activity-node'
  const selectedClass = data.selected ? ' selected' : ''
  const flowClass = data.flowState && data.flowState !== 'neutral' ? ` flow-${escapeAttr(data.flowState)}` : ''
  if (data.isTransitionRelay) {
    const tooltip = nodeTooltip(data)
    const moveHandle = data.canMutate
      ? '<span class="layout-handle" title="Drag to move"></span>'
      : ''
    return `
      <div class="x6-network-node x6-activity-node x6-transition-relay-node${selectedClass}${flowClass}" data-testid="${escapeAttr(data.testId)}" data-activity-graph-id="${escapeAttr(data.relayActivityGraphId || '')}" title="${escapeAttr(tooltip)}" tabindex="0">
        ${moveHandle}
        <span class="relay-dot"></span>
        <span class="relay-label">
          <strong>${escapeHtml(data.code || '')}</strong>
          <span>${escapeHtml(data.label || '')}</span>
        </span>
        <span class="relay-tooltip" role="tooltip">${escapeHtml(tooltip)}</span>
      </div>
    `
  }
  const moveHandle = data.canMutate
    ? '<span class="layout-handle" title="Drag to move"></span>'
    : ''
  const toggle = data.canToggle
    ? `<span class="node-action" role="button" tabindex="0" data-action="toggle">${escapeHtml(data.actionLabel)}</span>`
    : ''
  const edit = data.canMutate && props.showEditActions
    ? '<span class="node-action" role="button" tabindex="0" data-action="edit">编辑</span>'
    : ''
  const canCreateInside = data.canMutate && props.showEditActions && (
    data.kind === 'state'
      ? data.canToggle
      : data.isPackage && Number(data.node?.level || 0) === 2
  )
  const create = canCreateInside
    ? `<span class="node-action" role="button" tabindex="0" data-action="create">${data.kind === 'state' ? '添加状态' : '原子'}</span>`
    : ''

  const relationBadges = relationBadgesHtml(data)
  const transitionSummary = stateTransitionSummary(data.node)
  const fullTransitionSummary = stateTransitionFullSummary(data.node)
  const transitionBadges = stateTransitionBadgesHtml(data.node)
  const tooltip = nodeTooltip(data, fullTransitionSummary)

  return `
    <div class="x6-network-node ${nodeClass}${selectedClass}${flowClass}${data.canToggle && isExpandedNode(data.node, data.kind) ? ' is-expanded' : ''}" data-testid="${escapeAttr(data.testId)}" title="${escapeAttr(tooltip)}">
      ${moveHandle}
      ${relationBadges}
      <span class="node-name" title="${escapeAttr(data.label)}">${escapeHtml(data.label)}</span>
      ${transitionSummary ? `<span class="node-transition" title="${escapeAttr(transitionSummary)}">${escapeHtml(transitionSummary)}</span>` : ''}
      ${transitionBadges}
      <span class="node-actions">${toggle}${edit}${create}</span>
    </div>
  `
}

function renderContainerBodyHtml(data) {
  const selectedClass = data.selected ? ' selected' : ''
  const kindClass = data.kind === 'state' ? 'x6-state-container' : 'x6-activity-container'
  const resizeHandle = data.canMutate
    ? '<span class="container-resize-handle" data-action="resize" title="Resize container"></span>'
    : ''

  return `
    <div class="x6-network-container ${kindClass}${selectedClass}" data-testid="${escapeAttr(data.testId)}">
      ${resizeHandle}
    </div>
  `
}

function renderContainerTitleHtml(data) {
  const selectedClass = data.selected ? ' selected' : ''
  const kindClass = data.kind === 'state' ? 'x6-state-container-title' : 'x6-activity-container-title'
  const flowClass = data.flowState && data.flowState !== 'neutral' ? ` flow-${escapeAttr(data.flowState)}` : ''
  const relationBadges = relationBadgesHtml(data)
  const titleCopyAttrs = data.canMutate
    ? `class="container-title-copy container-move-handle" data-testid="${escapeAttr(data.moveTestId)}" title="Drag container"`
    : 'class="container-title-copy"'
  const canCreateInside = data.canMutate && props.showEditActions && (
    data.kind === 'state' ||
    (data.kind === 'activity' && Number(data.node?.level || 0) === 2)
  )
  const create = canCreateInside
    ? `<span class="node-action" role="button" tabindex="0" data-action="create">${data.kind === 'state' ? '添加状态' : '原子'}</span>`
    : ''
  const tooltip = nodeTooltip(data)

  return `
    <div class="container-title-row ${kindClass}${selectedClass}${flowClass} is-expanded" data-testid="${escapeAttr(data.titleTestId)}" title="${escapeAttr(tooltip)}">
      ${relationBadges}
      <div ${titleCopyAttrs}>
        <span class="node-name" title="${escapeAttr(data.label)}">${escapeHtml(data.label)}</span>
      </div>
      <span class="node-actions">
        <span class="node-action" role="button" tabindex="0" data-action="toggle">${escapeHtml(data.actionLabel)}</span>
        ${create}
      </span>
    </div>
  `
}

function relationBadgesHtml(data) {
  const counts = data.collapsedRelationCounts || {}
  const badges = []
  if (counts.input) {
    badges.push(`<span class="collapsed-relation-badge badge-input" title="折叠输入转移">+${escapeHtml(counts.input)}</span>`)
  }
  if (counts.output) {
    badges.push(`<span class="collapsed-relation-badge badge-output" title="折叠输出转移">+${escapeHtml(counts.output)}</span>`)
  }
  if (counts.internal) {
    badges.push(`<span class="collapsed-relation-badge badge-internal" title="包内转移">${escapeHtml(counts.internal)} 内部转移</span>`)
  }
  return badges.join('')
}

function stateTransitionSummary(node) {
  const transition = node?.stateTransition
  if (!transition) return ''
  const realizer = shortRealizerLabel(transition.realizerLabel)
  if (transition.isInitialSource || realizer === '起始条件') return '起始条件'
  const preconditionCount = Number(transition.preconditionCount || 0)
  return `${realizer} · 前置 ${preconditionCount}`
}

function stateTransitionFullSummary(node) {
  const transition = node?.stateTransition
  if (!transition) return ''
  const realizer = transition.realizerLabel || '待补达成活动'
  if (transition.isInitialSource || realizer === '起始条件') return '起始条件'
  const preconditionCount = Number(transition.preconditionCount || 0)
  return `${realizer} / 前置 ${preconditionCount}`
}

function shortRealizerLabel(label) {
  const value = String(label || '').trim()
  if (!value || value === '待补达成活动') return '待补'
  return value
}

function nodeTooltip(data, transition = '') {
  return [
    data.label,
    data.code ? `Code: ${data.code}` : '',
    data.meta ? `Meta: ${data.meta}` : '',
    transition ? `状态转移: ${transition}` : '',
    stateTransitionWarningText(data.node) ? `提示: ${stateTransitionWarningText(data.node)}` : '',
  ].filter(Boolean).join('\n')
}

function stateTransitionWarningText(node) {
  const warnings = node?.stateTransition?.warnings || []
  return warnings.map((item) => item.label || item).filter(Boolean).join(' ')
}

function stateTransitionBadgesHtml(node) {
  const warnings = node?.stateTransition?.warnings || []
  if (!warnings.length) return ''
  const title = stateTransitionWarningText(node)
  return `<span class="node-transition-warnings" title="${escapeAttr(title)}">${
    warnings.slice(0, 2).map((item) => {
      const label = typeof item === 'string' ? item : item.label
      const type = typeof item === 'string' ? 'warning' : (item.type || 'warning')
      return `<span class="state-transition-badge badge-${escapeAttr(type)}">${escapeHtml(label)}</span>`
    }).join('')
  }</span>`
}

function handleNodeClick({ node, e }) {
  if (e?.[NODE_ACTION_EVENT_HANDLED]) return
  const data = node.getData() || {}
  const actionElement = e?.target?.closest?.('[data-action]')
  const action = actionElement?.dataset?.action || e?.target?.dataset?.action
  if (dispatchNodeAction(data, action, e)) {
    markNodeActionEventHandled(e)
    return
  }
  emit(data.kind === 'state' ? 'select-state' : 'select-activity', { node: data.node, event: e })
}

function handleNodeMouseEnter({ node }) {
  const data = node?.getData?.() || {}
  if (!data.node || !data.kind) return
  emit('node-hover-change', {
    graphId: node.id,
    kind: data.kind,
    node: data.node,
  })
}

function handleNodeMouseLeave() {
  emit('node-hover-change', null)
}

function handleHtmlActionClick(event) {
  if (event?.[NODE_ACTION_EVENT_HANDLED]) return
  const actionElement = event?.target?.closest?.('[data-action]')
  if (!actionElement) {
    const nodeElement = nodeElementFromEvent(event)
    if (!nodeElement || !hostRef.value?.contains(nodeElement)) return
    const nodeCell = cellFromEventTarget(nodeElement)
    const data = nodeCell?.getData?.() || {}
    if (!data.node || !data.kind || data.role !== 'node') return
    markNodeActionEventHandled(event)
    emit(data.kind === 'state' ? 'select-state' : 'select-activity', { node: data.node, event })
    return
  }
  if (!hostRef.value?.contains(actionElement)) return
  const cell = cellFromEventTarget(actionElement)
  if (!cell) return
  const data = cell.getData() || {}
  const action = actionElement.dataset.action
  if (!action) return
  markNodeActionEventHandled(event)
  dispatchNodeAction(data, action, event)
}

function markNodeActionEventHandled(event) {
  if (!event) return
  try {
    event[NODE_ACTION_EVENT_HANDLED] = true
  } catch (_) {
    // Some browser event objects may be sealed by a test driver or extension.
  }
  event.preventDefault?.()
  event.stopPropagation?.()
  event.stopImmediatePropagation?.()
}

function dispatchNodeAction(data, action, event) {
  if (action === 'resize') return true
  const actionKey = nodeActionDedupeKey(data, action)
  const now = Date.now()
  if (actionKey && lastNodeAction?.key === actionKey && now - lastNodeAction.time < 20) return true
  if (actionKey) lastNodeAction = { key: actionKey, time: now }
  if (action === 'toggle') {
    emit(data.kind === 'state' ? 'toggle-state-expansion' : 'toggle-activity-expansion', data.node)
    return true
  }
  if (action === 'create') {
    emit(data.kind === 'state' ? 'create-state-inside' : 'create-activity-inside', data.node)
    return true
  }
  if (action === 'edit') {
    emit(data.kind === 'state' ? 'edit-state' : 'edit-activity', data.node)
    return true
  }
  return false
}

function handleNodeMouseDown({ node, e }) {
  const data = node.getData() || {}
  if (e?.target?.classList?.contains('container-move-handle')) {
    startContainerMove(data, node, e)
    return
  }
  if (e?.target?.dataset?.action === 'resize') {
    startResize(data, node, e)
  }
}

function handleHostContextMenu(event) {
  const nodeElement = nodeElementFromEvent(event) ||
    event?.target?.closest?.('.container-title-row')
  const nodeCell = nodeElement ? cellFromEventTarget(nodeElement) : null
  const data = nodeCell?.getData?.() || {}
  if (data.node && data.kind) {
    event.preventDefault()
    event.stopPropagation()
    emit(data.kind === 'state' ? 'select-state' : 'select-activity', { node: data.node, event })
    return
  }
  if (!isBlankCanvasPointerEvent(event)) return
  event.preventDefault()
  event.stopPropagation()
  emitBlankContextMenu(event)
}

function emitBlankContextMenu(event) {
  const point = clientPointToLocal(event.clientX, event.clientY)
  emit('blank-contextmenu', {
    x: point?.x,
    y: point?.y,
    event,
  })
}

function clientPointToLocal(clientX, clientY) {
  const graph = graphRef.value
  const rect = hostRef.value?.getBoundingClientRect?.()
  if (!graph || !rect) return null
  const translation = graph.translate()
  const scale = normalizeZoom(props.canvasZoom)
  return {
    x: (clientX - rect.left - Number(translation?.tx || 0)) / scale,
    y: (clientY - rect.top - Number(translation?.ty || 0)) / scale,
  }
}

function handleCanvasPointerDown(event) {
  if (isPointerControlTarget(event)) return
  if (event.button === 0 && startCanvasPan(event)) return
  const nodeElement = nodeElementFromEvent(event)
  if (nodeElement) {
    const cell = cellFromEventTarget(nodeElement)
    if (cell) {
      const data = cell.getData() || {}
      if (isTransitionRelayNode(data.node)) {
        startNodeMove(data, cell, event)
        return
      }
      startNodeMove(data, cell, event)
    }
    return
  }
  const handle = containerMoveHandleFromEvent(event)
  const container = handle || containerElementFromEvent(event)
  if (!container) return
  const cell = cellFromEventTarget(container)
  if (!cell) return
  startContainerMove(cell.getData() || {}, cell, event)
}

function startCanvasPan(event) {
  if (canvasPan.value) {
    if (canvasPan.value.finished) {
      clearCanvasPan()
    } else {
      event.preventDefault()
      event.stopPropagation()
      return true
    }
  }
  if (!isCanvasPanStartEvent(event)) return false
  const graph = graphRef.value
  if (!graph) return false

  event.preventDefault()
  event.stopPropagation()
  captureCanvasPanPointer(event)
  const translation = graph.translate()
  canvasPan.value = {
    pointerX: event.clientX,
    pointerY: event.clientY,
    startTx: Number(translation?.tx || 0),
    startTy: Number(translation?.ty || 0),
    pointerId: event.pointerId,
    dragged: false,
  }
  window.addEventListener('pointermove', onCanvasPanMove)
  window.addEventListener('pointerup', finishCanvasPan)
  window.addEventListener('pointercancel', cancelCanvasPan)
  window.addEventListener('mousemove', onCanvasPanMove)
  window.addEventListener('mouseup', finishCanvasPan)
  startCanvasPanGlobalSuppression()
  window.addEventListener('blur', cancelCanvasPan)
  return true
}

function isCanvasPanStartEvent(event) {
  if (!hostRef.value?.contains(event?.target)) return false
  if (isCanvasPanInteractiveTarget(event)) return false
  if (event?.target?.closest?.('.x6-network-node')) return false
  if (event?.target?.closest?.('.container-title-row')) return false
  if (event?.target?.closest?.('.x6-edge')) return false
  return true
}

function isCanvasPanInteractiveTarget(event) {
  const target = event?.target
  if (!target?.closest) return false
  if (isPointerControlTarget(event)) return true
  return false
}

function nodeActionDedupeKey(data, action) {
  if (!action || !data?.kind) return ''
  const nodeId = data.node?.id || data.node?.state_node_id || data.node?.activity_node_id || data.node?.atomic_activity_id
  return nodeId ? `${data.kind}:${action}:${nodeId}` : ''
}

function isPointerControlTarget(event) {
  const target = event?.target
  return !!target?.closest?.(POINTER_CONTROL_SELECTOR)
}

function isBlankCanvasPointerEvent(event) {
  if (!hostRef.value?.contains(event?.target)) return false
  if (isCanvasPanInteractiveTarget(event)) return false
  if (event?.target?.closest?.('[data-cell-id]')) return false
  if (event?.target?.closest?.('.x6-node')) return false
  if (event?.target?.closest?.('.x6-edge')) return false
  return true
}

function captureCanvasPanPointer(event) {
  if (event.pointerId === undefined) return
  try {
    hostRef.value?.setPointerCapture?.(event.pointerId)
  } catch (_) {
    // Pointer capture can fail when the browser has already retargeted the event.
  }
}

function onCanvasPanMove(event) {
  const pan = canvasPan.value
  const graph = graphRef.value
  if (!pan || !graph) return
  const dx = event.clientX - pan.pointerX
  const dy = event.clientY - pan.pointerY
  if (!pan.dragged && Math.hypot(dx, dy) > 4) {
    pan.dragged = true
    hostRef.value?.classList.add('is-canvas-panning')
  }
  if (!pan.dragged) return
  event.preventDefault()
  event.stopPropagation?.()
  graph.translate(pan.startTx + dx, pan.startTy + dy)
}

function finishCanvasPan(event) {
  const pan = canvasPan.value
  stopCanvasPanListeners()
  if (!pan) return
  pan.finished = true
  if (pan.dragged) {
    event?.preventDefault?.()
    event?.stopPropagation?.()
  }
  clearCanvasPan()
}

function stopCanvasPanListeners() {
  const pan = canvasPan.value
  if (pan?.pointerId !== undefined) {
    try {
      hostRef.value?.releasePointerCapture?.(pan.pointerId)
    } catch (_) {
      // It is fine if capture was already released by the browser.
    }
  }
  hostRef.value?.classList.remove('is-canvas-panning')
  window.removeEventListener('pointermove', onCanvasPanMove)
  window.removeEventListener('pointerup', finishCanvasPan)
  window.removeEventListener('pointercancel', cancelCanvasPan)
  window.removeEventListener('mousemove', onCanvasPanMove)
  window.removeEventListener('mouseup', finishCanvasPan)
  window.removeEventListener('blur', cancelCanvasPan)
}

function clearCanvasPan() {
  stopCanvasPanListeners()
  stopCanvasPanGlobalSuppression()
  canvasPan.value = null
}

function cancelCanvasPan() {
  clearCanvasPan()
}

function suppressCanvasPanDefault(event) {
  if (!hostRef.value?.contains(event?.target) && !canvasPan.value) return
  if (!canvasPan.value) return
  event.preventDefault?.()
  event.stopPropagation?.()
}

function startCanvasPanGlobalSuppression() {
  window.addEventListener('dragstart', suppressCanvasPanDefault, true)
  window.addEventListener('selectstart', suppressCanvasPanDefault, true)
}

function stopCanvasPanGlobalSuppression() {
  window.removeEventListener('dragstart', suppressCanvasPanDefault, true)
  window.removeEventListener('selectstart', suppressCanvasPanDefault, true)
}

function nodeElementFromEvent(event) {
  if (event?.target?.closest?.('[data-action]')) return null
  return event?.target?.closest?.('.x6-network-node') || null
}

function containerMoveHandleFromEvent(event) {
  const targetHandle = event?.target?.closest?.('.container-move-handle')
  if (targetHandle) return targetHandle
  return document
    .elementsFromPoint(event.clientX, event.clientY)
    .map((element) => element.closest?.('.container-move-handle'))
    .find(Boolean) || null
}

function containerElementFromEvent(event) {
  if (event?.target?.closest?.('[data-action]')) return null
  return event?.target?.closest?.('.x6-network-container') || null
}

function cellFromEventTarget(target) {
  const graph = graphRef.value
  if (!graph || !target) return null
  const cellElement = target.closest?.('[data-cell-id]') ||
    target.closest?.('.x6-cell') ||
    target.closest?.('.x6-node')
  const cellId = cellElement?.getAttribute?.('data-cell-id') ||
    cellElement?.getAttribute?.('data-node-id') ||
    cellElement?.id
  if (cellId) {
    const cell = graph.getCellById(cellId)
    if (cell) return cell
  }
  const view = graph.findViewByElem?.(target) || graph.findView?.(target)
  return view?.cell || null
}

function handleNodeDoubleClick({ node, e }) {
  const data = node.getData() || {}
  if (!data.node || !props.canMutate) return
  e?.preventDefault?.()
  e?.stopPropagation?.()
  emit(data.kind === 'state' ? 'edit-state' : 'edit-activity', data.node)
}

function handleNodeContextMenu({ node, e }) {
  e?.preventDefault?.()
  e?.stopPropagation?.()
  const data = node.getData() || {}
  emit(data.kind === 'state' ? 'select-state' : 'select-activity', { node: data.node, event: e })
}

function handleEdgeClick({ edge, e }) {
  const data = edge?.getData?.() || {}
  if (!data.edge?.isCollapsedProxy) return
  e?.preventDefault?.()
  e?.stopPropagation?.()
  emit('proxy-edge-click', { edge: data.edge, event: e })
}

function handleEdgeDoubleClick({ edge, e }) {
  const data = edge?.getData?.() || {}
  if (!data.edge?.isCollapsedProxy) return
  e?.preventDefault?.()
  e?.stopPropagation?.()
  emit('proxy-edge-dblclick', { edge: data.edge, event: e })
}

function emitNodeMove(node) {
  if (rendering.value || !props.canMutate) return
  if (movingContainer.value || movingNode.value) return
  const data = node.getData() || {}
  if (!data.node) return

  if (data.role === 'container') {
    translateContainerChildren(node, data)
    emitContainerRootLayout(node, data)
    for (const childId of data.childIds || []) {
      const child = graphRef.value?.getCellById(childId)
      if (!child) continue
      emitLayoutForCell(child, child.getData() || {})
    }
    return
  }

  emitLayoutForCell(node, data)
}

function translateContainerChildren(cell, data) {
  const current = cell.position()
  const previous = data.lastPosition || data.containerOrigin || current
  const dx = current.x - previous.x
  const dy = current.y - previous.y
  if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return

  for (const childId of data.childIds || []) {
    const child = graphRef.value?.getCellById(childId)
    if (!child) continue
    const position = child.position()
    child.position(position.x + dx, position.y + dy)
  }

  cell.setData({
    ...data,
    lastPosition: {
      x: current.x,
      y: current.y,
    },
  })
}

function emitContainerRootLayout(cell, data) {
  if (!data.node || !data.kind) return
  const position = cell.position()
  const offset = data.rootOffset || { x: 0, y: 0 }
  emit('layout-change', {
    node: data.node,
    kind: data.kind,
    position: persistedLayoutPosition(data.node, {
      x: position.x + offset.x,
      y: position.y + offset.y,
    }),
  })
}

function emitLayoutForCell(cell, data) {
  if (!data.node || !data.kind) return
  const position = cell.position()
  emit('layout-change', {
    node: data.node,
    kind: data.kind,
    position: persistedLayoutPosition(data.node, position),
  })
}

function startContainerMove(data, cell, event) {
  if (movingContainer.value) {
    event.preventDefault()
    event.stopPropagation()
    return
  }
  if (!props.canMutate || data.role !== 'container' || !data.node) return
  event.preventDefault()
  event.stopPropagation()

  const start = cell.position()
  const childStarts = []
  for (const childId of data.childIds || []) {
    const child = graphRef.value?.getCellById(childId)
    if (!child) continue
    childStarts.push({
      cell: child,
      data: child.getData() || {},
      position: child.position(),
    })
  }

  movingContainer.value = {
    cell,
    data,
    start,
    childStarts,
    pointerX: event.clientX,
    pointerY: event.clientY,
    dx: 0,
    dy: 0,
  }
  window.addEventListener('pointermove', onContainerMove)
  window.addEventListener('pointerup', finishContainerMove)
  window.addEventListener('mousemove', onContainerMove)
  window.addEventListener('mouseup', finishContainerMove)
}

function startNodeMove(data, cell, event) {
  if (movingNode.value) {
    event.preventDefault()
    event.stopPropagation()
    return
  }
  if (!props.canMutate || !['node', 'transition-relay'].includes(data.role) || !data.node) return
  event.preventDefault()
  event.stopPropagation()
  movingNode.value = {
    cell,
    data,
    start: cell.position(),
    descendantStarts: descendantCellStartsForMovedNode(data, cell),
    pointerX: event.clientX,
    pointerY: event.clientY,
    dx: 0,
    dy: 0,
  }
  window.addEventListener('pointermove', onNodeMove)
  window.addEventListener('pointerup', finishNodeMove)
  window.addEventListener('mousemove', onNodeMove)
  window.addEventListener('mouseup', finishNodeMove)
}

function onNodeMove(event) {
  const move = movingNode.value
  if (!move) return
  const scale = normalizeZoom(props.canvasZoom)
  const dx = (event.clientX - move.pointerX) / scale
  const dy = (event.clientY - move.pointerY) / scale
  move.dx = dx
  move.dy = dy
  const nextX = Math.max(0, move.start.x + dx)
  const nextY = Math.max(8, move.start.y + dy)
  const actualDx = nextX - move.start.x
  const actualDy = nextY - move.start.y
  move.dx = actualDx
  move.dy = actualDy
  move.cell.setPosition(nextX, nextY)
  const size = move.cell.size()
  ensureGraphCanContain(nextX, nextY, size.width, size.height)
  for (const descendant of move.descendantStarts || []) {
    const childX = Math.max(0, descendant.position.x + actualDx)
    const childY = Math.max(8, descendant.position.y + actualDy)
    descendant.cell.setPosition(childX, childY)
    const childSize = descendant.cell.size()
    ensureGraphCanContain(childX, childY, childSize.width, childSize.height)
  }
}

function finishNodeMove() {
  const move = movingNode.value
  stopNodeMoveListeners()
  if (!move) return
  if (Math.abs(move.dx) < 0.5 && Math.abs(move.dy) < 0.5) {
    movingNode.value = null
    return
  }
  const position = move.cell.position()
  movingNode.value = null
  const dx = position.x - move.start.x
  const dy = position.y - move.start.y
  emit('layout-change', {
    node: move.data.node,
    kind: move.data.kind,
    position: persistedLayoutPosition(move.data.node, position),
    delta: roundedPosition({ x: dx, y: dy }),
    updates: layoutUpdatesForMovedNode(move.data, position, dx, dy),
  })
}

function descendantCellStartsForMovedNode(data, movedCell) {
  const seen = new Set([movedCell?.id])
  const starts = []
  for (const descendant of descendantsForMovedNode(data.node, data.kind)) {
    for (const cellId of [descendant.id, `${descendant.id}:container-title`]) {
      if (!cellId || seen.has(cellId)) continue
      const cell = graphRef.value?.getCellById(cellId)
      if (!cell) continue
      seen.add(cellId)
      starts.push({
        cell,
        position: cell.position(),
      })
    }
  }
  return starts
}

function layoutUpdatesForMovedNode(data, position, dx, dy) {
  const updates = [{
    node: data.node,
    kind: data.kind,
    position: persistedLayoutPosition(data.node, position),
  }]
  for (const descendant of descendantsForMovedNode(data.node, data.kind)) {
    const current = nodePosition(descendant, data.kind)
    updates.push({
      node: descendant,
      kind: data.kind,
      position: roundedPosition({
        x: Math.max(0, current.x + dx),
        y: Math.max(8, current.y + dy),
      }),
    })
  }
  return updates
}

function persistedLayoutPosition(node, displayPosition) {
  const shift = node?._network_editor_display_shift || { dx: 0, dy: 0 }
  return roundedPosition({
    x: displayPosition.x - Number(shift.persistDx || 0),
    y: displayPosition.y - Number(shift.persistDy || 0),
  })
}

function descendantsForMovedNode(node, kind) {
  if (!node) return []
  if (kind === 'state') {
    if (node.is_leaf || !node.state_node_id) return []
    return props.stateNodes.filter((candidate) =>
      candidate.id !== node.id &&
      candidate.state_node_id !== node.state_node_id &&
      statePathContains(candidate, node.state_node_id),
    )
  }
  if (node.activity_type !== 'activity_package' || !node.activity_node_id) return []
  return props.activityNodes.filter((candidate) =>
    candidate.id !== node.id &&
    activityPathContains(candidate, node.activity_node_id),
  )
}

function roundedPosition(position) {
  return {
    x: Math.round(position.x),
    y: Math.round(position.y),
  }
}

function stopNodeMoveListeners() {
  window.removeEventListener('pointermove', onNodeMove)
  window.removeEventListener('pointerup', finishNodeMove)
  window.removeEventListener('mousemove', onNodeMove)
  window.removeEventListener('mouseup', finishNodeMove)
}

function onContainerMove(event) {
  const move = movingContainer.value
  if (!move) return
  const scale = normalizeZoom(props.canvasZoom)
  const dx = (event.clientX - move.pointerX) / scale
  const dy = (event.clientY - move.pointerY) / scale
  move.dx = dx
  move.dy = dy
  const rootX = Math.max(8, move.start.x + dx)
  const rootY = Math.max(8, move.start.y + dy)
  move.cell.setPosition(rootX, rootY)
  const rootSize = move.cell.size()
  ensureGraphCanContain(rootX, rootY, rootSize.width, rootSize.height)
  for (const child of move.childStarts) {
    const current = child.cell.position()
    const nextX = Math.max(0, child.position.x + dx)
    const nextY = Math.max(8, child.position.y + dy)
    child.cell.translate(nextX - current.x, nextY - current.y)
    const childSize = child.cell.size()
    ensureGraphCanContain(nextX, nextY, childSize.width, childSize.height)
  }
}

function finishContainerMove() {
  const move = movingContainer.value
  stopContainerMoveListeners()
  if (!move) return
  if (Math.abs(move.dx) < 0.5 && Math.abs(move.dy) < 0.5) {
    movingContainer.value = null
    return
  }

  const rootPosition = move.cell.position()
  const rootOffset = move.data.rootOffset || { x: 0, y: 0 }
  const childLayouts = move.childStarts
    .map((child) => ({
      node: child.data.node,
      kind: child.data.kind,
      position: child.cell.position(),
      skipLayout: child.data.skipLayout,
    }))
    .filter((item) => item.node && item.kind && !item.skipLayout)

  movingContainer.value = null
  emit('layout-change', {
    node: move.data.node,
    kind: move.data.kind,
    position: {
      x: Math.round(rootPosition.x + rootOffset.x),
      y: Math.round(rootPosition.y + rootOffset.y),
    },
  })
  for (const child of childLayouts) {
    emit('layout-change', {
      node: child.node,
      kind: child.kind,
      position: {
        x: Math.round(child.position.x),
        y: Math.round(child.position.y),
      },
    })
  }
}

function stopContainerMoveListeners() {
  window.removeEventListener('pointermove', onContainerMove)
  window.removeEventListener('pointerup', finishContainerMove)
  window.removeEventListener('mousemove', onContainerMove)
  window.removeEventListener('mouseup', finishContainerMove)
}

function startResize(data, cell, event) {
  if (!props.canMutate || !data.node) return
  event.preventDefault()
  event.stopPropagation()
  const size = cell.size()
  resizing.value = {
    cell,
    data,
    startWidth: size.width,
    startHeight: size.height,
    pointerX: event.clientX,
    pointerY: event.clientY,
  }
  window.addEventListener('pointermove', onResizeMove)
  window.addEventListener('pointerup', finishResize)
}

function onResizeMove(event) {
  const resize = resizing.value
  if (!resize) return
  const scale = normalizeZoom(props.canvasZoom)
  const width = Math.max(CONTAINER_MIN_WIDTH, resize.startWidth + (event.clientX - resize.pointerX) / scale)
  const height = Math.max(CONTAINER_MIN_HEIGHT, resize.startHeight + (event.clientY - resize.pointerY) / scale)
  resize.cell.resize(width, height)
  const position = resize.cell.position()
  ensureGraphCanContain(position.x, position.y, width, height)
}

function finishResize() {
  const resize = resizing.value
  stopResizeListeners()
  if (!resize) return
  const size = resize.cell.size()
  emit('container-resize', {
    node: resize.data.node,
    kind: resize.data.kind,
    size: {
      width: Math.round(size.width),
      height: Math.round(size.height),
    },
  })
  resizing.value = null
}

function stopResizeListeners() {
  window.removeEventListener('pointermove', onResizeMove)
  window.removeEventListener('pointerup', finishResize)
}

function observeHostResize() {
  if (!hostRef.value || typeof ResizeObserver === 'undefined') return
  hostResizeObserver?.disconnect()
  hostResizeObserver = new ResizeObserver(() => {
    resizeGraph()
  })
  hostResizeObserver.observe(hostRef.value.parentElement || hostRef.value)
}

function viewportCanvasSize() {
  if (!hostRef.value) return { width: 0, height: 0 }
  const viewport = hostRef.value.parentElement || hostRef.value
  const rect = viewport.getBoundingClientRect()
  return {
    width: Math.floor(rect.width || viewport.clientWidth || 0),
    height: Math.floor(rect.height || viewport.clientHeight || 0),
  }
}

function graphSizeFor(contentSize = graphCanvasSize.value) {
  const hostSize = viewportCanvasSize()
  return {
    width: Math.max(hostSize.width, CANVAS_MIN_WIDTH, contentSize.width || 0),
    height: Math.max(hostSize.height, CANVAS_MIN_HEIGHT, contentSize.height || 0),
  }
}

function resizeGraph() {
  const graph = graphRef.value
  if (!graph || !hostRef.value) return
  const nextSize = graphSizeFor()
  if (nextSize.width === graphCanvasSize.value.width && nextSize.height === graphCanvasSize.value.height) return
  graph.resize(nextSize.width, nextSize.height)
  graphCanvasSize.value = nextSize
}

function resetViewportToContentOrigin() {
  const graph = graphRef.value
  if (!graph || !hostRef.value) return
  graph.translate(0, 0)
  const viewport = hostRef.value.parentElement || hostRef.value
  if (viewport) {
    viewport.scrollLeft = 0
    viewport.scrollTop = 0
  }
}

function ensureGraphCanContain(x, y, width = NODE_WIDTH, height = NODE_HEIGHT) {
  const graph = graphRef.value
  if (!graph) return
  const nextSize = {
    width: Math.max(
      graphCanvasSize.value.width,
      CANVAS_MIN_WIDTH,
      Math.ceil(Math.max(0, x) + Math.max(0, width) + CANVAS_CONTENT_PADDING_X),
    ),
    height: Math.max(
      graphCanvasSize.value.height,
      CANVAS_MIN_HEIGHT,
      Math.ceil(Math.max(0, y) + Math.max(0, height) + CANVAS_CONTENT_PADDING_Y),
    ),
  }
  if (nextSize.width === graphCanvasSize.value.width && nextSize.height === graphCanvasSize.value.height) return
  graph.resize(nextSize.width, nextSize.height)
  graphCanvasSize.value = nextSize
}

function normalizeZoom(value) {
  return Math.min(1.6, Math.max(0.65, Number(value) || 1))
}

function isSelected(node, kind) {
  if (kind === 'state') {
    return String(props.selectedStateId || '') === String(node.state_node_id || '')
  }
  const relayActivityGraphId = transitionRelayActivityGraphId(node)
  if (relayActivityGraphId) {
    return String(props.selectedActivityGraphId || '') === String(relayActivityGraphId)
  }
  return String(props.selectedActivityGraphId || '') === String(node.id || '')
}

function isExpandedNode(node, kind) {
  if (kind === 'state') {
    if (!node?.state_node_id) return false
    const hasVisibleChild = props.stateNodes.some((candidate) =>
      candidate.id !== node.id &&
      candidate.state_node_id !== node.state_node_id &&
      statePathContains(candidate, node.state_node_id),
    )
    if (!hasVisibleChild) return false
    if ((props.expandedStateGraphIds || []).some((id) => String(id) === String(node.id))) return true
    if (Number(props.stateDepth) === 0) return true
    const rootIds = (props.stateRootIds || []).map((id) => String(id || '')).filter(Boolean)
    if (!rootIds.length) return false
    const maxDepth = Math.max(1, Number(props.stateDepth) || 1)
    return rootIds.some((rootId) => {
      if (String(node.state_node_id || '') === rootId) return maxDepth > 1
      const scopeNode = props.stateNodes.find((item) => String(item.state_node_id || '') === rootId)
      if (scopeNode && statePathContains(scopeNode, node.state_node_id)) return true
      const relativeDepth = stateRelativeDepthFromRoot(node, rootId)
      return Number.isFinite(relativeDepth) && relativeDepth >= 1 && relativeDepth < maxDepth
    })
  }
  if (!node?.activity_node_id) return false
  const hasVisibleChild = props.activityNodes.some((candidate) =>
    candidate.id !== node.id && activityPathContains(candidate, node.activity_node_id),
  )
  if (!hasVisibleChild) return false
  if (Number(props.activityDepth) === 0) return true
  const rootIds = (props.activityScopeIds || []).map((id) => String(id || '')).filter(Boolean)
  if (!rootIds.length) return false
  const maxDepth = Math.max(1, Number(props.activityDepth) || 1)
  return rootIds.some((rootId) => {
    if (String(node.activity_node_id || '') === rootId) return maxDepth > 1
    const scopeNode = props.activityNodes.find((item) => String(item.activity_node_id || '') === rootId)
    if (scopeNode && activityPathContains(scopeNode, node.activity_node_id)) return true
    const relativeDepth = activityRelativeDepthFromRoot(node, rootId)
    return Number.isFinite(relativeDepth) && relativeDepth >= 1 && relativeDepth < maxDepth
  })
}

function nodeMeta(node, kind) {
  if (node?.display_meta) return node.display_meta
  if (kind === 'state') {
    const parts = [`${node.leaf_count || 1} leaves`]
    if (node.reference_ids?.length) parts.push(`${node.reference_ids.length} refs`)
    return parts.join(' / ')
  }
  if (isTransitionRelayNode(node)) return 'transition relay'
  const type = node.activity_type === 'activity_package' ? 'package' : 'atomic'
  return `${type} / L${node.level || '-'}`
}

function nodePosition(node, kind) {
  const saved = metadataLayout(node)
  if (saved) return saved
  const sourceIndex = kind === 'state' ? stateIndex.value : activityIndex.value
  const index = sourceIndex.get(node.id) || 0
  return {
    x: kind === 'state' ? STATE_DEFAULT_X : ACTIVITY_DEFAULT_X,
    y: TOP_PADDING + index * ROW_GAP,
  }
}

function metadataLayout(node) {
  const layout = node?.metadata_json?._network_editor_layout
  if (!layout || typeof layout !== 'object') return null
  const x = finiteNumber(layout.x)
  const y = finiteNumber(layout.y)
  if (x === null || y === null) return null
  return { x, y }
}

function metadataContainer(node) {
  const container = node?.metadata_json?._network_editor_container
  if (!container || typeof container !== 'object') return null
  const width = finiteNumber(container.width)
  const height = finiteNumber(container.height)
  if (width === null || height === null) return null
  return { width, height }
}

function statePathContains(node, stateNodeId) {
  if (!node || !stateNodeId) return false
  if (String(node.parent_id || '') === String(stateNodeId)) return true
  if (String(node.parent_state_node_id || '') === String(stateNodeId)) return true
  if (stateGraphPathContains(node, stateNodeId)) return true
  if (stateAncestorContains(node, stateNodeId)) return true
  return false
}

function stateGraphPathContains(node, stateNodeId) {
  if (!node || !stateNodeId) return false
  if ((node.reference_parent_ids || []).some((id) => String(id) === String(stateNodeId))) return true
  const pathIds = node.path_ids || []
  if (!Array.isArray(pathIds)) return false
  if (pathIds.some((item) => Array.isArray(item))) {
    return pathIds.some((path) =>
      Array.isArray(path) && path.some((id) => String(id) === String(stateNodeId)),
    )
  }
  return pathIds.some((id) => String(id) === String(stateNodeId))
}

function stateAncestorContains(node, stateNodeId) {
  const seen = new Set()
  const stack = [node?.parent_id, node?.parent_state_node_id].filter(Boolean)
  while (stack.length) {
    const parentId = stack.pop()
    if (!parentId || seen.has(String(parentId))) continue
    if (String(parentId) === String(stateNodeId)) return true
    seen.add(String(parentId))
    const parentInstances = props.stateNodes.filter((candidate) =>
      String(candidate.state_node_id || '') === String(parentId),
    )
    for (const parent of parentInstances) {
      if (stateGraphPathContains(parent, stateNodeId)) return true
      stack.push(parent.parent_id || parent.parent_state_node_id || null)
    }
  }
  return false
}

function statePathLists(node) {
  const pathIds = Array.isArray(node?.path_ids) ? node.path_ids : []
  if (pathIds.some((item) => Array.isArray(item))) {
    return pathIds
      .filter((path) => Array.isArray(path))
      .map((path) => path.map((id) => String(id)))
      .filter((path) => path.length)
  }
  if (pathIds.length) return [pathIds.map((id) => String(id))]
  const path = []
  if (node?.parent_id) path.push(String(node.parent_id))
  if (node?.parent_state_node_id) path.push(String(node.parent_state_node_id))
  if (node?.state_node_id) path.push(String(node.state_node_id))
  return path.length ? [path] : []
}

function stateRelativeDepthFromRoot(node, rootId) {
  const rootKey = String(rootId || '')
  if (!node || !rootKey) return null
  if (node.state_node_id && String(node.state_node_id) === rootKey) return 1
  for (const path of statePathLists(node)) {
    const index = path.findIndex((id) => id === rootKey)
    if (index >= 0) return path.length - index
  }
  if (String(node.parent_id || '') === rootKey) return 2
  if (String(node.parent_state_node_id || '') === rootKey) return 2
  return null
}

function activityPathContains(node, activityNodeId) {
  if (!node || !activityNodeId) return false
  if (String(node.parent_id || '') === String(activityNodeId)) return true
  const pathIds = node.path_ids || []
  if (Array.isArray(pathIds)) {
    if (pathIds.some((item) => Array.isArray(item))) {
      if (pathIds.some((path) =>
        Array.isArray(path) && path.some((id) => String(id) === String(activityNodeId)),
      )) return true
    } else if (pathIds.some((id) => String(id) === String(activityNodeId))) {
      return true
    }
  }
  return (node.parent_activity_node_ids || []).some((id) => String(id) === String(activityNodeId))
}

function activityPathLists(node) {
  const pathIds = Array.isArray(node?.path_ids) ? node.path_ids : []
  if (pathIds.some((item) => Array.isArray(item))) {
    return pathIds
      .filter((path) => Array.isArray(path))
      .map((path) => path.map((id) => String(id)))
      .filter((path) => path.length)
  }
  if (pathIds.length) return [pathIds.map((id) => String(id))]
  const parentIds = Array.isArray(node?.parent_activity_node_ids) ? node.parent_activity_node_ids : []
  const path = parentIds.map((id) => String(id))
  if (node?.activity_node_id) path.push(String(node.activity_node_id))
  else if (node?.atomic_activity_id) path.push(String(node.atomic_activity_id))
  return path.length ? [path] : []
}

function activityRelativeDepthFromRoot(node, rootId) {
  const rootKey = String(rootId || '')
  if (!node || !rootKey) return null
  if (node.activity_node_id && String(node.activity_node_id) === rootKey) return 1
  for (const path of activityPathLists(node)) {
    const index = path.findIndex((id) => id === rootKey)
    if (index >= 0) return path.length - index
  }
  if (String(node.parent_id || '') === rootKey) return 2
  const parentIds = Array.isArray(node.parent_activity_node_ids) ? node.parent_activity_node_ids.map((id) => String(id)) : []
  const parentIndex = parentIds.findIndex((id) => id === rootKey)
  if (parentIndex >= 0) return parentIds.length - parentIndex + 1
  return null
}

function finiteNumber(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/`/g, '&#96;')
}
</script>

<style>
.x6-network-canvas {
  box-sizing: border-box;
  flex: 1 1 auto;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border: 1px solid #d8e2ef;
  border-radius: 6px;
  background: #f8fafc;
  touch-action: none;
  user-select: none;
  -webkit-user-drag: none;
}

.x6-graph {
  cursor: default;
}

.x6-network-canvas.is-canvas-panning .x6-graph {
  cursor: grabbing;
}

.x6-network-canvas .x6-node foreignObject {
  overflow: visible;
}

.x6-network-canvas .network-flow-edge-line {
  transition: stroke 0.16s ease, stroke-width 0.16s ease, stroke-opacity 0.16s ease, filter 0.16s ease;
}

.x6-network-canvas .network-flow-edge-line.flow-active {
  filter: drop-shadow(0 0 5px rgba(245, 158, 11, 0.42));
  animation: network-flow-dash 0.95s linear infinite;
}

.x6-network-canvas .network-flow-edge-line.flow-backbone {
  filter: drop-shadow(0 1px 1px rgba(15, 23, 42, 0.08));
}

.x6-network-canvas .network-flow-edge-line.route-corridor,
.x6-network-canvas .network-flow-edge-line.route-channel,
.x6-network-canvas .network-flow-edge-line.route-fork,
.x6-network-canvas .network-flow-edge-line.route-join,
.x6-network-canvas .network-flow-edge-line.route-elk,
.x6-network-canvas .network-flow-edge-line.route-elk-lane,
.x6-network-canvas .network-flow-edge-line.flow-proxy,
.x6-network-canvas .network-flow-edge-line.flow-aggregate {
  stroke-linecap: round;
}

@keyframes network-flow-dash {
  to {
    stroke-dashoffset: -20;
  }
}

@media (prefers-reduced-motion: reduce) {
  .x6-network-canvas .network-flow-edge-line.flow-active {
    animation: none;
  }
}

.x6-network-node,
.x6-network-container,
.container-title-row {
  box-sizing: border-box;
  width: 100%;
  height: 100%;
  color: #0f172a;
  font-size: 12px;
  letter-spacing: 0;
  user-select: none;
}

.x6-network-node.flow-muted,
.container-title-row.flow-muted {
  opacity: 0.38;
  filter: saturate(0.62);
}

.x6-network-node.flow-active,
.container-title-row.flow-active {
  box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.3), 0 8px 20px rgba(15, 23, 42, 0.12);
}

.x6-network-node {
  position: relative;
  display: grid;
  grid-template-areas:
    "name"
    "transition"
    "warnings";
  grid-template-columns: minmax(0, 1fr);
  align-content: center;
  gap: 1px;
  padding: 6px 28px 6px 22px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #ffffff;
  box-shadow: 0 5px 12px rgba(15, 23, 42, 0.07);
  overflow: visible;
}

.x6-network-node::after,
.container-title-row::after {
  content: "";
  position: absolute;
  z-index: 1;
  left: 56px;
  right: 56px;
  bottom: -32px;
  height: 34px;
  pointer-events: none;
}

.x6-state-node {
  justify-items: center;
  padding: 6px 28px 6px 26px;
  border: 2px solid #2563eb;
  border-radius: 999px;
  background: #ffffff;
  text-align: center;
}

.x6-activity-node {
  border-left: 4px solid #0f9f6e;
}

.x6-transition-relay-node {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  padding: 6px 10px 6px 24px;
  border: 1px solid #6ee7b7;
  border-left: 4px solid #0f9f6e;
  border-radius: 8px;
  background: #f0fdf4;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.12);
  cursor: pointer;
}

.x6-transition-relay-node .relay-dot {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: #0f9f6e;
  box-shadow:
    0 0 0 3px rgba(15, 159, 110, 0.16),
    0 2px 5px rgba(15, 23, 42, 0.16);
  transition: transform 0.14s ease, box-shadow 0.14s ease, background 0.14s ease;
}

.x6-transition-relay-node .relay-label {
  display: flex;
  min-width: 0;
  flex-direction: column;
  line-height: 1.15;
}

.x6-transition-relay-node .relay-label strong,
.x6-transition-relay-node .relay-label span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.x6-transition-relay-node .relay-label strong {
  color: #065f46;
  font-size: 11px;
}

.x6-transition-relay-node .relay-label span {
  color: #334155;
  font-size: 10px;
}

.x6-transition-relay-node:hover .relay-dot,
.x6-transition-relay-node:focus-visible .relay-dot,
.x6-transition-relay-node.selected .relay-dot,
.x6-transition-relay-node.flow-active .relay-dot {
  background: #f59e0b;
  box-shadow:
    0 0 0 4px rgba(245, 158, 11, 0.2),
    0 4px 10px rgba(15, 23, 42, 0.22);
  transform: scale(1.16);
}

.x6-transition-relay-node .relay-tooltip {
  position: absolute;
  z-index: 40;
  left: 50%;
  bottom: calc(100% + 9px);
  max-width: 260px;
  min-width: 132px;
  padding: 7px 9px;
  border: 1px solid #bfdbfe;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.16);
  color: #0f172a;
  font-size: 12px;
  font-weight: 700;
  line-height: 16px;
  opacity: 0;
  overflow-wrap: anywhere;
  pointer-events: none;
  text-align: center;
  transform: translate(-50%, 4px);
  transition: opacity 0.14s ease, transform 0.14s ease;
  white-space: normal;
}

.x6-transition-relay-node .relay-tooltip::after {
  content: "";
  position: absolute;
  left: 50%;
  bottom: -6px;
  width: 10px;
  height: 10px;
  border-right: 1px solid #bfdbfe;
  border-bottom: 1px solid #bfdbfe;
  background: rgba(255, 255, 255, 0.98);
  transform: translateX(-50%) rotate(45deg);
}

.x6-transition-relay-node:hover .relay-tooltip,
.x6-transition-relay-node:focus-visible .relay-tooltip {
  opacity: 1;
  transform: translate(-50%, 0);
}

.x6-network-node.selected,
.container-title-row.selected {
  border-color: #f59e0b;
  box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.2), 0 8px 16px rgba(15, 23, 42, 0.1);
}

.x6-network-container.selected {
  box-shadow: inset 0 0 0 1px rgba(245, 158, 11, 0.16), 0 8px 18px rgba(15, 23, 42, 0.06);
}

.node-code {
  grid-area: code;
  min-width: 0;
  max-width: 100%;
  overflow: visible;
  color: #475569;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  line-height: 13px;
  overflow-wrap: anywhere;
  text-overflow: clip;
  white-space: normal;
  word-break: break-word;
}

.node-name {
  grid-area: name;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  font-weight: 700;
  line-height: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-meta {
  grid-area: meta;
  min-width: 0;
  max-width: 100%;
  overflow: visible;
  color: #64748b;
  font-size: 11px;
  line-height: 13px;
  overflow-wrap: anywhere;
  text-overflow: clip;
  white-space: normal;
  word-break: break-word;
}

.node-transition {
  grid-area: transition;
  min-width: 0;
  max-width: 100%;
  display: block;
  overflow: hidden;
  color: #0f766e;
  font-size: 10px;
  font-weight: 600;
  line-height: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-transition-warnings {
  grid-area: warnings;
  display: flex;
  flex-wrap: nowrap;
  justify-content: center;
  gap: 2px;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.state-transition-badge {
  display: inline-flex;
  align-items: center;
  max-width: 76px;
  min-height: 14px;
  padding: 0 4px;
  border-radius: 999px;
  background: #fef3c7;
  color: #92400e;
  font-size: 10px;
  font-weight: 700;
  line-height: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.state-transition-badge.badge-danger {
  background: #fee2e2;
  color: #991b1b;
}

.state-transition-badge.badge-info {
  background: #e0f2fe;
  color: #075985;
}

.node-actions {
  display: contents;
}

.node-action {
  display: inline-flex;
  align-items: center;
  min-height: 18px;
  padding: 0 5px;
  border-radius: 4px;
  color: #1d4ed8;
  font-size: 10px;
  line-height: 18px;
  cursor: pointer;
}

.node-action[data-action="edit"] {
  display: none;
}

.node-icon-action,
.node-action[data-action="toggle"] {
  position: absolute;
  z-index: 6;
  top: 4px;
  right: 5px;
  justify-content: center;
  width: 20px;
  min-height: 20px;
  padding: 0;
  border: 1px solid #cbd5e1;
  border-radius: 999px;
  background: #ffffff;
  box-shadow: 0 3px 8px rgba(15, 23, 42, 0.1);
  color: transparent;
  font-size: 0;
  line-height: 1;
}

.node-icon-action::before,
.node-action[data-action="toggle"]::before {
  content: "\2795";
  color: #2563eb;
  font-size: 11px;
}

.is-expanded .node-icon-action::before,
.is-expanded .node-action[data-action="toggle"]::before {
  content: "\2796";
}

.node-text-action,
.node-action[data-action="focus"] {
  position: absolute;
  right: 6px;
  bottom: 5px;
}

.node-create-row {
  display: contents;
}

.node-create-action,
.node-action[data-action="create"] {
  position: absolute;
  z-index: 20;
  right: 5px;
  bottom: 3px;
  left: auto;
  justify-content: center;
  min-width: 62px;
  min-height: 20px;
  padding: 0 8px;
  border: 1px solid #bfdbfe;
  border-radius: 999px;
  background: #ffffff;
  box-shadow: 0 6px 14px rgba(37, 99, 235, 0.14);
  color: #1d4ed8;
  opacity: 0;
  pointer-events: none;
  transform: translateY(-2px);
  transition: opacity 0.14s ease, transform 0.14s ease;
  white-space: nowrap;
}

.x6-network-node:hover .node-create-action,
.x6-network-node:focus-within .node-create-action,
.x6-network-node:hover .node-action[data-action="create"],
.x6-network-node:focus-within .node-action[data-action="create"],
.container-title-row:hover .node-create-action,
.container-title-row:focus-within .node-create-action,
.container-title-row:hover .node-action[data-action="create"],
.container-title-row:focus-within .node-action[data-action="create"] {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0);
}

.node-action:hover,
.node-action:focus-visible {
  background: #dbeafe;
  outline: none;
}

.layout-handle {
  position: absolute;
  top: 7px;
  left: 7px;
  width: 8px;
  height: 18px;
  border-radius: 999px;
  background:
    radial-gradient(circle at 3px 3px, #94a3b8 1.5px, transparent 2px),
    radial-gradient(circle at 7px 3px, #94a3b8 1.5px, transparent 2px),
    radial-gradient(circle at 3px 9px, #94a3b8 1.5px, transparent 2px),
    radial-gradient(circle at 7px 9px, #94a3b8 1.5px, transparent 2px),
    radial-gradient(circle at 3px 15px, #94a3b8 1.5px, transparent 2px),
    radial-gradient(circle at 7px 15px, #94a3b8 1.5px, transparent 2px);
  cursor: move;
}

.collapsed-relation-badge {
  position: absolute;
  z-index: 12;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 16px;
  padding: 0 4px;
  border: 1px solid #bfdbfe;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 10px;
  font-weight: 700;
  line-height: 16px;
  pointer-events: none;
  white-space: nowrap;
}

.collapsed-relation-badge.badge-input {
  top: 50%;
  left: -10px;
  transform: translate(-100%, -50%);
}

.collapsed-relation-badge.badge-output {
  top: 50%;
  right: -10px;
  transform: translate(100%, -50%);
}

.collapsed-relation-badge.badge-internal {
  left: 50%;
  bottom: -21px;
  transform: translateX(-50%);
  border-color: #cbd5e1;
  background: #f8fafc;
  color: #334155;
}

.port-left {
  left: -18px;
}

.port-right {
  right: -18px;
}

.x6-network-container {
  position: relative;
  border: 1px solid rgba(37, 99, 235, 0.28);
  border-radius: 6px;
  background: rgba(239, 246, 255, 0.16);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.76), 0 8px 18px rgba(15, 23, 42, 0.05);
  pointer-events: auto;
}

.x6-activity-container {
  border-color: rgba(15, 159, 110, 0.26);
  background: rgba(236, 253, 245, 0.16);
}

.container-title-row {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px;
  min-height: 42px;
  padding: 6px 42px 6px 10px;
  border: 1px solid rgba(148, 163, 184, 0.38);
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 3px 10px rgba(15, 23, 42, 0.05);
  overflow: visible;
  pointer-events: auto;
}

.x6-activity-container-title {
  border-color: rgba(15, 159, 110, 0.38);
}

.container-title-row .node-action[data-action="create"] {
  right: 8px;
  bottom: 3px;
  left: auto;
  transform: none;
}

.container-title-row:hover .node-action[data-action="create"],
.container-title-row:focus-within .node-action[data-action="create"] {
  transform: none;
}

.container-title-row .node-action[data-action="focus"] {
  right: 76px;
  bottom: 3px;
}

.container-title-copy {
  display: grid;
  min-width: 0;
}

.container-move-handle {
  cursor: move;
}

.container-resize-handle {
  position: absolute;
  right: 7px;
  bottom: 7px;
  width: 16px;
  height: 16px;
  border-right: 2px solid #64748b;
  border-bottom: 2px solid #64748b;
  cursor: nwse-resize;
  pointer-events: auto;
}
</style>
