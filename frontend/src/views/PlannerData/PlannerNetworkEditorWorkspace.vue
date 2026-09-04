<template>
  <div class="network-editor planner-network-editor" data-testid="planner-network-editor">
    <div class="filter-strip">
      <el-input v-model="keyword" clearable placeholder="搜索活动或活动包" style="width:240px" />
      <el-select
        v-model="packageFilterIds"
        multiple
        collapse-tags
        clearable
        placeholder="按活动包筛选"
        style="min-width:260px"
      >
        <el-option
          v-for="item in effectiveScenario.activity_packages || []"
          :key="item.id"
          :value="item.id"
          :label="`${item.display_code || '草稿'} · ${item.name}`"
        />
      </el-select>
      <div class="toolbar-controls">
        <el-button :disabled="!selectedActivity" @click="impactVisible = true">影响分析</el-button>
        <el-button @click="$emit('run-validation')">场景校验</el-button>
      </div>
    </div>

    <div class="summary-strip">
      <div class="metric"><span>活动</span><strong>{{ effectiveScenario.activities?.length || 0 }}</strong></div>
      <div class="metric"><span>显示引用</span><strong>{{ projectedGraph.nodes.length }}</strong></div>
      <div class="metric"><span>活动包</span><strong>{{ projectedGraph.containers.length }}</strong></div>
      <div class="metric"><span>依赖</span><strong>{{ projectedGraph.edges.length }}</strong></div>
      <div class="metric danger"><span>阻断</span><strong>{{ validation?.issues?.length || 0 }}</strong></div>
      <el-tag type="info">状态与状态包不作为画布节点</el-tag>
    </div>

    <NetworkEditorWorkbenchFrame
      :resource-pane-collapsed="resourcePaneCollapsed"
      :properties-pane-collapsed="propertiesPaneCollapsed"
      :resource-pane-width="resourcePaneWidth"
      :properties-pane-width="propertiesPaneWidth"
      workspace-test-id="planner-network-workspace-body"
    >
      <template #resource>
        <section class="resource-pane" :class="{ collapsed: resourcePaneCollapsed }">
          <div class="pane-header">
            <span>场景资源</span>
            <div class="pane-header-actions">
              <el-dropdown v-if="!resourcePaneCollapsed" :disabled="!editing" @command="handleCreate">
                <el-button size="small" type="primary">新建</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="root-package">一级活动包</el-dropdown-item>
                    <el-dropdown-item command="child-package">二级活动包</el-dropdown-item>
                    <el-dropdown-item command="activity">活动</el-dropdown-item>
                    <el-dropdown-item command="seed">基础状态</el-dropdown-item>
                    <el-dropdown-item command="resource">容量资源</el-dropdown-item>
                    <el-dropdown-item command="event">外部事件</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button text circle :icon="resourcePaneCollapsed ? ArrowRight : ArrowLeft" @click="resourcePaneCollapsed = !resourcePaneCollapsed" />
            </div>
          </div>
          <div v-if="resourcePaneCollapsed" class="pane-rail">场景资源</div>
          <template v-else>
            <section v-if="drafts.length" class="resource-section draft-section">
              <div class="section-title"><span>编辑草稿</span><el-tag size="small" type="warning">{{ drafts.length }}</el-tag></div>
              <div v-for="(draft, index) in drafts" :key="`${draft.operation}-${index}`" class="draft-row">
                <span>{{ draft.description || operationLabel(draft.operation) }}</span>
                <el-button link type="danger" @click="$emit('remove-draft', index)">撤回</el-button>
              </div>
            </section>

            <section class="resource-section">
              <div class="section-title">活动包与活动</div>
              <el-tree
                :data="resourceTree"
                node-key="id"
                default-expand-all
                highlight-current
                :expand-on-click-node="false"
                @node-click="selectTreeNode"
              >
                <template #default="{ data }">
                  <div class="tree-row">
                    <span>{{ data.label }}</span>
                    <el-tag size="small" :type="data.kind === 'activity' ? 'success' : 'info'">
                      {{ data.kind === 'activity' ? '活动' : data.level === 1 ? '一级包' : '二级包' }}
                    </el-tag>
                  </div>
                </template>
              </el-tree>
            </section>

            <section class="resource-section">
              <div class="section-title">基础状态</div>
              <div v-for="item in baseStates" :key="item.id" class="compact-row"><span>{{ item.name }}</span><el-tag size="small">隐藏事实</el-tag></div>
              <el-empty v-if="!baseStates.length" description="暂无基础状态" :image-size="42" />
            </section>
            <section class="resource-section">
              <div class="section-title">容量资源</div>
              <div v-for="item in effectiveScenario.resources || []" :key="item.id" class="compact-row"><span>{{ item.name }}</span><strong>{{ item.capacity }}</strong></div>
              <el-empty v-if="!effectiveScenario.resources?.length" description="暂无容量资源" :image-size="42" />
            </section>
            <section class="resource-section">
              <div class="section-title">外部事件</div>
              <div v-for="item in effectiveScenario.external_events || []" :key="item.id" class="compact-row"><span>{{ item.name }}</span><strong>T+{{ item.time }}</strong></div>
              <el-empty v-if="!effectiveScenario.external_events?.length" description="暂无外部事件" :image-size="42" />
            </section>
          </template>
          <div v-if="!resourcePaneCollapsed" class="pane-resize-handle resource-resize-handle" @pointerdown="startPaneResize('resource', $event)" />
        </section>
      </template>

      <template #canvas>
        <section class="canvas-pane">
          <PlannerX6ActivityCanvas
            :graph="visibleGraph"
            :editable="editing"
            @select-activity="selectActivity"
            @connect-activities="$emit('connect-activities', $event)"
            @remove-connection="$emit('remove-connection', $event)"
            @layout-change="$emit('layout-change', $event)"
          />
        </section>
      </template>

      <template #properties>
        <section class="properties-pane" :class="{ collapsed: propertiesPaneCollapsed }">
          <div class="pane-header">
            <span>活动属性</span>
            <div class="pane-header-actions">
              <el-button text circle :icon="propertiesPaneCollapsed ? ArrowLeft : ArrowRight" @click="propertiesPaneCollapsed = !propertiesPaneCollapsed" />
            </div>
          </div>
          <div v-if="propertiesPaneCollapsed" class="pane-rail">活动属性</div>
          <template v-else-if="selectedActivity">
            <el-form label-position="top" size="small">
              <el-form-item label="活动名称"><el-input v-model="form.name" :disabled="!editing" @input="syncPropertyActivityName" /></el-form-item>
              <div class="two-column">
                <el-form-item label="工期"><el-input-number v-model="form.duration" :min="1" :disabled="!editing" /></el-form-item>
                <el-form-item label="最多执行"><el-input-number v-model="form.max_instances" :min="1" :disabled="!editing" placeholder="不限" /></el-form-item>
              </div>
              <el-form-item label="所属二级活动包">
                <el-select v-model="form.package_ids" multiple clearable :disabled="!editing" style="width:100%">
                  <el-option v-for="item in childPackages" :key="item.id" :value="item.id" :label="item.name" />
                </el-select>
              </el-form-item>
              <el-tabs v-model="propertyStateTab" class="property-state-tabs">
                <el-tab-pane label="状态转移" name="transition">
                  <PlannerTransitionMatrix
                    :source-state-id="form.transition_state_id"
                    :output-state-id="selectedActivity.output_state_id"
                    :output-state-name="form.output_state_name"
                    :states="effectiveScenario.states || []"
                    :activities="effectiveScenario.activities || []"
                    :legacy-transitions="form.legacy_transitions"
                    :disabled="!editing"
                    compact
                    @update:source-state-id="updatePropertyTransition"
                    @update:output-state-name="updatePropertyOutputName"
                  />
                </el-tab-pane>
                <el-tab-pane label="前置状态" name="required">
                  <PlannerStateBindingSelector
                    v-model="form.required_bindings"
                    :states="effectiveScenario.states || []"
                    :state-packages="effectiveScenario.state_packages || []"
                    :state-package-memberships="effectiveScenario.state_package_memberships || []"
                    :excluded-state-ids="[form.transition_state_id, selectedActivity.output_state_id].filter(Boolean)"
                    :disabled="!editing"
                    compact
                  />
                </el-tab-pane>
              </el-tabs>
              <el-form-item label="容量资源需求">
                <div class="binding-list">
                  <div v-for="item in effectiveScenario.resources || []" :key="item.id" class="quantity-row">
                    <span>{{ item.name }}</span>
                    <el-input-number v-model="form.resource_reqs[item.id]" :min="0" :max="item.capacity" :disabled="!editing" />
                  </div>
                </div>
              </el-form-item>
              <el-form-item label="必须等待的外部事件">
                <el-select v-model="form.event_reqs" multiple clearable :disabled="!editing" style="width:100%">
                  <el-option v-for="item in effectiveScenario.external_events || []" :key="item.id" :value="item.id" :label="`${item.name}（T+${item.time}）`" />
                </el-select>
              </el-form-item>
              <div class="property-actions">
                <el-button @click="impactVisible = true">影响分析</el-button>
                <el-button v-if="editing" type="primary" @click="saveProperties">保存到草稿</el-button>
                <el-button v-if="editing" type="danger" plain @click="$emit('delete-activity', selectedActivity)">删除活动</el-button>
              </div>
            </el-form>
          </template>
          <el-empty v-else description="选择一个活动查看属性" />
          <div v-if="!propertiesPaneCollapsed" class="pane-resize-handle properties-resize-handle" @pointerdown="startPaneResize('properties', $event)" />
        </section>
      </template>

      <template #validation-status>
        <div class="validation-status-strip" :class="validationClass">
          <div class="validation-status-main">
            <strong>{{ validationTitle }}</strong>
            <span>{{ validationSubtitle }}</span>
          </div>
          <div class="validation-status-chips">
            <el-tag :type="validation?.valid ? 'success' : validation ? 'danger' : 'info'">{{ validation?.issues?.length || 0 }} 个问题</el-tag>
          </div>
          <div class="validation-status-actions"><el-button size="small" @click="$emit('run-validation')">重新校验</el-button></div>
        </div>
      </template>

      <template #validation-details>
        <section v-if="validation?.issues?.length" class="validation-pane">
          <el-table :data="validation.issues" size="small" max-height="180">
            <el-table-column prop="code" label="问题代码" width="210" />
            <el-table-column prop="message" label="说明" />
            <el-table-column prop="object_id" label="对象" width="220" />
          </el-table>
        </section>
      </template>
    </NetworkEditorWorkbenchFrame>

    <el-drawer v-model="impactVisible" title="活动影响分析" size="420px">
      <template v-if="impact">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="活动">{{ impact.activity.display_code }} · {{ impact.activity.name }}</el-descriptions-item>
          <el-descriptions-item label="所属包">{{ impact.packages.join('、') || '未归属' }}</el-descriptions-item>
          <el-descriptions-item label="直接前置">{{ impact.preconditions.join('、') || '无' }}</el-descriptions-item>
          <el-descriptions-item label="提供者活动">{{ impact.providers.join('、') || '无' }}</el-descriptions-item>
          <el-descriptions-item label="下游活动">{{ impact.consumers.join('、') || '无' }}</el-descriptions-item>
          <el-descriptions-item label="容量资源">{{ impact.resources.join('、') || '无' }}</el-descriptions-item>
          <el-descriptions-item label="外部事件">{{ impact.events.join('、') || '无' }}</el-descriptions-item>
          <el-descriptions-item label="相关校验问题">{{ impact.issues.length }}</el-descriptions-item>
        </el-descriptions>
      </template>
      <el-empty v-else description="请先选择活动" />
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import NetworkEditorWorkbenchFrame from '../DataManagement/components/NetworkEditorWorkbenchFrame.vue'
import PlannerX6ActivityCanvas from './PlannerX6ActivityCanvas.vue'
import PlannerStateBindingSelector from './PlannerStateBindingSelector.vue'
import PlannerTransitionMatrix from './PlannerTransitionMatrix.vue'
import { activityPreconditions, bindingStateIds, splitActivityRelations } from './plannerStateBindings'

const props = defineProps({
  scenario: { type: Object, default: () => ({}) },
  graph: { type: Object, default: () => ({ containers: [], nodes: [], edges: [] }) },
  editing: { type: Boolean, default: false },
  drafts: { type: Array, default: () => [] },
  validation: { type: Object, default: null },
})
const emit = defineEmits([
  'connect-activities', 'remove-connection', 'layout-change', 'remove-draft',
  'run-validation', 'create-package', 'create-activity', 'create-seed',
  'create-resource', 'create-event', 'update-activity', 'change-memberships',
  'delete-activity',
])

const keyword = ref('')
const packageFilterIds = ref([])
const resourcePaneCollapsed = ref(false)
const propertiesPaneCollapsed = ref(false)
const resourcePaneWidth = ref(280)
const propertiesPaneWidth = ref(520)
const selectedActivityId = ref('')
const impactVisible = ref(false)
const propertyStateTab = ref('transition')
const form = reactive({ name: '', duration: 1, max_instances: null, package_ids: [], transition_state_id: null, transition_dirty: false, legacy_transitions: [], required_bindings: [], output_state_name: '', output_name_customized: false, resource_reqs: {}, event_reqs: [] })
let stopResize = null

const effectiveScenario = computed(() => applyDrafts(props.scenario, props.drafts))
const projectedGraph = computed(() => projectScenario(effectiveScenario.value))
const childPackages = computed(() => (effectiveScenario.value.activity_packages || []).filter((item) => item.level === 2))
const baseStates = computed(() => (effectiveScenario.value.states || []).filter((item) => item.state_kind !== 'activity_output'))
const selectedActivity = computed(() => (effectiveScenario.value.activities || []).find((item) => item.id === selectedActivityId.value) || null)
const visibleGraph = computed(() => filterGraph(projectedGraph.value, effectiveScenario.value, keyword.value, packageFilterIds.value))
const resourceTree = computed(() => buildResourceTree(effectiveScenario.value, keyword.value))
const validationClass = computed(() => props.validation?.valid ? 'is-success' : props.validation ? 'is-danger' : 'is-info')
const validationTitle = computed(() => props.validation ? (props.validation.valid ? '场景校验通过' : '场景存在阻断问题') : '尚未执行场景校验')
const validationSubtitle = computed(() => props.validation?.scenario_hash ? `快照 ${props.validation.scenario_hash.slice(0, 12)}` : '校验只读取已提交场景，不写入数据')
const impact = computed(() => selectedActivity.value ? buildImpact(selectedActivity.value, effectiveScenario.value, props.validation) : null)

watch(selectedActivity, (activity) => {
  if (!activity) return
  const memberships = (effectiveScenario.value.activity_package_memberships || []).filter((item) => item.activity_id === activity.id)
  const relations = splitActivityRelations(activity.preconditions || [])
  propertyStateTab.value = 'transition'
  Object.assign(form, {
    name: activity.name,
    duration: activity.duration,
    max_instances: activity.max_instances ?? null,
    package_ids: memberships.map((item) => item.package_id),
    transition_state_id: relations.transitionStateId,
    transition_dirty: false,
    legacy_transitions: relations.legacyTransitions,
    required_bindings: relations.requiredBindings,
    output_state_name: activity.output_state_name || `${activity.name}完成`,
    output_name_customized: activity.output_name_customized ?? ((activity.output_state_name || `${activity.name}完成`) !== `${activity.name}完成`),
    resource_reqs: { ...(activity.resource_reqs || {}) },
    event_reqs: [...(activity.event_reqs || [])],
  })
}, { immediate: true })

watch(effectiveScenario, (scenario) => {
  if (selectedActivityId.value && !(scenario.activities || []).some((item) => item.id === selectedActivityId.value)) selectedActivityId.value = ''
})

function handleCreate(command) {
  if (command === 'root-package') emit('create-package', 'root')
  else if (command === 'child-package') emit('create-package', 'child')
  else if (command === 'activity') emit('create-activity')
  else if (command === 'seed') emit('create-seed')
  else if (command === 'resource') emit('create-resource')
  else if (command === 'event') emit('create-event')
}

function selectTreeNode(node) { if (node.kind === 'activity') selectActivity(node.activity_id) }
function selectActivity(activityId) { selectedActivityId.value = activityId }

function updatePropertyTransition(stateId) { form.transition_state_id = stateId; form.transition_dirty = true }
function updatePropertyOutputName(name) { form.output_state_name = name; form.output_name_customized = true }
function syncPropertyActivityName(name) { if (!form.output_name_customized) form.output_state_name = `${name || '当前活动'}完成` }

function saveProperties() {
  if (!form.name.trim()) return ElMessage.warning('请填写活动名称')
  if (!form.output_state_name.trim()) return ElMessage.warning('请填写结果状态名称')
  if (form.required_bindings.some((item) => item.binding_type === 'state_package' && !item.covered_state_ids?.length)) return ElMessage.warning('状态包绑定至少需要覆盖一个原子状态')
  const preconditions = activityPreconditions({ transitionStateId: form.transition_state_id, legacyTransitions: form.legacy_transitions, preserveLegacy: form.legacy_transitions.length > 0 && !form.transition_dirty, requiredBindings: form.required_bindings })
  if (new Set(preconditions.map((item) => item.state_id)).size !== preconditions.length) return ElMessage.warning('同一前置状态只能绑定一次')
  const requiredIds = bindingStateIds(form.required_bindings)
  if ([form.transition_state_id, selectedActivity.value.output_state_id].some((id) => id && requiredIds.has(id))) { propertyStateTab.value = 'required'; return ElMessage.warning('前置状态与当前状态转移冲突') }
  const resourceReqs = Object.fromEntries(Object.entries(form.resource_reqs || {}).filter(([, value]) => Number(value) > 0).map(([key, value]) => [key, Number(value)]))
  const payload = { name: form.name.trim(), duration: Number(form.duration), max_instances: form.max_instances || null, preconditions, resource_reqs: resourceReqs, event_reqs: [...form.event_reqs] }
  if (form.output_name_customized) payload.output_state_name = form.output_state_name.trim()
  emit('update-activity', {
    activityId: selectedActivityId.value,
    payload,
  })
  emit('change-memberships', { activityId: selectedActivityId.value, packageIds: [...form.package_ids] })
}
function startPaneResize(side, event) {
  event.preventDefault()
  const startX = event.clientX
  const startWidth = side === 'resource' ? resourcePaneWidth.value : propertiesPaneWidth.value
  const move = (nextEvent) => {
    const delta = nextEvent.clientX - startX
    const next = side === 'resource' ? startWidth + delta : startWidth - delta
    if (side === 'resource') resourcePaneWidth.value = Math.max(220, Math.min(460, next))
    else propertiesPaneWidth.value = Math.max(300, Math.min(560, next))
  }
  const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); document.body.classList.remove('network-editor-pane-resizing'); stopResize = null }
  document.body.classList.add('network-editor-pane-resizing')
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
  stopResize = up
}
onBeforeUnmount(() => stopResize?.())

function operationLabel(operation) {
  return ({ create_package: '新增活动包', update_package: '编辑活动包', delete_package: '删除活动包', create_activity: '新增活动', update_activity: '编辑活动', delete_activity: '删除活动', add_membership: '加入活动包', remove_membership: '移出活动包', update_layout: '调整布局' })[operation] || operation
}

function applyDrafts(source, drafts) {
  const scenario = JSON.parse(JSON.stringify(source || {}))
  for (const [index, draft] of (drafts || []).entries()) {
    const data = JSON.parse(JSON.stringify(draft.payload || {}))
    if (draft.operation === 'create_package') {
      const parent = (scenario.activity_packages || []).find((item) => item.id === data.parent_id)
      scenario.activity_packages ||= []
      scenario.activity_packages.push({ id: draft.client_ref || `draft:package:${index}`, display_code: '草稿', name: data.name, parent_id: data.parent_id || null, level: parent ? 2 : 1, layout: data.layout || {}, sort_order: data.sort_order || 0 })
    } else if (draft.operation === 'update_package') {
      Object.assign((scenario.activity_packages || []).find((item) => item.id === draft.object_id) || {}, data)
    } else if (draft.operation === 'delete_package') {
      scenario.activity_packages = (scenario.activity_packages || []).filter((item) => item.id !== draft.object_id)
      scenario.activity_package_memberships = (scenario.activity_package_memberships || []).filter((item) => item.package_id !== draft.object_id)
    } else if (draft.operation === 'create_activity') {
      const id = draft.client_ref || `draft:activity:${index}`
      scenario.activities ||= []
      scenario.states ||= []
      const outputName = data.output_state_name || `${data.name}完成`
      scenario.activities.push({ id, display_code: '草稿', output_state_id: `${id}:output`, output_state_name: outputName, is_active: true, ...data })
      scenario.states.push({ id: `${id}:output`, name: outputName, state_kind: 'activity_output', source_activity_id: id })
    } else if (draft.operation === 'update_activity') {
      const activity = (scenario.activities || []).find((item) => item.id === draft.object_id)
      if (activity) {
        Object.assign(activity, data)
        const output = (scenario.states || []).find((item) => item.id === activity.output_state_id)
        if (output && data.output_state_name) output.name = data.output_state_name
      }
    } else if (draft.operation === 'delete_activity') {
      scenario.activities = (scenario.activities || []).filter((item) => item.id !== draft.object_id)
      scenario.activity_package_memberships = (scenario.activity_package_memberships || []).filter((item) => item.activity_id !== draft.object_id)
    } else if (draft.operation === 'add_membership') {
      scenario.activity_package_memberships ||= []
      if (!scenario.activity_package_memberships.some((item) => item.package_id === data.package_id && item.activity_id === data.activity_id)) scenario.activity_package_memberships.push({ id: draft.client_ref || `draft:membership:${index}`, package_id: data.package_id, activity_id: data.activity_id, sort_order: data.sort_order || 0, layout: {} })
    } else if (draft.operation === 'remove_membership') {
      scenario.activity_package_memberships = (scenario.activity_package_memberships || []).filter((item) => item.id !== draft.object_id)
    } else if (draft.operation === 'create_seed_state') {
      scenario.states ||= []; scenario.states.push({ id: draft.client_ref || `draft:state:${index}`, state_kind: 'seed', ...data })
    } else if (draft.operation === 'create_resource') {
      scenario.resources ||= []; scenario.resources.push({ id: draft.client_ref || `draft:resource:${index}`, ...data })
    } else if (draft.operation === 'create_event') {
      scenario.external_events ||= []; scenario.external_events.push({ id: draft.client_ref || `draft:event:${index}`, ...data })
    } else if (draft.operation === 'update_event') {
      Object.assign((scenario.external_events || []).find((item) => item.id === draft.object_id) || {}, data)
    } else if (draft.operation === 'update_layout') {
      const refs = new Map((scenario.activity_package_memberships || []).map((item) => [item.id, item]))
      const packages = new Map((scenario.activity_packages || []).map((item) => [item.id, item]))
      for (const item of data.activity_refs || []) if (refs.has(item.id)) refs.get(item.id).layout = { ...(refs.get(item.id).layout || {}), ...item }
      for (const item of data.package_containers || []) if (packages.has(item.id)) packages.get(item.id).layout = { ...(packages.get(item.id).layout || {}), ...item }
    }
  }
  return scenario
}

function projectScenario(scenario) {
  const activities = new Map((scenario.activities || []).map((item) => [item.id, item]))
  const membershipsByActivity = new Map()
  for (const item of scenario.activity_package_memberships || []) {
    if (!membershipsByActivity.has(item.activity_id)) membershipsByActivity.set(item.activity_id, [])
    membershipsByActivity.get(item.activity_id).push(item)
  }
  const nodes = []
  const refs = new Map()
  for (const activity of activities.values()) {
    const memberships = membershipsByActivity.get(activity.id) || [null]
    refs.set(activity.id, [])
    for (const membership of memberships) {
      const id = membership?.id || `activity-body:${activity.id}`
      refs.get(activity.id).push(id)
      nodes.push({ id, kind: 'activity', canonical_activity_id: activity.id, package_id: membership?.package_id || null, display_code: activity.display_code, name: activity.name, duration: activity.duration, layout: membership?.layout || {}, seed_preconditions: [], event_preconditions: [...(activity.event_reqs || [])] })
    }
  }
  const producers = new Map()
  for (const activity of activities.values()) for (const stateId of [activity.output_state_id, ...(activity.additional_output_state_ids || [])]) {
    if (!producers.has(stateId)) producers.set(stateId, [])
    producers.get(stateId).push(activity.id)
  }
  const initial = new Set(scenario.initial_state_ids || [])
  const eventStates = new Set((scenario.external_events || []).flatMap((item) => item.add_state_ids || []))
  const nodeById = new Map(nodes.map((item) => [item.id, item]))
  const edges = []
  for (const consumer of activities.values()) for (const relation of consumer.preconditions || []) {
    if (initial.has(relation.state_id)) for (const ref of refs.get(consumer.id) || []) nodeById.get(ref)?.seed_preconditions.push(relation.state_id)
    if (eventStates.has(relation.state_id)) continue
    for (const providerId of producers.get(relation.state_id) || []) for (const source of refs.get(providerId) || []) for (const target of refs.get(consumer.id) || []) edges.push({ id: `dependency:${source}:${target}:${relation.state_id}`, kind: 'activity_dependency', source, target, source_activity_id: providerId, target_activity_id: consumer.id, state_id: relation.state_id, relation_role: relation.relation_role || 'required', provider_semantics: 'OR' })
  }
  return { scenario_id: scenario.id, containers: scenario.activity_packages || [], nodes, edges, summary: { state_node_count: 0 } }
}

function filterGraph(graph, scenario, query, packageIds) {
  const text = query.trim().toLowerCase()
  const packages = new Map((scenario.activity_packages || []).map((item) => [item.id, item]))
  const selected = new Set(packageIds || [])
  const inSelectedPackage = (packageId) => {
    if (!selected.size) return true
    let current = packages.get(packageId)
    const seen = new Set()
    while (current && !seen.has(current.id)) { if (selected.has(current.id)) return true; seen.add(current.id); current = packages.get(current.parent_id) }
    return false
  }
  const packageMatches = (packageId) => {
    let current = packages.get(packageId)
    const seen = new Set()
    while (current && !seen.has(current.id)) {
      if (`${current.display_code || ''} ${current.name || ''}`.toLowerCase().includes(text)) return true
      seen.add(current.id)
      current = packages.get(current.parent_id)
    }
    return false
  }
  const nodes = graph.nodes.filter((item) => inSelectedPackage(item.package_id) && (!text || `${item.display_code} ${item.name}`.toLowerCase().includes(text) || packageMatches(item.package_id)))
  const ids = new Set(nodes.map((item) => item.id))
  const usedPackages = new Set(nodes.map((item) => item.package_id).filter(Boolean))
  for (const id of [...usedPackages]) { let current = packages.get(id); while (current?.parent_id) { usedPackages.add(current.parent_id); current = packages.get(current.parent_id) } }
  return { ...graph, nodes, containers: graph.containers.filter((item) => usedPackages.has(item.id) || (!text && !selected.size)), edges: graph.edges.filter((item) => ids.has(item.source) && ids.has(item.target)) }
}

function buildResourceTree(scenario, query) {
  const text = query.trim().toLowerCase()
  const packages = scenario.activity_packages || []
  const activities = new Map((scenario.activities || []).map((item) => [item.id, item]))
  const memberships = scenario.activity_package_memberships || []
  const children = (parentId) => packages.filter((item) => item.parent_id === parentId).map((item) => packageNode(item))
  const packageNode = (item) => ({ id: item.id, kind: 'package', level: item.level, label: `${item.display_code || '草稿'} · ${item.name}`, children: item.level === 1 ? children(item.id) : memberships.filter((member) => member.package_id === item.id).map((member) => activityNode(activities.get(member.activity_id))).filter(Boolean) })
  const activityNode = (item) => item && ({ id: `tree:${item.id}`, kind: 'activity', activity_id: item.id, label: `${item.display_code || '草稿'} · ${item.name}` })
  const assigned = new Set(memberships.map((item) => item.activity_id))
  const roots = packages.filter((item) => !item.parent_id).map(packageNode)
  const unassigned = [...activities.values()].filter((item) => !assigned.has(item.id)).map(activityNode)
  if (unassigned.length) roots.push({ id: 'unassigned', kind: 'package', level: 2, label: '未归属活动', children: unassigned })
  if (!text) return roots
  const keep = (node) => { if (node.label.toLowerCase().includes(text)) return node; const childrenKept = (node.children || []).map(keep).filter(Boolean); return childrenKept.length ? { ...node, children: childrenKept } : null }
  return roots.map(keep).filter(Boolean)
}

function buildImpact(activity, scenario, validation) {
  const states = new Map((scenario.states || []).map((item) => [item.id, item.name]))
  const activities = scenario.activities || []
  const outputs = new Set([activity.output_state_id, ...(activity.additional_output_state_ids || [])])
  const providers = new Set()
  for (const relation of activity.preconditions || []) for (const candidate of activities) if ([candidate.output_state_id, ...(candidate.additional_output_state_ids || [])].includes(relation.state_id)) providers.add(candidate.name)
  const consumers = activities.filter((candidate) => (candidate.preconditions || []).some((item) => outputs.has(item.state_id))).map((item) => item.name)
  const packageIds = new Set((scenario.activity_package_memberships || []).filter((item) => item.activity_id === activity.id).map((item) => item.package_id))
  const packages = (scenario.activity_packages || []).filter((item) => packageIds.has(item.id)).map((item) => item.name)
  const resourceById = new Map((scenario.resources || []).map((item) => [item.id, item.name]))
  const eventById = new Map((scenario.external_events || []).map((item) => [item.id, item.name]))
  return { activity, packages, preconditions: (activity.preconditions || []).map((item) => `${states.get(item.state_id) || item.state_id}（${item.relation_role === 'transition' ? '替换' : '保留'}）`), providers: [...providers], consumers, resources: Object.entries(activity.resource_reqs || {}).map(([id, count]) => `${resourceById.get(id) || id} × ${count}`), events: (activity.event_reqs || []).map((id) => eventById.get(id) || id), issues: (validation?.issues || []).filter((item) => item.object_id === activity.id) }
}
</script>

<style scoped>
.planner-network-editor{min-width:0}.resource-section{padding:10px 0;border-top:1px solid #ebeef5}.resource-section:first-of-type{border-top:0}.section-title{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;font-size:13px;font-weight:700}.draft-section{padding-top:0}.draft-row,.compact-row,.tree-row{display:flex;align-items:center;justify-content:space-between;gap:8px}.draft-row{padding:5px 0;font-size:12px}.draft-row span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.compact-row{padding:5px 2px;font-size:12px}.tree-row{width:100%;padding-right:6px}.two-column{display:grid;grid-template-columns:1fr 1fr;gap:8px}.binding-list{display:grid;width:100%;gap:8px}.binding-row{display:grid;gap:6px}.quantity-row{display:grid;grid-template-columns:1fr 130px;align-items:center;gap:8px}.property-state-tabs{width:100%;margin-bottom:12px}.property-actions{display:flex;flex-wrap:wrap;gap:8px}.canvas-pane :deep(.planner-x6-shell){height:100%}.canvas-pane :deep(.canvas-viewport){height:calc(100% - 52px);min-height:520px}.canvas-pane :deep(.x6-network-canvas){min-height:520px}
</style>
