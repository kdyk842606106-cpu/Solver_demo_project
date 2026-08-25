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
        @layout-change="handleLayout"
        @container-resize="handleResize"
      />
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import NetworkEditorX6Canvas from '../DataManagement/components/NetworkEditorX6Canvas.vue'
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
const x6 = computed(() => plannerGraphToX6(props.graph))
const visibleEdges = computed(() => props.graph.edges || [])

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

function emitLayout(node, position = null, size = null) {
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
