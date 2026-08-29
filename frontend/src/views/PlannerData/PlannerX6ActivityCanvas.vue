<template>
  <section class="planner-x6-shell" data-testid="planner-activity-x6-canvas">
    <header class="canvas-toolbar">
      <div class="legend">
        <span><i class="dot activity-dot" />活动节点</span>
        <span><i class="line transition-line" />替换前置</span>
        <span><i class="line required-line" />保留前置</span>
        <el-tag size="small" type="info">状态与状态包已隐藏</el-tag>
      </div>
      <div class="tools">
        <el-button
          size="small"
          :loading="arranging"
          :disabled="!editable"
          data-testid="planner-network-auto-arrange"
          @click="autoArrange"
        >
          自动整理
        </el-button>
        <el-button-group>
          <el-button size="small" aria-label="缩小画布" @click="changeZoom(-0.1)">−</el-button>
          <el-button size="small" aria-label="重置画布缩放" @click="resetZoom">{{ Math.round(zoom * 100) }}%</el-button>
          <el-button size="small" aria-label="放大画布" @click="changeZoom(0.1)">＋</el-button>
        </el-button-group>
        <el-button v-if="editable" size="small" :type="connecting ? 'warning' : 'primary'" plain @click="toggleConnect">
          {{ connecting ? '取消连线' : '连接活动' }}
        </el-button>
      </div>
    </header>

    <div v-if="editable && visibleEdges.length" class="edge-list">
      <span>已投影依赖</span>
      <el-tag v-for="edge in visibleEdges" :key="edge.id" closable size="small" @close="$emit('remove-connection', edge)">
        {{ nodeLabel(edge.source) }} → {{ nodeLabel(edge.target) }}
      </el-tag>
    </div>

    <el-alert
      v-if="connecting"
      :title="connectSource ? '请选择目标活动' : '请选择起点活动'"
      type="warning"
      :closable="false"
      class="connect-alert"
    />
    <el-empty v-if="!graph.nodes?.length" description="创建活动并加入二级活动包后，这里会形成活动网络" />
    <div v-else class="canvas-viewport">
      <NetworkEditorX6Canvas
        :state-nodes="[]"
        :activity-nodes="x6.activityNodes"
        :edges="x6.edges"
        :selected-activity-graph-id="selectedGraphId"
        :is-edit-mode="editable"
        :can-mutate="editable"
        :show-edit-actions="false"
        :canvas-zoom="zoom"
        :activity-scope-ids="x6.rootPackageIds"
        :activity-depth="0"
        :viewport-reset-token="viewportToken"
        @select-activity="handleSelect"
        @toggle-activity-expansion="togglePackage"
        @layout-change="handleLayout"
        @container-resize="handleResize"
      />
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import NetworkEditorX6Canvas from '../DataManagement/components/NetworkEditorX6Canvas.vue'
import { layoutNestedContainerGraph } from '../DataManagement/networkEditorAutoLayout'
import { plannerGraphToX6 } from './plannerPresentation'

const props = defineProps({
  graph: { type: Object, default: () => ({ containers: [], nodes: [], edges: [] }) },
  editable: { type: Boolean, default: false },
})
const emit = defineEmits(['select-activity', 'connect-activities', 'remove-connection', 'layout-change'])
const zoom = ref(1)
const viewportToken = ref(0)
const connecting = ref(false)
const connectSource = ref(null)
const selectedGraphId = ref(null)
const arranging = ref(false)
const collapsedPackageIds = ref(new Set())
const layoutOverrides = ref(new Map())
const baseX6 = computed(() => plannerGraphToX6(props.graph, {
  collapsedPackageIds: [...collapsedPackageIds.value],
}))
const x6 = computed(() => ({
  ...baseX6.value,
  activityNodes: baseX6.value.activityNodes.map((node) => {
    const override = layoutOverrides.value.get(String(node._planner_id))
    if (!override) return node
    return {
      ...node,
      metadata_json: {
        ...(node.metadata_json || {}),
        ...(override.x != null && override.y != null
          ? { _network_editor_layout: { x: override.x, y: override.y } }
          : {}),
        ...(override.width != null && override.height != null
          ? { _network_editor_container: { width: override.width, height: override.height } }
          : {}),
      },
      _network_editor_has_container_draft: node._planner_kind === 'package',
    }
  }),
}))
const visibleEdges = computed(() => props.graph.edges || [])

watch(
  () => props.graph.containers,
  (containers = []) => {
    const valid = new Set(containers.map((item) => String(item.id)))
    collapsedPackageIds.value = new Set(
      [...collapsedPackageIds.value].filter((id) => valid.has(String(id))),
    )
  },
  { deep: true },
)

watch(
  () => props.editable,
  (editable) => {
    if (!editable) layoutOverrides.value = new Map()
  },
)

function changeZoom(delta) {
  zoom.value = Math.min(1.6, Math.max(0.65, Number((zoom.value + delta).toFixed(2))))
}

function resetZoom() {
  zoom.value = 1
  viewportToken.value += 1
}

function toggleConnect() {
  connecting.value = !connecting.value
  connectSource.value = null
}

function togglePackage(node) {
  const id = String(node?._planner_id || node?.id || '')
  if (!id) return
  const next = new Set(collapsedPackageIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  collapsedPackageIds.value = next
  if (selectedGraphId.value && !x6.value.activityNodes.some((item) => item.id === selectedGraphId.value)) {
    selectedGraphId.value = null
  }
  viewportToken.value += 1
}

async function autoArrange() {
  if (!props.editable || arranging.value) return
  arranging.value = true
  try {
    const nodes = x6.value.activityNodes
    const expandedPackageIds = nodes
      .filter((node) => node.activity_type === 'activity_package' && nodes.some((candidate) => (
        candidate.id !== node.id && (candidate.parent_activity_node_ids || []).includes(node.activity_node_id)
      )))
      .map((node) => String(node.id))
    const plan = await layoutNestedContainerGraph({
      activityNodes: nodes,
      edges: x6.value.edges,
      expandedActivityContainerIds: expandedPackageIds,
      activityDirection: 'RIGHT',
    })
    const updates = new Map()
    for (const node of nodes) {
      const position = plan.activityPositions?.get(String(node.id))
      if (!position) continue
      updates.set(String(node.id), {
        kind: node._planner_kind,
        id: node._planner_id,
        x: Math.round(position.x),
        y: Math.round(position.y),
      })
    }
    for (const [id, size] of plan.containerSizes || []) {
      const node = nodes.find((item) => String(item.id) === String(id))
      if (!node?._planner_id) continue
      updates.set(String(id), {
        ...(updates.get(String(id)) || { kind: 'package', id: node._planner_id }),
        width: Math.round(size.width),
        height: Math.round(size.height),
      })
    }
    if (!updates.size) {
      ElMessage.info('当前没有可整理节点')
      return
    }
    const values = [...updates.values()]
    applyLayoutOverrides(values)
    emit('layout-change', { reason: 'auto-arrange', updates: values })
    viewportToken.value += 1
  } catch (error) {
    console.warn('Planner activity network auto layout failed.', error)
    ElMessage.error('自动整理失败')
  } finally {
    arranging.value = false
  }
}

function handleSelect({ node }) {
  selectedGraphId.value = node.id
  const activityId = node.canonical_activity_id
  if (!activityId) return
  if (!props.editable || !connecting.value) {
    emit('select-activity', activityId)
    return
  }
  if (!connectSource.value) {
    connectSource.value = activityId
    return
  }
  if (connectSource.value === activityId) return
  emit('connect-activities', { sourceActivityId: connectSource.value, targetActivityId: activityId })
  connecting.value = false
  connectSource.value = null
}

function layoutPayload(node, position = null, size = null) {
  if (!node?._planner_id) return
  const payload = {
    kind: node._planner_kind,
    id: node._planner_id,
    ...(size || {}),
  }
  if (Number.isFinite(Number(position?.x)) && Number.isFinite(Number(position?.y))) {
    payload.x = Number(position.x)
    payload.y = Number(position.y)
  }
  return payload
}

function applyLayoutOverrides(updates) {
  const next = new Map(layoutOverrides.value)
  for (const update of updates || []) {
    if (!update?.id) continue
    next.set(String(update.id), { ...(next.get(String(update.id)) || {}), ...update })
  }
  layoutOverrides.value = next
}

function emitLayout(node, position = null, size = null) {
  const payload = layoutPayload(node, position, size)
  if (!payload) return
  applyLayoutOverrides([payload])
  emit('layout-change', payload)
}

function handleLayout(change) {
  const updates = change.updates?.length ? change.updates : [change]
  updates.forEach((item) => emitLayout(item.node, item.position))
}

function handleResize(change) {
  emitLayout(change.node, null, change.size)
}

function nodeLabel(graphId) {
  const node = (props.graph.nodes || []).find((item) => item.id === graphId)
  return node ? `${node.display_code} ${node.name}` : '未知活动'
}
</script>

<style scoped>
.planner-x6-shell{overflow:hidden;border:1px solid #dbe4f0;border-radius:12px;background:#fff}.canvas-toolbar{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:10px 14px;border-bottom:1px solid #e5eaf2;background:#fff}.legend,.tools{display:flex;align-items:center;gap:14px;flex-wrap:wrap}.legend{font-size:12px;color:#64748b}.legend span{display:inline-flex;align-items:center;gap:6px}.dot{display:inline-block;width:9px;height:9px;border-radius:50%}.activity-dot{background:#0f766e}.line{display:inline-block;width:20px;border-top:2px solid}.transition-line{border-color:#f97316}.required-line{border-color:#2563eb;border-top-style:dashed}.edge-list{display:flex;align-items:center;gap:7px;flex-wrap:wrap;padding:8px 14px;border-bottom:1px solid #e5eaf2;color:#64748b;font-size:12px}.connect-alert{margin:10px 12px 0}.canvas-viewport{min-height:640px;overflow:auto;background:#f8fafc}.canvas-viewport :deep(.x6-network-canvas){min-height:640px}
</style>
