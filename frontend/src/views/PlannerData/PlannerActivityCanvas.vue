<template>
  <div class="canvas-shell" data-testid="planner-activity-canvas">
    <div class="canvas-legend">
      <span><i class="dot activity-dot" />活动节点</span>
      <span><i class="dot transition-dot" />替换前置</span>
      <span><i class="dot required-dot" />保留前置</span>
      <el-tag size="small" type="info">状态与状态包已隐藏</el-tag>
      <el-button v-if="editable" size="small" :type="connecting ? 'warning' : 'primary'" plain @click="toggleConnect">
        {{ connecting ? '取消连线' : '连接活动' }}
      </el-button>
      <small v-if="connecting" class="connect-tip">{{ connectSource ? '请选择目标活动' : '请选择起点活动' }}</small>
    </div>

    <div v-if="editable && visibleEdges.length" class="edge-list">
      <span>已投影依赖</span>
      <el-tag v-for="edge in visibleEdges" :key="edge.semanticKey" closable size="small" @close="$emit('remove-connection', edge)">
        {{ nodeLabel(edge.source) }} → {{ nodeLabel(edge.target) }}
      </el-tag>
    </div>

    <el-empty v-if="!graph.nodes?.length" description="创建活动并加入二级活动包后，这里会形成活动网络" />
    <div v-else class="canvas-stage" :style="{ minHeight: `${stageHeight}px`, width: `${stageWidth}px` }">
      <svg class="edge-layer" :width="stageWidth" :height="stageHeight" aria-label="活动依赖线">
        <defs>
          <marker id="arrow-required" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 Z" fill="#2563eb" />
          </marker>
          <marker id="arrow-transition" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 Z" fill="#f97316" />
          </marker>
        </defs>
        <path
          v-for="edge in renderedEdges"
          :key="edge.id"
          :d="edge.path"
          fill="none"
          :stroke="edge.role === 'transition' ? '#f97316' : '#2563eb'"
          stroke-width="2"
          :stroke-dasharray="edge.role === 'required' ? '6 4' : undefined"
          :marker-end="`url(#arrow-${edge.role})`"
        />
      </svg>

      <section
        v-for="container in containers"
        :key="container.id"
        class="package-container"
        data-container-kind="activity-package"
        :data-package-level="container.level"
        :style="container.style"
      >
        <header>
          <div>
            <strong>{{ container.display_code }} {{ container.name }}</strong>
            <small>{{ container.level === 1 ? '一级活动包' : '二级活动包' }}</small>
          </div>
          <el-button text size="small" @click="toggle(container.id)">
            {{ collapsed.has(container.id) ? '展开' : '折叠' }}
          </el-button>
        </header>
        <div v-if="!collapsed.has(container.id)" class="container-body">
          <article
            v-for="node in nodesByPackage[container.id] || []"
            :key="node.id"
            class="activity-node"
            data-node-kind="activity"
            :data-canonical-id="node.canonical_activity_id"
            :style="node.style"
            :class="{ draggable: editable, 'connect-source': connectSource === node.canonical_activity_id }"
            @pointerdown="beginDrag(node, $event)"
            @click="activateNode(node)"
          >
            <div class="node-title"><span>{{ node.display_code }}</span>{{ node.name }}</div>
            <div class="node-meta">工期 {{ node.duration }} · {{ node.is_target ? '目标活动' : '普通活动' }}</div>
            <div class="node-badges">
              <el-tag v-if="node.seed_preconditions?.length" size="small" type="success">初始前置 {{ node.seed_preconditions.length }}</el-tag>
              <el-tag v-if="node.event_preconditions?.length" size="small" type="warning">事件 {{ node.event_preconditions.length }}</el-tag>
            </div>
          </article>
          <div v-if="!(nodesByPackage[container.id] || []).length" class="empty-package">暂无活动</div>
        </div>
      </section>

      <article
        v-for="node in ungroupedNodes"
        :key="node.id"
        class="activity-node ungrouped"
        data-node-kind="activity"
        :data-canonical-id="node.canonical_activity_id"
        :style="node.style"
        @click="activateNode(node)"
      >
        <div class="node-title"><span>{{ node.display_code }}</span>{{ node.name }}</div>
        <div class="node-meta">未加入活动包 · 工期 {{ node.duration }}</div>
      </article>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'

const props = defineProps({
  graph: { type: Object, default: () => ({ containers: [], nodes: [], edges: [] }) },
  editable: { type: Boolean, default: false },
})
const emit = defineEmits(['select-activity', 'connect-activities', 'remove-connection', 'layout-change'])
const collapsed = reactive(new Set())
const dragLayouts = reactive({})
const connecting = ref(false)
const connectSource = ref(null)
const CARD_W = 190
const CARD_H = 92
const PACKAGE_W = 480
const PACKAGE_H = 230

const containers = computed(() => {
  const roots = (props.graph.containers || []).filter((item) => item.level === 1)
  const children = (props.graph.containers || []).filter((item) => item.level === 2)
  return [...roots, ...children].map((item, index) => {
    const column = index % 2
    const row = Math.floor(index / 2)
    const fallback = { x: 30 + column * 520, y: 30 + row * 270, width: PACKAGE_W, height: PACKAGE_H }
    const layout = { ...fallback, ...(item.layout || {}) }
    return { ...item, layout, style: { left: `${layout.x}px`, top: `${layout.y}px`, width: `${layout.width}px`, height: `${layout.height}px` } }
  })
})
const containerById = computed(() => Object.fromEntries(containers.value.map((item) => [item.id, item])))
const stageWidth = computed(() => Math.max(1100, ...containers.value.map((item) => item.layout.x + item.layout.width + 30)))
const stageHeight = computed(() => Math.max(520, ...containers.value.map((item) => item.layout.y + item.layout.height + 180)))
const positionedNodes = computed(() => (props.graph.nodes || []).map((node, index) => {
  const container = containerById.value[node.package_id]
  if (!container) {
    const layout = { x: 30 + (index % 4) * 220, y: stageHeight.value - 130 }
    return { ...node, layout, style: { left: `${layout.x}px`, top: `${layout.y}px` } }
  }
  const siblings = (props.graph.nodes || []).filter((item) => item.package_id === node.package_id)
  const localIndex = siblings.findIndex((item) => item.id === node.id)
  const local = dragLayouts[node.id] || (node.layout?.x != null ? node.layout : { x: 20 + (localIndex % 2) * 215, y: 66 + Math.floor(localIndex / 2) * 108 })
  const layout = { x: container.layout.x + local.x, y: container.layout.y + local.y }
  return { ...node, layout, style: { left: `${local.x}px`, top: `${local.y}px` } }
}))
const nodesByPackage = computed(() => {
  const groups = {}
  for (const node of positionedNodes.value.filter((item) => item.package_id)) (groups[node.package_id] ||= []).push(node)
  return groups
})
const ungroupedNodes = computed(() => positionedNodes.value.filter((item) => !item.package_id))
const positionById = computed(() => Object.fromEntries(positionedNodes.value.map((item) => [item.id, item.layout])))
const visibleEdges = computed(() => {
  const graphNodes = Object.fromEntries((props.graph.nodes || []).map((item) => [item.id, item]))
  const unique = new Map()
  for (const edge of props.graph.edges || []) {
    const source = graphNodes[edge.source]?.canonical_activity_id
    const target = graphNodes[edge.target]?.canonical_activity_id
    const semanticKey = `${source}:${target}:${edge.state_id}:${edge.relation_role}`
    if (!unique.has(semanticKey)) unique.set(semanticKey, { ...edge, semanticKey })
  }
  return [...unique.values()]
})
const renderedEdges = computed(() => (props.graph.edges || []).flatMap((edge) => {
  const source = positionById.value[edge.source]
  const target = positionById.value[edge.target]
  if (!source || !target) return []
  const x1 = source.x + CARD_W
  const y1 = source.y + CARD_H / 2
  const x2 = target.x
  const y2 = target.y + CARD_H / 2
  const mid = Math.max(40, Math.abs(x2 - x1) / 2)
  // 同一水平线上的三次贝塞尔曲线会产生高度为 0 的边界框，既不利于
  // 浏览器可访问性判断，也容易完全压在节点/容器边框下。给它一个小弧度。
  const bend = Math.abs(y2 - y1) < 1 ? 24 : 0
  return [{ ...edge, role: edge.relation_role || 'required', path: `M${x1},${y1} C${x1 + mid},${y1 - bend} ${x2 - mid},${y2 - bend} ${x2},${y2}` }]
}))

function toggle(id) {
  if (collapsed.has(id)) collapsed.delete(id)
  else collapsed.add(id)
}

function nodeLabel(refId) {
  const node = (props.graph.nodes || []).find((item) => item.id === refId)
  return node ? `${node.display_code} ${node.name}` : '未知活动'
}

function toggleConnect() {
  connecting.value = !connecting.value
  connectSource.value = null
}

function activateNode(node) {
  if (!props.editable || !connecting.value) {
    emit('select-activity', node.canonical_activity_id)
    return
  }
  if (!connectSource.value) {
    connectSource.value = node.canonical_activity_id
    return
  }
  if (connectSource.value === node.canonical_activity_id) return
  emit('connect-activities', { sourceActivityId: connectSource.value, targetActivityId: node.canonical_activity_id })
  connecting.value = false
  connectSource.value = null
}

function beginDrag(node, event) {
  if (!props.editable || !node.package_id || event.button !== 0) return
  const origin = dragLayouts[node.id] || node.layout || { x: 20, y: 66 }
  const startX = event.clientX
  const startY = event.clientY
  let moved = false
  const move = (next) => {
    const dx = next.clientX - startX
    const dy = next.clientY - startY
    moved ||= Math.abs(dx) + Math.abs(dy) > 3
    dragLayouts[node.id] = { x: Math.max(8, origin.x + dx), y: Math.max(58, origin.y + dy) }
  }
  const finish = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', finish)
    if (moved) emit('layout-change', { id: node.id, ...dragLayouts[node.id] })
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', finish, { once: true })
}
</script>

<style scoped>
.canvas-shell { border: 1px solid #dbe4f0; border-radius: 12px; background: #fff; overflow: auto; }
.canvas-legend { position: sticky; left: 0; z-index: 5; display: flex; gap: 18px; align-items: center; padding: 10px 14px; border-bottom: 1px solid #e5eaf2; background: rgba(255,255,255,.96); font-size: 12px; color: #64748b; }
.connect-tip { color: #b45309; }.edge-list { display:flex;gap:7px;align-items:center;flex-wrap:wrap;padding:8px 14px;border-bottom:1px solid #e5eaf2;color:#64748b;font-size:12px; }
.canvas-legend span { display: inline-flex; align-items: center; gap: 6px; }.dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
.activity-dot { background: #0f766e; }.transition-dot { background: #f97316; }.required-dot { background: #2563eb; }
.canvas-stage { position: relative; min-width: 100%; background-image: radial-gradient(#dbe4f0 1px, transparent 1px); background-size: 20px 20px; }
.edge-layer { position: absolute; z-index: 1; left: 0; top: 0; pointer-events: none; overflow: visible; }
.package-container { position: absolute; z-index: 0; border: 2px solid #94a3b8; border-radius: 14px; background: rgba(241,245,249,.76); }
.package-container[data-package-level="1"] { border-color: #64748b; background: rgba(226,232,240,.58); }
.package-container header { height: 54px; display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; border-bottom: 1px solid #cbd5e1; }
.package-container header strong { display: block; font-size: 14px; }.package-container header small { color: #64748b; }.container-body { position: relative; height: calc(100% - 54px); }
.activity-node { position: absolute; z-index: 2; width: 190px; min-height: 92px; padding: 10px 12px; border: 2px solid #0f766e; border-radius: 10px; background: #f0fdfa; box-shadow: 0 5px 14px rgba(15,118,110,.12); cursor: pointer; }
.activity-node:hover { border-color: #0d9488; transform: translateY(-1px); }.activity-node.ungrouped { border-style: dashed; background: #fff; }
.activity-node.draggable { cursor: grab; touch-action: none; }.activity-node.connect-source { outline: 3px solid #f59e0b; }
.node-title { font-weight: 650; color: #134e4a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }.node-title span { margin-right: 6px; color: #0f766e; }
.node-meta { margin-top: 7px; color: #64748b; font-size: 12px; }.node-badges { display: flex; gap: 4px; margin-top: 7px; }.empty-package { padding: 36px; text-align: center; color: #94a3b8; }
</style>
