<template>
  <div ref="hostRef" class="x6-network-canvas" data-testid="network-editor-x6-canvas" />
</template>

<script setup>
import { Graph, Shape } from '@antv/x6'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const NODE_WIDTH = 220
const NODE_HEIGHT = 62
const CONTAINER_MIN_WIDTH = 268
const CONTAINER_MIN_HEIGHT = 128
const CONTAINER_HEADER_SPACE = 76
const STATE_DEFAULT_X = 80
const ACTIVITY_DEFAULT_X = 520
const TOP_PADDING = 48
const ROW_GAP = 88
const CANVAS_MIN_WIDTH = 980
const CANVAS_MIN_HEIGHT = 640
const INPUT_PORT_ID = 'input'
const OUTPUT_PORT_ID = 'output'

let shapesRegistered = false

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
  activityDepth: {
    type: Number,
    default: 2,
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
  'focus-activity',
  'layout-change',
  'container-resize',
  'blank-dblclick',
  'connect-nodes',
])

const hostRef = ref(null)
const graphRef = ref(null)
const rendering = ref(false)
const resizing = ref(null)
const movingContainer = ref(null)
const movingNode = ref(null)
const connectionDrag = ref(null)

const stateIndex = computed(() => new Map(props.stateNodes.map((node, index) => [node.id, index])))
const activityIndex = computed(() => new Map(props.activityNodes.map((node, index) => [node.id, index])))

onMounted(async () => {
  registerShapes()
  await nextTick()
  createGraph()
  renderGraph()
  window.addEventListener('resize', resizeGraph)
  hostRef.value?.addEventListener('click', handleHtmlActionClick, true)
  hostRef.value?.addEventListener('pointerdown', handleCanvasPointerDown, true)
  hostRef.value?.addEventListener('mousedown', handleCanvasPointerDown, true)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeGraph)
  hostRef.value?.removeEventListener('click', handleHtmlActionClick, true)
  hostRef.value?.removeEventListener('pointerdown', handleCanvasPointerDown, true)
  hostRef.value?.removeEventListener('mousedown', handleCanvasPointerDown, true)
  stopResizeListeners()
  stopContainerMoveListeners()
  stopNodeMoveListeners()
  stopConnectionDragListeners()
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
    html: (cell) => renderContainerHtml(cell.getData()),
    effect: ['data', 'size'],
  })

  Shape.HTML.register({
    shape: 'network-activity-container',
    width: CONTAINER_MIN_WIDTH,
    height: CONTAINER_MIN_HEIGHT,
    html: (cell) => renderContainerHtml(cell.getData()),
    effect: ['data', 'size'],
  })

  Shape.HTML.register({
    shape: 'network-container-title',
    width: CONTAINER_MIN_WIDTH,
    height: 58,
    html: (cell) => renderContainerTitleHtml(cell.getData()),
    effect: ['data', 'size'],
  })
}

function createGraph() {
  if (!hostRef.value) return
  graphRef.value = new Graph({
    container: hostRef.value,
    width: hostRef.value.clientWidth || CANVAS_MIN_WIDTH,
    height: CANVAS_MIN_HEIGHT,
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
      nodeMovable: props.canMutate,
      edgeMovable: false,
      arrowheadMovable: false,
      vertexMovable: false,
      vertexAddable: false,
      vertexDeletable: false,
    }),
  })

  graphRef.value.on('node:click', handleNodeClick)
  graphRef.value.on('node:mousedown', handleNodeMouseDown)
  graphRef.value.on('node:dblclick', handleNodeDoubleClick)
  graphRef.value.on('node:contextmenu', handleNodeContextMenu)
  graphRef.value.on('edge:connected', handleEdgeConnected)
  graphRef.value.on('blank:dblclick', ({ e, x, y }) => {
    emit('blank-dblclick', { x, y, event: e })
  })
  graphRef.value.on('node:moved', ({ node }) => emitNodeMove(node))
}

function createTemporaryEdge() {
  return new Shape.Edge({
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
  const canConnect = !!props.canMutate
  return {
    groups: {
      in: {
        position: 'left',
        attrs: {
          circle: {
            r: 6,
            magnet: canConnect ? 'passive' : false,
            stroke: '#64748b',
            strokeWidth: 2,
            fill: '#ffffff',
            cursor: canConnect ? 'crosshair' : 'default',
          },
        },
      },
      out: {
        position: 'right',
        attrs: {
          circle: {
            r: 6,
            magnet: canConnect,
            stroke: '#64748b',
            strokeWidth: 2,
            fill: '#ffffff',
            cursor: canConnect ? 'crosshair' : 'default',
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

function validateMagnet({ magnet }) {
  return !!props.canMutate && magnet?.getAttribute('port-group') === 'out'
}

function validateConnection({ sourceCell, targetCell, sourceMagnet, targetMagnet }) {
  if (!props.canMutate || !sourceCell || !targetCell || sourceCell.id === targetCell.id) return false
  if (sourceMagnet?.getAttribute('port-group') !== 'out') return false
  if (targetMagnet?.getAttribute('port-group') !== 'in') return false

  const sourceData = sourceCell.getData() || {}
  const targetData = targetCell.getData() || {}
  if (sourceData.kind === targetData.kind) return false
  if (sourceData.kind === 'state' && targetData.kind === 'activity') {
    return activityNodeSupportsBinding(targetData.node)
  }
  if (sourceData.kind === 'activity' && targetData.kind === 'state') {
    return activityNodeSupportsBinding(sourceData.node)
  }
  return false
}

function handleEdgeConnected({ edge, isNew }) {
  if (!isNew || !edge || edge.getData()?.handledByCanvas) return
  const source = edge.getSource()
  const target = edge.getTarget()
  if (!source?.cell || !target?.cell || source.port !== OUTPUT_PORT_ID || target.port !== INPUT_PORT_ID) return

  const sourceCell = graphRef.value?.getCellById(source.cell)
  const targetCell = graphRef.value?.getCellById(target.cell)
  if (!validateConnectedCells(sourceCell, targetCell)) return

  edge.setData({ ...(edge.getData() || {}), handledByCanvas: true })
  emit('connect-nodes', {
    source: endpointFromCell(sourceCell),
    target: endpointFromCell(targetCell),
  })
  edge.remove({ silent: true })
}

function validateConnectedCells(sourceCell, targetCell) {
  if (!sourceCell || !targetCell) return false
  const sourceData = sourceCell.getData() || {}
  const targetData = targetCell.getData() || {}
  if (sourceData.kind === 'state' && targetData.kind === 'activity') {
    return activityNodeSupportsBinding(targetData.node)
  }
  if (sourceData.kind === 'activity' && targetData.kind === 'state') {
    return activityNodeSupportsBinding(sourceData.node)
  }
  return false
}

function endpointFromCell(cell) {
  const data = cell?.getData?.() || {}
  return {
    cellId: String(cell?.id || ''),
    kind: data.kind,
    role: data.role,
    node: data.node,
  }
}

function activityNodeSupportsBinding(node) {
  return !!node && (!!node.atomic_activity_id || node.activity_type === 'virtual')
}

function renderGraph() {
  const graph = graphRef.value
  if (!graph) return

  rendering.value = true
  const { cells, canvasSize } = buildCells()
  graph.clearCells()
  graph.fromJSON({ cells })

  graph.resize(canvasSize.width, canvasSize.height)
  graph.zoomTo(normalizeZoom(props.canvasZoom))
  rendering.value = false
}

function buildCells() {
  const cells = []
  const nodeCellIds = new Set()
  const containerRoots = new Set()
  const stateContainers = buildStateContainers()
  const activityContainers = buildActivityContainers()

  for (const container of stateContainers) {
    containerRoots.add(container.node.id)
    cells.push(createContainerCell(container, 'state'))
    cells.push(createContainerTitleCell(container, 'state'))
  }
  for (const container of activityContainers) {
    containerRoots.add(container.node.id)
    cells.push(createContainerCell(container, 'activity'))
    cells.push(createContainerTitleCell(container, 'activity'))
  }

  for (const node of props.stateNodes) {
    if (!containerRoots.has(node.id)) {
      cells.push(createNodeCell(node, 'state'))
    }
    nodeCellIds.add(node.id)
  }

  for (const node of props.activityNodes) {
    if (!containerRoots.has(node.id)) {
      cells.push(createNodeCell(node, 'activity'))
    }
    nodeCellIds.add(node.id)
  }

  const edgeCells = props.edges
    .map(createEdgeCell)
    .filter(Boolean)
    .filter((edge) => nodeCellIds.has(edge.source.cell) && nodeCellIds.has(edge.target.cell))
  cells.push(...edgeCells)

  const canvasSize = cells.reduce(
    (size, cell) => {
      if (cell.shape === 'edge') return size
      const x = finiteNumber(cell.x) ?? finiteNumber(cell.position?.x) ?? 0
      const y = finiteNumber(cell.y) ?? finiteNumber(cell.position?.y) ?? 0
      const width = finiteNumber(cell.width) ?? finiteNumber(cell.size?.width) ?? NODE_WIDTH
      const height = finiteNumber(cell.height) ?? finiteNumber(cell.size?.height) ?? NODE_HEIGHT
      return {
        width: Math.max(size.width, Math.ceil(x + width + 220)),
        height: Math.max(size.height, Math.ceil(y + height + 180)),
      }
    },
    { width: CANVAS_MIN_WIDTH, height: CANVAS_MIN_HEIGHT },
  )

  return { cells, canvasSize }
}

function buildStateContainers() {
  return props.stateNodes
    .filter((node) => !node.is_leaf && isExpandedNode(node, 'state'))
    .map((node) => {
      const children = props.stateNodes.filter((candidate) => (
        candidate.id !== node.id &&
        candidate.state_node_id !== node.state_node_id &&
        statePathContains(candidate, node.state_node_id)
      ))
      if (!children.length) return null
      return buildContainerModel(node, children, 'state')
    })
    .filter(Boolean)
}

function buildActivityContainers() {
  return props.activityNodes
    .filter((node) => node.activity_type === 'virtual' && node.activity_node_id && isExpandedNode(node, 'activity'))
    .map((node) => {
      const children = props.activityNodes.filter((candidate) => (
        candidate.id !== node.id &&
        activityPathContains(candidate, node.activity_node_id)
      ))
      if (!children.length) return null
      return buildContainerModel(node, children, 'activity')
    })
    .filter(Boolean)
}

function buildContainerModel(node, children, kind) {
  const members = [node, ...children]
  const bounds = memberBounds(members, kind)
  const saved = metadataContainer(node)
  const width = Math.max(CONTAINER_MIN_WIDTH, saved?.width || bounds.width + 52)
  const height = Math.max(CONTAINER_MIN_HEIGHT, saved?.height || bounds.height + CONTAINER_HEADER_SPACE + 36)
  return {
    node,
    children,
    x: Math.max(8, bounds.x - 26),
    y: Math.max(8, bounds.y - CONTAINER_HEADER_SPACE),
    width,
    height,
  }
}

function memberBounds(nodes, kind) {
  const positions = nodes.map((node) => nodePosition(node, kind))
  const minX = Math.min(...positions.map((point) => point.x))
  const minY = Math.min(...positions.map((point) => point.y))
  const maxX = Math.max(...positions.map((point) => point.x + NODE_WIDTH))
  const maxY = Math.max(...positions.map((point) => point.y + NODE_HEIGHT))
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
  const rootPosition = nodePosition(node, kind)
  return {
    id: node.id,
    shape: isState ? 'network-state-container' : 'network-activity-container',
    x: container.x,
    y: container.y,
    width: container.width,
    height: container.height,
    zIndex: 1,
    data: {
      kind,
      role: 'container',
      skipLayout: true,
      node,
      canMutate: props.canMutate,
      selected: isSelected(node, kind),
      testId: isState
        ? `network-editor-state-package-container-${node.state_node_id}`
        : `network-editor-virtual-activity-container-${node.id}`,
      titleTestId: `network-editor-container-body-title-${node.id}`,
      moveTestId: `network-editor-container-body-move-${node.id}`,
      label: node.name || node.code || node.id,
      code: node.code || node.id,
      meta: isState
        ? `${container.children.length} 个状态`
        : `${container.children.length} 个活动`,
      actionLabel: isState ? '折叠' : '折叠',
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
    height: 58,
    zIndex: 40,
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
        : `network-editor-virtual-activity-container-move-${node.id}`,
      label: node.name || node.code || node.id,
      code: node.code || node.id,
      meta: isState
        ? `${container.children.length} states`
        : `${container.children.length} activities`,
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
  return {
    id: node.id,
    shape: kind === 'state' ? 'network-state-node' : 'network-activity-node',
    x: position.x,
    y: position.y,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
    zIndex: 10,
    data: {
      kind,
      role: 'node',
      node,
      canMutate: props.canMutate,
      selected: isSelected(node, kind),
      testId: kind === 'state'
        ? `network-editor-state-node-${node.state_node_id}`
        : `network-editor-activity-node-${node.id}`,
      label: node.name || node.code || node.id,
      code: node.code || node.id,
      meta: nodeMeta(node, kind),
      canToggle: kind === 'state' ? !node.is_leaf : node.activity_type === 'virtual',
      actionLabel: isExpandedNode(node, kind) ? '折叠' : '展开',
      isVirtual: kind === 'activity' && node.activity_type === 'virtual',
    },
    ports: nodePorts(),
  }
}

function createEdgeCell(edge) {
  if (!edge?.source_id || !edge?.target_id) return null
  const isInput = edge.type === 'STATE_TO_ACTIVITY'
  const label = edge.displayLabel || edge.aggregateLabel || ''
  return {
    id: String(edge.id),
    shape: 'edge',
    source: { cell: edge.source_id, port: OUTPUT_PORT_ID },
    target: { cell: edge.target_id, port: INPUT_PORT_ID },
    zIndex: 0,
    labels: label ? [{ attrs: { label: { text: label } } }] : undefined,
    attrs: {
      line: {
        stroke: isInput ? '#2563eb' : '#0f9f6e',
        strokeWidth: edge.aggregate ? 3 : 2,
        strokeDasharray: edge.aggregate ? '6 5' : ((edge.is_draft || edge.is_pending) ? '4 4' : ''),
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
    data: { edge },
  }
}

function renderNodeHtml(data) {
  const nodeClass = data.kind === 'state' ? 'x6-state-node' : 'x6-activity-node'
  const selectedClass = data.selected ? ' selected' : ''
  const moveHandle = data.canMutate
    ? '<span class="layout-handle" title="Drag to move"></span>'
    : ''
  const toggle = data.canToggle
    ? `<span class="node-action" role="button" tabindex="0" data-action="toggle">${escapeHtml(data.actionLabel)}</span>`
    : ''
  const edit = data.canMutate
    ? '<span class="node-action" role="button" tabindex="0" data-action="edit">编辑</span>'
    : ''
  const focus = data.kind === 'activity' && data.isVirtual
    ? '<span class="node-action" role="button" tabindex="0" data-action="focus">专注</span>'
    : ''
  const create = data.canMutate && data.canToggle
    ? `<span class="node-action" role="button" tabindex="0" data-action="create">${data.kind === 'state' ? '添加状态' : (data.node?.level === 1 ? '子活动' : '原子')}</span>`
    : ''

  return `
    <div class="x6-network-node ${nodeClass}${selectedClass}" data-testid="${escapeAttr(data.testId)}">
      ${moveHandle}
      <span class="semantic-port port-left" data-port-role="input">输入</span>
      <span class="semantic-port port-right" data-port-role="output">产出</span>
      <span class="node-code">${escapeHtml(data.code)}</span>
      <span class="node-name">${escapeHtml(data.label)}</span>
      <span class="node-meta">${escapeHtml(data.meta)}</span>
      <span class="node-actions">${toggle}${focus}${edit}${create}</span>
    </div>
  `
}

function renderContainerHtml(data) {
  const selectedClass = data.selected ? ' selected' : ''
  const kindClass = data.kind === 'state' ? 'x6-state-container' : 'x6-activity-container'
  const titleCopyAttrs = data.canMutate
    ? `class="container-title-copy container-move-handle" data-testid="${escapeAttr(data.moveTestId)}" title="Drag container"`
    : 'class="container-title-copy"'
  const resizeHandle = data.canMutate
    ? '<span class="container-resize-handle" data-action="resize" title="Resize container"></span>'
    : ''
  const create = data.canMutate
    ? `<span class="node-action" role="button" tabindex="0" data-action="create">${data.kind === 'state' ? '添加状态' : (data.node?.level === 1 ? '子活动' : '原子')}</span>`
    : ''
  const focus = data.kind === 'activity'
    ? '<span class="node-action" role="button" tabindex="0" data-action="focus">专注</span>'
    : ''

  return `
    <div class="x6-network-container ${kindClass}${selectedClass}" data-testid="${escapeAttr(data.testId)}">
      <div class="container-title-row" data-testid="${escapeAttr(data.titleTestId)}">
        <div ${titleCopyAttrs}>
          <span class="node-code">${escapeHtml(data.code)}</span>
          <span class="node-name">${escapeHtml(data.label)}</span>
          <span class="node-meta">${escapeHtml(data.meta)}</span>
        </div>
        <span class="node-actions">
          <span class="node-action" role="button" tabindex="0" data-action="toggle">${escapeHtml(data.actionLabel)}</span>
          ${focus}
          ${create}
        </span>
      </div>
      ${resizeHandle}
    </div>
  `
}

function renderContainerTitleHtml(data) {
  return renderContainerHtml(data)
}

function handleNodeClick({ node, e }) {
  const data = node.getData() || {}
  const action = e?.target?.dataset?.action
  if (dispatchNodeAction(data, action, e)) return
  emit(data.kind === 'state' ? 'select-state' : 'select-activity', { node: data.node, event: e })
}

function handleHtmlActionClick(event) {
  const actionElement = event?.target?.closest?.('[data-action]')
  if (!actionElement || !hostRef.value?.contains(actionElement)) return
  const cell = cellFromEventTarget(actionElement)
  if (!cell) return
  const data = cell.getData() || {}
  const action = actionElement.dataset.action
  if (!action) return
  event.preventDefault()
  event.stopPropagation()
  dispatchNodeAction(data, action, event)
}

function dispatchNodeAction(data, action, event) {
  if (action === 'resize') return true
  if (action === 'toggle') {
    emit(data.kind === 'state' ? 'toggle-state-expansion' : 'toggle-activity-expansion', data.node)
    return true
  }
  if (action === 'create') {
    emit(data.kind === 'state' ? 'create-state-inside' : 'create-activity-inside', data.node)
    return true
  }
  if (action === 'focus') {
    emit('focus-activity', data.node)
    return true
  }
  if (action === 'edit') {
    emit(data.kind === 'state' ? 'edit-state' : 'edit-activity', data.node)
    return true
  }
  return false
}

function handleNodeMouseDown({ node, e }) {
  if (e?.target?.classList?.contains('container-move-handle')) {
    startContainerMove(node.getData() || {}, node, e)
    return
  }
  if (e?.target?.dataset?.action === 'resize') {
    startResize(node.getData() || {}, node, e)
  }
}

function handleCanvasPointerDown(event) {
  if (startConnectionDragFromPort(event)) return
  const nodeElement = nodeElementFromEvent(event)
  if (nodeElement) {
    const cell = cellFromEventTarget(nodeElement)
    if (cell) startNodeMove(cell.getData() || {}, cell, event)
    return
  }
  const handle = containerMoveHandleFromEvent(event)
  const container = handle || containerElementFromEvent(event)
  if (!container) return
  const cell = cellFromEventTarget(container)
  if (!cell) return
  startContainerMove(cell.getData() || {}, cell, event)
}

function nodeElementFromEvent(event) {
  if (event?.target?.closest?.('[data-action]')) return null
  if (event?.target?.closest?.('.semantic-port')) return null
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
  const cellElement = target?.closest?.('[data-cell-id]') || target?.closest?.('.x6-node')
  const cellId = cellElement?.getAttribute?.('data-cell-id')
  if (!cellId) return null
  return graphRef.value?.getCellById(cellId) || null
}

function startConnectionDragFromPort(event) {
  if (!props.canMutate || connectionDrag.value) return false
  const port = event?.target?.closest?.('.semantic-port[data-port-role="output"]')
  if (!port || !hostRef.value?.contains(port)) return false
  const sourceCell = cellFromEventTarget(port)
  if (!sourceCell?.getData?.()?.kind) return false
  const graph = graphRef.value
  if (!graph) return false

  event.preventDefault()
  event.stopPropagation()
  const edge = createTemporaryEdge()
  edge.setSource({ cell: sourceCell.id, port: OUTPUT_PORT_ID })
  edge.setTarget(graph.clientToLocal(event.clientX, event.clientY))
  graph.addEdge(edge)
  connectionDrag.value = { sourceCell, edge }
  window.addEventListener('pointermove', onConnectionDragMove)
  window.addEventListener('pointerup', finishConnectionDrag)
  window.addEventListener('mousemove', onConnectionDragMove)
  window.addEventListener('mouseup', finishConnectionDrag)
  return true
}

function onConnectionDragMove(event) {
  const drag = connectionDrag.value
  const graph = graphRef.value
  if (!drag || !graph) return
  drag.edge.setTarget(graph.clientToLocal(event.clientX, event.clientY))
}

function finishConnectionDrag(event) {
  const drag = connectionDrag.value
  stopConnectionDragListeners()
  if (!drag) return
  const targetPort = inputPortFromPoint(event.clientX, event.clientY)
  const targetCell = targetPort ? cellFromEventTarget(targetPort) : null
  if (validateConnectedCells(drag.sourceCell, targetCell)) {
    emit('connect-nodes', {
      source: endpointFromCell(drag.sourceCell),
      target: endpointFromCell(targetCell),
    })
  }
  drag.edge.remove({ silent: true })
  connectionDrag.value = null
}

function inputPortFromPoint(x, y) {
  return document
    .elementsFromPoint(x, y)
    .map((element) => element.closest?.('.semantic-port[data-port-role="input"]'))
    .find((element) => element && hostRef.value?.contains(element)) || null
}

function stopConnectionDragListeners() {
  window.removeEventListener('pointermove', onConnectionDragMove)
  window.removeEventListener('pointerup', finishConnectionDrag)
  window.removeEventListener('mousemove', onConnectionDragMove)
  window.removeEventListener('mouseup', finishConnectionDrag)
}

function handleNodeDoubleClick({ node, e }) {
  const data = node.getData() || {}
  if (data.role !== 'container') return
  const point = graphRef.value?.clientToLocal(e.clientX, e.clientY)
  emit('blank-dblclick', {
    x: point?.x || node.getPosition().x,
    y: point?.y || node.getPosition().y,
    containerNode: data.node,
    kind: data.kind,
    event: e,
  })
}

function handleNodeContextMenu({ node, e }) {
  const data = node.getData() || {}
  emit(data.kind === 'state' ? 'select-state' : 'select-activity', { node: data.node, event: e })
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
    position: {
      x: Math.round(position.x + offset.x),
      y: Math.round(position.y + offset.y),
    },
  })
}

function emitLayoutForCell(cell, data) {
  if (!data.node || !data.kind) return
  const position = cell.position()
  emit('layout-change', {
    node: data.node,
    kind: data.kind,
    position: {
      x: Math.round(position.x),
      y: Math.round(position.y),
    },
  })
}

function startContainerMove(data, cell, event) {
  if (movingContainer.value) return
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
  if (movingNode.value) return
  if (!props.canMutate || data.role !== 'node' || !data.node) return
  event.preventDefault()
  event.stopPropagation()
  movingNode.value = {
    cell,
    data,
    start: cell.position(),
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
  move.cell.setPosition(Math.max(0, move.start.x + dx), Math.max(8, move.start.y + dy))
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
  emit('layout-change', {
    node: move.data.node,
    kind: move.data.kind,
    position: {
      x: Math.round(position.x),
      y: Math.round(position.y),
    },
  })
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
  move.cell.setPosition(Math.max(8, move.start.x + dx), Math.max(8, move.start.y + dy))
  for (const child of move.childStarts) {
    const current = child.cell.position()
    const nextX = Math.max(0, child.position.x + dx)
    const nextY = Math.max(8, child.position.y + dy)
    child.cell.translate(nextX - current.x, nextY - current.y)
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

function resizeGraph() {
  const graph = graphRef.value
  if (!graph || !hostRef.value) return
  graph.resize(Math.max(hostRef.value.clientWidth, CANVAS_MIN_WIDTH), Math.max(hostRef.value.clientHeight, CANVAS_MIN_HEIGHT))
}

function normalizeZoom(value) {
  return Math.min(1.6, Math.max(0.65, Number(value) || 1))
}

function isSelected(node, kind) {
  if (kind === 'state') {
    return String(props.selectedStateId || '') === String(node.state_node_id || '')
  }
  return String(props.selectedActivityGraphId || '') === String(node.id || '')
}

function isExpandedNode(node, kind) {
  if (kind === 'state') {
    if (Number(props.stateDepth) !== 0 || !props.stateRootIds.length) return false
    const rootIds = props.stateRootIds.map((id) => String(id || ''))
    const isRoot = rootIds.some((rootId) => rootId === String(node.state_node_id || ''))
    const isNestedUnderRoot = rootIds.some((rootId) =>
      rootId !== String(node.state_node_id || '') && statePathContains(node, rootId),
    )
    return (isRoot || isNestedUnderRoot) &&
      props.stateNodes.some((candidate) =>
        candidate.id !== node.id &&
        candidate.state_node_id !== node.state_node_id &&
        statePathContains(candidate, node.state_node_id),
      )
  }
  return Number(props.activityDepth) === 0 &&
    props.activityNodes.some((candidate) => candidate.id !== node.id && activityPathContains(candidate, node.activity_node_id))
}

function nodeMeta(node, kind) {
  if (kind === 'state') {
    const parts = [`${node.leaf_count || 1} leaves`]
    if (node.reference_ids?.length) parts.push(`${node.reference_ids.length} refs`)
    return parts.join(' / ')
  }
  const type = node.activity_type === 'virtual' ? 'virtual' : 'atomic'
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
  width: 100%;
  min-height: 640px;
  height: 70vh;
  overflow: hidden;
  border: 1px solid #d8e2ef;
  border-radius: 6px;
  background: #f8fafc;
}

.x6-graph {
  cursor: default;
}

.x6-network-node,
.x6-network-container {
  box-sizing: border-box;
  width: 100%;
  height: 100%;
  color: #0f172a;
  font-size: 12px;
  letter-spacing: 0;
  user-select: none;
}

.x6-network-node {
  position: relative;
  display: grid;
  grid-template-areas:
    "code actions"
    "name actions"
    "meta meta";
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 4px 8px;
  padding: 9px 12px 9px 26px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #ffffff;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.08);
}

.x6-state-node {
  border-left: 4px solid #2563eb;
}

.x6-activity-node {
  border-left: 4px solid #0f9f6e;
}

.x6-network-node.selected,
.x6-network-container.selected {
  border-color: #f59e0b;
  box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.22), 0 12px 22px rgba(15, 23, 42, 0.12);
}

.node-code {
  grid-area: code;
  overflow: hidden;
  color: #475569;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-name {
  grid-area: name;
  overflow: hidden;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-meta {
  grid-area: meta;
  overflow: hidden;
  color: #64748b;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-actions {
  grid-area: actions;
  display: inline-flex;
  align-items: flex-start;
  gap: 4px;
  max-width: 96px;
}

.node-action {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 5px;
  border-radius: 4px;
  color: #1d4ed8;
  font-size: 11px;
  line-height: 20px;
  cursor: pointer;
}

.node-action:hover,
.node-action:focus-visible {
  background: #dbeafe;
  outline: none;
}

.layout-handle {
  position: absolute;
  top: 8px;
  left: 8px;
  width: 10px;
  height: 22px;
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

.semantic-port {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 18px;
  border: 1px solid #cbd5e1;
  border-radius: 999px;
  background: #f8fafc;
  color: #475569;
  font-size: 10px;
  pointer-events: auto;
}

.semantic-port[data-port-role="output"] {
  cursor: crosshair;
}

.port-left {
  left: -18px;
}

.port-right {
  right: -18px;
}

.x6-network-container {
  position: relative;
  border: 2px solid rgba(37, 99, 235, 0.42);
  border-radius: 6px;
  background: rgba(239, 246, 255, 0.24);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.85), 0 12px 24px rgba(15, 23, 42, 0.08);
  pointer-events: none;
}

.x6-activity-container {
  border-color: rgba(15, 159, 110, 0.44);
  background: rgba(236, 253, 245, 0.26);
}

.container-title-row {
  position: absolute;
  top: 8px;
  left: 10px;
  right: 10px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  min-height: 42px;
  padding: 8px 10px;
  border: 1px solid rgba(148, 163, 184, 0.38);
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.9);
  pointer-events: auto;
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
