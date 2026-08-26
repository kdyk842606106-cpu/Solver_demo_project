<template>
  <div class="network-board">
    <div class="board-toolbar">
      <div class="board-title">
        <span>活动网络图</span>
        <el-tag size="small" effect="plain">{{ graphStats.nodeCount }} 个活动</el-tag>
        <el-tag size="small" effect="plain">{{ graphStats.edgeCount }} 条依赖</el-tag>
      </div>
      <div class="board-actions">
        <el-radio-group v-model="layoutMode" size="small">
          <el-radio-button label="dag">依赖层级</el-radio-button>
          <el-radio-button label="time">时间分布</el-radio-button>
        </el-radio-group>
        <el-switch v-model="criticalOnly" size="small" active-text="关键路径" />
      </div>
    </div>

    <div class="board-content">
      <div ref="canvasWrap" class="canvas-wrap">
        <div v-if="!visibleTasks.length" class="empty-state">暂无可展示的活动依赖</div>
        <canvas
          ref="canvasEl"
          class="network-canvas"
          :style="canvasStyle"
          @mousemove="onCanvasMove"
          @mouseleave="hideTooltip"
        />
        <div
          v-if="hoverTask"
          class="canvas-tooltip"
          :style="{ left: `${tooltip.x}px`, top: `${tooltip.y}px` }"
        >
          <strong>{{ hoverTask.step_order }}. {{ getTaskName(hoverTask) }}</strong>
          <span>编码：{{ getTaskCode(hoverTask) }}</span>
          <span>时间：{{ hoverTask.start_min ?? 0 }}m - {{ hoverTask.end_min ?? 0 }}m</span>
          <span>时长：{{ hoverTask.duration_min ?? 0 }}m</span>
          <span>资源：{{ formatResources(hoverTask.resources) }}</span>
        </div>
      </div>

      <aside class="insight-panel">
        <div class="insight-grid">
          <div class="insight-item">
            <span class="insight-label">总工期</span>
            <strong>{{ makespan }}m</strong>
          </div>
          <div class="insight-item">
            <span class="insight-label">关键活动</span>
            <strong>{{ graphStats.criticalCount }}</strong>
          </div>
          <div class="insight-item">
            <span class="insight-label">并行宽度</span>
            <strong>{{ graphStats.maxWidth }}</strong>
          </div>
          <div class="insight-item">
            <span class="insight-label">网络深度</span>
            <strong>{{ graphStats.depth }}</strong>
          </div>
        </div>

        <div class="legend">
          <span v-for="role in roleLegend" :key="role.key" class="legend-item">
            <span class="legend-dot" :style="{ background: role.color }" />
            {{ role.label }}
          </span>
          <span class="legend-item">
            <span class="legend-dot critical-dot" />
            关键路径
          </span>
        </div>

        <div class="hotspot-section">
          <div class="section-title">资源热点</div>
          <template v-if="resourceHotspots.length">
            <div v-for="item in resourceHotspots" :key="item.name" class="hotspot-row">
              <span class="hotspot-name">{{ item.name }}</span>
              <el-tag size="small" type="info">{{ item.count }} 次</el-tag>
            </div>
          </template>
          <span v-else class="muted">暂无资源占用数据</span>
        </div>

        <div class="hotspot-section">
          <div class="section-title">结构提示</div>
          <div class="hint-line">起点活动 {{ graphStats.sourceCount }} 个</div>
          <div class="hint-line">收尾活动 {{ graphStats.sinkCount }} 个</div>
          <div class="hint-line">最长依赖层级 {{ graphStats.depth }} 层</div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  tasks: { type: Array, default: () => [] },
  makespan: { type: Number, default: 0 },
  criticalPath: { type: Array, default: () => [] },
})

const ROLE_COLORS = {
  normal: '#0f766e',
  repair: '#dc2626',
  pulled_forward: '#2563eb',
  delayed: '#d97706',
}

const ROLE_LABELS = {
  normal: '正常',
  repair: '维修',
  pulled_forward: '提前',
  delayed: '延后',
}

const NODE_WIDTH = 150
const NODE_HEIGHT = 58
const COLUMN_GAP = 230
const ROW_GAP = 112
const PADDING_X = 72
const PADDING_Y = 72

const canvasWrap = ref(null)
const canvasEl = ref(null)
const wrapWidth = ref(720)
const layoutMode = ref('dag')
const criticalOnly = ref(false)
const hoverTask = ref(null)
const tooltip = ref({ x: 0, y: 0 })
let resizeObserver = null
let hitBoxes = []

const criticalCodes = computed(() => new Set(props.criticalPath ?? []))
const sortedTasks = computed(() =>
  [...(props.tasks ?? [])].sort((a, b) => (a.step_order ?? 0) - (b.step_order ?? 0))
)
const visibleTasks = computed(() => {
  if (!criticalOnly.value) return sortedTasks.value
  return sortedTasks.value.filter((task) => isCriticalTask(task))
})

const roleLegend = computed(() =>
  Object.entries(ROLE_LABELS).map(([key, label]) => ({ key, label, color: ROLE_COLORS[key] }))
)

const graphModel = computed(() => buildGraphModel(visibleTasks.value))

const graphStats = computed(() => {
  const model = graphModel.value
  const targetOrders = new Set(model.edges.map((edge) => edge.targetOrder))
  const sourceOrders = new Set(model.edges.map((edge) => edge.sourceOrder))
  return {
    nodeCount: model.nodes.length,
    edgeCount: model.edges.length,
    sourceCount: model.nodes.filter((node) => !targetOrders.has(node.task.step_order)).length,
    sinkCount: model.nodes.filter((node) => !sourceOrders.has(node.task.step_order)).length,
    criticalCount: visibleTasks.value.filter((task) => isCriticalTask(task)).length,
    maxWidth: model.maxWidth,
    depth: model.depth,
  }
})

const canvasSize = computed(() => {
  const model = graphModel.value
  const widthByDepth = layoutMode.value === 'time'
    ? Math.max(980, visibleTasks.value.length * 120)
    : Math.max(760, model.depth * COLUMN_GAP + PADDING_X * 2)
  const heightByRows = Math.max(420, model.maxWidth * ROW_GAP + PADDING_Y * 2)
  return {
    width: Math.max(wrapWidth.value, widthByDepth),
    height: heightByRows,
  }
})

const canvasStyle = computed(() => ({
  width: `${canvasSize.value.width}px`,
  height: `${canvasSize.value.height}px`,
}))

const resourceHotspots = computed(() => {
  const counts = new Map()
  visibleTasks.value.forEach((task) => {
    normalizeResources(task.resources).forEach((name) => {
      counts.set(name, (counts.get(name) ?? 0) + 1)
    })
  })
  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
    .slice(0, 5)
})

function normalizeResources(resources) {
  if (!Array.isArray(resources)) return []
  return resources
    .map((resource) => {
      if (typeof resource === 'string' || typeof resource === 'number') return String(resource)
      if (!resource || typeof resource !== 'object') return ''
      return resource.resource_code ?? resource.code ?? resource.resource_name ?? resource.name ?? ''
    })
    .filter(Boolean)
}

function formatResources(resources) {
  const labels = normalizeResources(resources)
  return labels.length ? labels.join(', ') : '无'
}

function getTaskCode(task) {
  return task.op_rule_code ?? task.op_code ?? `STEP-${task.step_order ?? '?'}`
}

function getTaskName(task) {
  return task.op_rule_name ?? task.op_name ?? getTaskCode(task)
}

function isCriticalTask(task) {
  return criticalCodes.value.has(getTaskCode(task))
}

function getPredecessors(task) {
  return task.predecessors ?? task.predecessor_ids ?? []
}

function buildGraphModel(tasks) {
  const taskByOrder = new Map(tasks.map((task) => [task.step_order, task]))
  const levelCache = new Map()
  const visiting = new Set()

  function validPredecessors(task) {
    return [...new Set(getPredecessors(task))].filter((order) => (
      order !== task.step_order &&
      taskByOrder.has(order) &&
      Number(order) < Number(task.step_order)
    ))
  }

  function levelOf(task) {
    if (levelCache.has(task.step_order)) return levelCache.get(task.step_order)
    if (visiting.has(task.step_order)) return 0
    visiting.add(task.step_order)
    const predecessorLevels = validPredecessors(task)
      .map((order) => taskByOrder.get(order))
      .filter(Boolean)
      .map((predecessor) => levelOf(predecessor))
    const level = predecessorLevels.length ? Math.max(...predecessorLevels) + 1 : 0
    visiting.delete(task.step_order)
    levelCache.set(task.step_order, level)
    return level
  }

  tasks.forEach(levelOf)

  const rowsByLevel = new Map()
  tasks.forEach((task) => {
    const level = levelCache.get(task.step_order) ?? 0
    const row = rowsByLevel.get(level) ?? 0
    rowsByLevel.set(level, row + 1)
  })

  const rowCursorByLevel = new Map()
  const maxTime = Math.max(props.makespan || 0, ...tasks.map((task) => task.end_min ?? 0), 1)
  const depth = tasks.length ? Math.max(...levelCache.values()) + 1 : 0
  const maxWidth = Math.max(0, ...rowsByLevel.values())

  const nodes = tasks.map((task, index) => {
    const level = levelCache.get(task.step_order) ?? 0
    const row = rowCursorByLevel.get(level) ?? 0
    rowCursorByLevel.set(level, row + 1)
    const rowCount = rowsByLevel.get(level) ?? 1
    const y = centeredRowY(row, rowCount, maxWidth)
    const x = layoutMode.value === 'time'
      ? PADDING_X + ((task.start_min ?? 0) / maxTime) * Math.max(1, canvasSize.value.width - PADDING_X * 2 - NODE_WIDTH)
      : PADDING_X + level * COLUMN_GAP

    return { task, level, row, orderIndex: index, x, y }
  })

  const edges = []
  tasks.forEach((task) => {
    validPredecessors(task).forEach((sourceOrder) => {
      edges.push({
        sourceOrder,
        targetOrder: task.step_order,
      })
    })
  })

  return { nodes, edges, depth, maxWidth }
}

function centeredRowY(row, rowCount, maxWidth) {
  const usedHeight = Math.max(0, (rowCount - 1) * ROW_GAP)
  const availableHeight = Math.max(0, (maxWidth - 1) * ROW_GAP)
  const offset = (availableHeight - usedHeight) / 2
  return PADDING_Y + offset + row * ROW_GAP
}

function draw() {
  const canvas = canvasEl.value
  if (!canvas) return

  const width = canvasSize.value.width
  const height = canvasSize.value.height
  const dpr = window.devicePixelRatio || 1
  canvas.width = Math.round(width * dpr)
  canvas.height = Math.round(height * dpr)

  const ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, width, height)
  drawBackground(ctx, width, height)

  const model = graphModel.value
  const nodeByOrder = new Map(model.nodes.map((node) => [node.task.step_order, node]))
  hitBoxes = []

  model.edges.forEach((edge) => {
    const source = nodeByOrder.get(edge.sourceOrder)
    const target = nodeByOrder.get(edge.targetOrder)
    if (source && target) drawEdge(ctx, source, target)
  })

  model.nodes.forEach((node) => drawNode(ctx, node))
}

function drawBackground(ctx, width, height) {
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, width, height)
  ctx.strokeStyle = '#e2e8f0'
  ctx.lineWidth = 1
  for (let x = PADDING_X; x < width; x += COLUMN_GAP) {
    ctx.beginPath()
    ctx.moveTo(x, 24)
    ctx.lineTo(x, height - 24)
    ctx.stroke()
  }
}

function drawEdge(ctx, source, target) {
  const critical = isCriticalTask(source.task) && isCriticalTask(target.task)
  const startX = source.x + NODE_WIDTH
  const startY = source.y + NODE_HEIGHT / 2
  const endX = target.x
  const endY = target.y + NODE_HEIGHT / 2
  const midX = startX + Math.max(48, (endX - startX) / 2)

  ctx.save()
  ctx.strokeStyle = critical ? '#f59e0b' : '#64748b'
  ctx.fillStyle = critical ? '#f59e0b' : '#64748b'
  ctx.lineWidth = critical ? 3 : 1.8
  ctx.setLineDash(critical ? [] : [0])
  ctx.beginPath()
  ctx.moveTo(startX, startY)
  ctx.bezierCurveTo(midX, startY, midX, endY, endX - 10, endY)
  ctx.stroke()
  drawArrow(ctx, endX - 10, endY, 0)
  ctx.restore()
}

function drawArrow(ctx, x, y, angle) {
  const size = 8
  ctx.beginPath()
  ctx.moveTo(x, y)
  ctx.lineTo(x - size * Math.cos(angle - Math.PI / 6), y - size * Math.sin(angle - Math.PI / 6))
  ctx.lineTo(x - size * Math.cos(angle + Math.PI / 6), y - size * Math.sin(angle + Math.PI / 6))
  ctx.closePath()
  ctx.fill()
}

function drawNode(ctx, node) {
  const task = node.task
  const role = task.step_role ?? 'normal'
  const critical = isCriticalTask(task)
  const x = node.x
  const y = node.y
  const fill = ROLE_COLORS[role] ?? ROLE_COLORS.normal

  ctx.save()
  ctx.shadowColor = critical ? 'rgba(245, 158, 11, 0.28)' : 'rgba(15, 23, 42, 0.14)'
  ctx.shadowBlur = critical ? 16 : 8
  roundRect(ctx, x, y, NODE_WIDTH, NODE_HEIGHT, 8)
  ctx.fillStyle = fill
  ctx.fill()
  ctx.shadowBlur = 0
  ctx.lineWidth = critical ? 4 : 2
  ctx.strokeStyle = critical ? '#f59e0b' : '#ffffff'
  ctx.stroke()

  ctx.fillStyle = '#ffffff'
  ctx.font = '700 12px "Segoe UI", "Microsoft YaHei", sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(`${task.step_order ?? ''}. ${shortText(getTaskCode(task), 14)}`, x + NODE_WIDTH / 2, y + 21)
  ctx.font = '11px "Segoe UI", "Microsoft YaHei", sans-serif'
  ctx.fillText(shortText(getTaskName(task), 16), x + NODE_WIDTH / 2, y + 39)

  hitBoxes.push({ task, x, y, width: NODE_WIDTH, height: NODE_HEIGHT })
  ctx.restore()
}

function roundRect(ctx, x, y, width, height, radius) {
  ctx.beginPath()
  ctx.moveTo(x + radius, y)
  ctx.lineTo(x + width - radius, y)
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius)
  ctx.lineTo(x + width, y + height - radius)
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height)
  ctx.lineTo(x + radius, y + height)
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius)
  ctx.lineTo(x, y + radius)
  ctx.quadraticCurveTo(x, y, x + radius, y)
  ctx.closePath()
}

function shortText(text, maxLength) {
  const value = String(text ?? '')
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}…` : value
}

function onCanvasMove(event) {
  const rect = canvasEl.value.getBoundingClientRect()
  const x = event.clientX - rect.left
  const y = event.clientY - rect.top
  const hit = hitBoxes.find((box) =>
    x >= box.x && x <= box.x + box.width && y >= box.y && y <= box.y + box.height
  )
  hoverTask.value = hit?.task ?? null
  tooltip.value = {
    x: x + 14,
    y: y + 14,
  }
}

function hideTooltip() {
  hoverTask.value = null
}

onMounted(() => {
  resizeObserver = new ResizeObserver((entries) => {
    const width = entries[0]?.contentRect?.width
    if (width) wrapWidth.value = Math.floor(width)
    nextTick(draw)
  })
  resizeObserver.observe(canvasWrap.value)
  nextTick(draw)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
})

watch(
  () => [visibleTasks.value, props.makespan, props.criticalPath, layoutMode.value, criticalOnly.value, canvasSize.value],
  () => nextTick(draw),
  { deep: true },
)
</script>

<style scoped>
.network-board {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.board-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.board-title,
.board-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.board-title > span:first-child {
  color: #0f172a;
  font-weight: 600;
}

.board-content {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.canvas-wrap {
  position: relative;
  width: 100%;
  min-width: 0;
  min-height: 420px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
  overflow: auto;
  overscroll-behavior: contain;
}

.network-canvas {
  display: block;
  cursor: default;
}

.canvas-tooltip {
  position: absolute;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-width: 260px;
  padding: 8px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.96);
  color: #334155;
  font-size: 12px;
  line-height: 1.45;
  pointer-events: none;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.12);
}

.canvas-tooltip strong {
  color: #0f172a;
}

.empty-state {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-size: 13px;
  background: rgba(255, 255, 255, 0.7);
}

.insight-panel {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(220px, 0.8fr) minmax(220px, 0.8fr);
  gap: 14px;
  min-width: 0;
}

.insight-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.insight-item {
  min-width: 0;
  padding: 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
}

.insight-label {
  display: block;
  margin-bottom: 4px;
  color: #64748b;
  font-size: 12px;
}

.insight-item strong {
  color: #0f172a;
  font-size: 20px;
  line-height: 1;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  color: #475569;
  font-size: 12px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.legend-dot {
  width: 12px;
  height: 12px;
  border-radius: 3px;
}

.critical-dot {
  background: #ffffff;
  border: 3px solid #f59e0b;
}

.hotspot-section {
  min-width: 0;
  padding: 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
}

.section-title {
  margin-bottom: 8px;
  color: #334155;
  font-size: 13px;
  font-weight: 600;
}

.hotspot-row,
.hint-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 26px;
  color: #475569;
  font-size: 13px;
}

.hotspot-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.muted {
  color: #94a3b8;
  font-size: 13px;
}

@media (max-width: 960px) {
  .insight-panel {
    grid-template-columns: 1fr;
  }

  .insight-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .insight-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
