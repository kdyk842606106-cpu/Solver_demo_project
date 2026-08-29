<template>
  <div class="solve-workspace">
    <section class="solve-hero">
      <div>
        <p class="eyebrow">IMMUTABLE SHARED INPUT</p>
        <h1>多引擎求解</h1>
        <p>沿用原求解工作台的甘特图、活动网络和指标视图，输入统一切换为 Planner 场景快照。</p>
      </div>
      <el-tag :type="capabilities.planner_available ? 'success' : 'danger'">
        {{ capabilities.planner_available ? 'Planner 已连接' : 'Planner 未连接' }}
      </el-tag>
    </section>

    <section class="control-card">
      <el-form label-position="top" class="control-grid">
        <el-form-item label="场景">
          <el-select v-model="form.scenario_id" filterable style="width:100%" @change="loadScenario">
            <el-option v-for="item in scenarios" :key="item.id" :value="item.id" :label="`${item.display_code} · ${item.name}`" />
          </el-select>
        </el-form-item>
        <el-form-item label="运行方式">
          <el-select v-model="form.engine" style="width:100%">
            <el-option label="全部对比" value="ALL" />
            <el-option label="旧引擎" value="LEGACY" />
            <el-option label="Anytime A*" value="ASTAR" />
            <el-option label="遗传算法 GA" value="GA" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间预算（秒）">
          <el-input-number v-model="form.budget.time_limit_seconds" :min="0.1" :max="120" :step="0.5" style="width:100%" />
        </el-form-item>
        <el-form-item label="随机种子">
          <el-input-number v-model="form.seed" style="width:100%" />
        </el-form-item>
        <el-form-item label="当前状态" class="state-control">
          <el-tree-select
            v-model="form.current_state_node_ids"
            :data="currentStateTreeOptions"
            :props="stateTreeProps"
            node-key="id"
            value-key="id"
            multiple
            show-checkbox
            check-on-click-node
            default-expand-all
            :render-after-expand="false"
            :teleported="false"
            filterable
            collapse-tags
            :max-collapse-tags="4"
            placeholder="选择一级包、二级包或原子状态"
            data-testid="current-state-select"
            style="width:100%"
          />
        </el-form-item>
        <el-form-item label="目标状态" class="state-control">
          <el-tree-select
            v-model="form.target_state_node_ids"
            :data="targetStateTreeOptions"
            :props="stateTreeProps"
            node-key="id"
            value-key="id"
            multiple
            show-checkbox
            check-on-click-node
            default-expand-all
            :render-after-expand="false"
            :teleported="false"
            filterable
            collapse-tags
            :max-collapse-tags="4"
            placeholder="选择一级包、二级包或单个状态"
            data-testid="target-state-select"
            style="width:100%"
          />
        </el-form-item>
        <el-form-item label="旧引擎优化目标" class="objective-control">
          <div class="objective-editor" data-testid="legacy-objectives">
            <div v-for="(objective, index) in form.objectives" :key="`${objective.type}:${index}`" class="objective-row">
              <el-select v-model="objective.type" style="flex:1">
                <el-option v-for="item in objectiveOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <el-input-number v-model="objective.weight" :min="0.001" :step="0.25" controls-position="right" style="width:130px" />
              <el-button text type="danger" :disabled="form.objectives.length === 1" @click="removeObjective(index)">删除</el-button>
            </div>
            <div class="objective-hint">
              <span>权重仅由旧引擎的 CP-SAT Scheduler 使用；A*、GA 保持各自原生优化。</span>
              <el-button link type="primary" @click="addObjective">添加目标</el-button>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <el-alert v-if="invalidSuggestedStateLabels.length" type="error" :closable="false" show-icon class="selection-alert" :title="`建议状态已失效：${invalidSuggestedStateLabels.join('、')}`" />
      <el-alert v-else-if="selectedForbiddenTargetLabels.length" type="error" :closable="false" show-icon class="selection-alert" :title="`禁止状态不能作为目标：${selectedForbiddenTargetLabels.join('、')}`" />
      <div class="selection-summary" data-testid="state-selection-summary">
        <span>当前状态 <strong>{{ stateCounts.current }}</strong></span>
        <span>目标状态 <strong>{{ stateCounts.target }}</strong></span>
        <span>已满足目标 <strong>{{ stateCounts.satisfied }}</strong></span>
        <span>尚需实现 <strong>{{ stateCounts.outstanding }}</strong></span>
        <el-button link type="primary" :disabled="!form.scenario_id" @click="restoreSuggestions">恢复建议值</el-button>
      </div>
      <div class="run-actions">
        <div><span>资源模型</span><strong>容量汇总（不分配具体资源实例）</strong></div>
        <el-button type="primary" size="large" :disabled="!canSolve" :loading="running" @click="solve">开始求解</el-button>
      </div>
    </section>

    <el-empty v-if="!run" description="选择场景并启动求解" />
    <template v-else>
      <section class="run-summary">
        <div><span>运行状态</span><strong>{{ run.status }}</strong></div>
        <div><span>场景快照</span><code>{{ run.scenario_hash?.slice(0, 16) }}</code></div>
        <div><span>输入共享</span><strong>{{ run.result?.engines_share_mutable_state === false ? '隔离且一致' : '-' }}</strong></div>
        <div><span>当前 / 目标</span><strong>{{ run.request?.current_state_ids?.length || 0 }} / {{ run.request?.target_state_ids?.length || 0 }}</strong></div>
        <div><span>已满足 / 待实现</span><strong>{{ runStateCounts.satisfied }} / {{ runStateCounts.outstanding }}</strong></div>
        <div><span>场景版本</span><strong>r{{ run.request?.expected_revision || '-' }}</strong></div>
        <div><span>优化目标</span><strong>{{ run.request?.objectives?.length || 1 }}</strong></div>
      </section>

      <section class="comparison-card">
        <header class="section-title"><div><h2>引擎结果对比</h2><p>同一不可变快照、同一 Validator 口径。</p></div></header>
        <el-table :data="engineRows" size="small" row-key="engine">
          <el-table-column prop="label" label="引擎" min-width="150" />
          <el-table-column label="状态" width="130"><template #default="{ row }"><el-tag size="small" :type="row.pathCount ? 'success' : 'danger'">{{ row.status }}</el-tag></template></el-table-column>
          <el-table-column prop="pathCount" label="合法方案" width="100" />
          <el-table-column prop="makespan" label="最短完工" width="100" />
          <el-table-column prop="executionCount" label="活动数" width="90" />
          <el-table-column prop="elapsed" label="耗时（秒）" width="120" />
          <el-table-column label="统一校验" width="110"><template #default="{ row }"><el-tag v-if="row.validator" size="small" type="success">{{ row.validator }}</el-tag><span v-else>-</span></template></el-table-column>
          <el-table-column label="查看" width="90"><template #default="{ row }"><el-button link type="primary" @click="activeEngine = row.engine">详情</el-button></template></el-table-column>
        </el-table>
      </section>

      <section class="result-card">
        <header class="result-header">
          <div><p class="eyebrow dark">SOLUTION WORKBENCH</p><h2>{{ engineLabel(activeEngine) }} · 方案详情</h2></div>
          <el-radio-group v-model="activeEngine" size="small">
            <el-radio-button v-for="item in engineRows" :key="item.engine" :value="item.engine">{{ item.label }}</el-radio-button>
          </el-radio-group>
        </header>

        <el-alert v-if="!activePresentation.path" :title="activePresentation.result?.error || activePresentation.result?.diagnosis?.error_message || '未找到合法方案'" type="error" :closable="false" show-icon />
        <template v-else>
          <div class="metric-strip">
            <div><span>总工期</span><strong>{{ activePresentation.makespan }}</strong></div>
            <div><span>活动数</span><strong>{{ activePresentation.tasks.length }}</strong></div>
            <div><span>资源峰值</span><strong>{{ activePresentation.resourcePeak }}</strong></div>
            <div><span>Validator</span><strong>{{ activePresentation.path.validator_status }}</strong></div>
          </div>

          <el-tabs v-model="activeResultTab" class="result-tabs">
            <el-tab-pane label="甘特图" name="gantt">
              <GanttChart :tasks="activePresentation.tasks" :makespan="activePresentation.makespan" :critical-path="activePresentation.criticalPath" time-mode="minute" />
            </el-tab-pane>
            <el-tab-pane label="活动网络图" name="network">
              <ActivityNetworkBoard :tasks="activePresentation.tasks" :makespan="activePresentation.makespan" :critical-path="activePresentation.criticalPath" />
            </el-tab-pane>
            <el-tab-pane label="执行明细" name="detail">
              <el-table :data="activePresentation.tasks" size="small" stripe>
                <el-table-column prop="step_order" label="#" width="55" />
                <el-table-column prop="op_code" label="活动编号" width="120" />
                <el-table-column prop="op_name" label="活动" min-width="180" />
                <el-table-column prop="start_min" label="开始" width="85" />
                <el-table-column prop="end_min" label="结束" width="85" />
                <el-table-column prop="duration_min" label="工期" width="85" />
                <el-table-column label="资源" min-width="180"><template #default="{ row }">{{ resourceLabel(row.resources) || '-' }}</template></el-table-column>
              </el-table>
            </el-tab-pane>
            <el-tab-pane label="求解指标" name="metrics">
              <el-descriptions :column="3" border>
                <el-descriptions-item label="执行管线">{{ activePresentation.result?.engine_pipeline || '-' }}</el-descriptions-item>
                <el-descriptions-item label="实际优化目标" :span="2">{{ objectiveSummary(activePresentation.result?.applied_objectives) }}</el-descriptions-item>
                <el-descriptions-item v-for="item in metricRows" :key="item.key" :label="item.label">{{ item.value }}</el-descriptions-item>
              </el-descriptions>
            </el-tab-pane>
          </el-tabs>
        </template>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import GanttChart from '../../components/GanttChart.vue'
import ActivityNetworkBoard from '../../components/ActivityNetworkBoard.vue'
import { createPlannerRun, getPlannerCapabilities, getPlannerScenario, listPlannerScenarios } from '../../api/planner'
import { plannerPathToTasks } from '../PlannerData/plannerPresentation'

const scenarios = ref([])
const capabilities = ref({ planner_available: false })
const scenarioDetails = ref({ revision: 0, scenario: {} })
const running = ref(false)
const run = ref(null)
const activeEngine = ref('ASTAR')
const activeResultTab = ref('gantt')
const suggestedStates = reactive({ current: [], target: [] })
const form = reactive({ scenario_id: '', expected_revision: 0, current_state_node_ids: [], target_state_node_ids: [], engine: 'ALL', seed: 42, budget: { time_limit_seconds: 5, transition_limit: 20000, max_solutions: 10 }, objectives: [{ type: 'minimize_makespan', weight: 1 }] })
const objectiveOptions = [
  { value: 'minimize_makespan', label: '最短总工期' },
  { value: 'minimize_activity_group_span', label: '最小活动包跨度' },
  { value: 'minimize_activity_group_gaps', label: '最小活动包间隙' },
  { value: 'minimize_activity_group_interruptions', label: '最少活动包打断' },
  { value: 'minimize_state_group_span', label: '最小状态包跨度' },
  { value: 'minimize_state_group_gaps', label: '最小状态包间隙' },
  { value: 'minimize_state_group_interruptions', label: '最少状态包打断' },
]
const results = computed(() => run.value?.result?.results || {})
const stateTreeProps = { value: 'id', label: 'label', children: 'children', disabled: 'disabled' }
const stateTreeIndex = computed(() => buildStateTreeIndex(scenarioDetails.value.scenario || {}))
const currentStateTreeOptions = computed(() => buildStateTree(stateTreeIndex.value, false))
const targetStateTreeOptions = computed(() => buildStateTree(stateTreeIndex.value, true))
const currentStateIds = computed(() => expandSelectedStates(form.current_state_node_ids, stateTreeIndex.value, false))
const targetStateIds = computed(() => expandSelectedStates(form.target_state_node_ids, stateTreeIndex.value, true))
const knownStateIds = computed(() => new Set(stateTreeIndex.value.states.keys()))
const invalidSuggestedStateLabels = computed(() => [...new Set([...suggestedStates.current, ...suggestedStates.target].filter((id) => !knownStateIds.value.has(id)))])
const selectedForbiddenTargetLabels = computed(() => {
  const forbidden = stateTreeIndex.value.forbidden
  return selectedLeafStateIds(form.target_state_node_ids, stateTreeIndex.value)
    .filter((stateId) => forbidden.has(stateId))
    .map((stateId) => stateTreeIndex.value.states.get(stateId)?.name || stateId)
})
const stateCounts = computed(() => selectionCounts(currentStateIds.value, targetStateIds.value))
const runStateCounts = computed(() => selectionCounts(run.value?.request?.current_state_ids || [], run.value?.request?.target_state_ids || []))
const canSolve = computed(() => Boolean(form.scenario_id && capabilities.value.planner_available && currentStateIds.value.length && targetStateIds.value.length && !invalidSuggestedStateLabels.value.length && !selectedForbiddenTargetLabels.value.length))

const presentations = computed(() => Object.fromEntries(Object.entries(results.value).map(([engine, result]) => {
  const path = result.paths?.[0] || null
  const tasks = path ? plannerPathToTasks(path, scenarioDetails.value.scenario || {}) : []
  const makespan = Number(path?.metrics?.makespan ?? Math.max(0, ...tasks.map((item) => item.end_min)))
  return [engine, { engine, result, path, tasks, makespan, criticalPath: tasks.map((item) => item.op_code), resourcePeak: (path?.metrics?.resource_peak || []).reduce((total, item) => total + Number(item?.[1] || 0), 0) }]
})))

const engineRows = computed(() => Object.entries(results.value).map(([engine, result]) => {
  const path = result.paths?.[0]
  return { engine, label: engineLabel(engine), status: result.status, pathCount: result.paths?.length || 0, makespan: path?.metrics?.makespan ?? '-', executionCount: path?.metrics?.execution_count ?? path?.executions?.length ?? '-', elapsed: result.elapsed_seconds ?? '-', validator: path?.validator_status || '' }
}))

const activePresentation = computed(() => presentations.value[activeEngine.value] || { result: results.value[activeEngine.value], path: null, tasks: [], makespan: 0, criticalPath: [], resourcePeak: 0 })
const metricRows = computed(() => {
  const metrics = activePresentation.value.path?.metrics || {}
  const labels = { makespan: '总工期', execution_count: '活动数', critical_path_length: '关键路径长度', peak_parallelism: '峰值并行度', average_parallelism: '平均并行度', total_wait: '总等待', missing_goal_facts: '缺失目标事实', resource_utilization: '资源利用率', resource_peak: '资源峰值' }
  return Object.entries(metrics).filter(([key]) => labels[key]).map(([key, value]) => ({ key, label: labels[key], value: formatMetric(value) }))
})

onMounted(async () => {
  ;[scenarios.value, capabilities.value] = await Promise.all([listPlannerScenarios(), getPlannerCapabilities()])
  if (scenarios.value.length) {
    form.scenario_id = scenarios.value[0].id
    await loadScenario()
  }
})

async function loadScenario() {
  run.value = null
  if (!form.scenario_id) {
    scenarioDetails.value = { revision: 0, scenario: {} }
    return
  }
  scenarioDetails.value = await getPlannerScenario(form.scenario_id)
  form.expected_revision = scenarioDetails.value.revision
  suggestedStates.current = [...(scenarioDetails.value.scenario?.initial_state_ids || [])]
  suggestedStates.target = [...(scenarioDetails.value.scenario?.goal_state_ids || [])]
  restoreSuggestions()
  const budget = scenarioDetails.value.scenario?.default_budget
  if (budget) Object.assign(form.budget, budget)
}

function restoreSuggestions() {
  form.current_state_node_ids = suggestedStates.current.map(directStateNodeId)
  form.target_state_node_ids = suggestedStates.target.map(directStateNodeId)
}

async function solve() {
  if (!currentStateIds.value.length) return ElMessage.warning('请至少选择一个当前状态或状态包')
  if (!targetStateIds.value.length) return ElMessage.warning('请至少选择一个目标状态或状态包')
  if (invalidSuggestedStateLabels.value.length) return ElMessage.error(`存在失效状态：${invalidSuggestedStateLabels.value.join('、')}`)
  if (selectedForbiddenTargetLabels.value.length) return ElMessage.error(`禁止状态不能作为目标：${selectedForbiddenTargetLabels.value.join('、')}`)
  running.value = true
  try {
    run.value = await createPlannerRun({
      scenario_id: form.scenario_id,
      expected_revision: form.expected_revision,
      current_state_ids: [...currentStateIds.value],
      target_state_ids: [...targetStateIds.value],
      engine: form.engine,
      seed: form.seed,
      budget: { ...form.budget },
      objectives: form.objectives.map((item) => ({ type: item.type, weight: Number(item.weight) })),
    })
    const resultEngines = Object.keys(results.value)
    activeEngine.value = resultEngines.find((engine) => results.value[engine]?.paths?.length) || resultEngines[0] || form.engine
    activeResultTab.value = 'gantt'
    if (run.value.status === 'OK') ElMessage.success('求解完成并通过统一校验')
    else ElMessage.warning('运行结束，请检查各引擎结果')
  } catch (error) {
    ElMessage.error(error?.response?.data?.error_message || error.message || '求解失败')
  } finally {
    running.value = false
  }
}

function directStateNodeId(stateId) { return `direct-state:${stateId}` }
function addObjective() { form.objectives.push({ type: 'minimize_makespan', weight: 1 }) }
function removeObjective(index) { if (form.objectives.length > 1) form.objectives.splice(index, 1) }
function bySortOrder(left, right) { return Number(left.sort_order || 0) - Number(right.sort_order || 0) || String(left.name || left.label || left.id).localeCompare(String(right.name || right.label || right.id), 'zh-CN') }

function buildStateTreeIndex(scenario) {
  const states = new Map((scenario.states || []).map((item) => [item.id, item]))
  const activities = new Map((scenario.activities || []).map((item) => [item.id, item]))
  const activityMemberships = new Map((scenario.activity_package_memberships || []).map((item) => [item.id, item]))
  const packages = new Map((scenario.state_packages || []).map((item) => [item.id, item]))
  const memberships = new Map((scenario.state_package_memberships || []).map((item) => [item.id, item]))
  const childrenByPackage = new Map()
  const membersByPackage = new Map()
  const providersByState = new Map()
  for (const activity of activities.values()) {
    for (const stateId of [activity.output_state_id, ...(activity.additional_output_state_ids || [])]) {
      if (!stateId) continue
      if (!providersByState.has(stateId)) providersByState.set(stateId, [])
      providersByState.get(stateId).push(activity)
    }
  }
  for (const item of packages.values()) {
    if (!item.parent_id) continue
    if (!childrenByPackage.has(item.parent_id)) childrenByPackage.set(item.parent_id, [])
    childrenByPackage.get(item.parent_id).push(item)
  }
  for (const item of memberships.values()) {
    if (!membersByPackage.has(item.state_package_id)) membersByPackage.set(item.state_package_id, [])
    membersByPackage.get(item.state_package_id).push(item)
  }
  return { states, activities, activityMemberships, packages, memberships, childrenByPackage, membersByPackage, providersByState, forbidden: new Set(scenario.forbidden_state_ids || []) }
}

function stateEnabled(stateId, index, forTarget) {
  const state = index.states.get(stateId)
  if (!state || state.is_active === false || (forTarget && index.forbidden.has(stateId))) return false
  const providers = index.providersByState.get(stateId) || []
  return !providers.length || providers.some((activity) => activity.is_active !== false)
}

function memberEnabled(member, index, forTarget) {
  if (!stateEnabled(member.state_id, index, forTarget)) return false
  const sourceMembership = member.source_membership_id ? index.activityMemberships.get(member.source_membership_id) : null
  const activity = sourceMembership ? index.activities.get(sourceMembership.activity_id) : null
  return activity?.is_active !== false
}

function buildStateTree(index, forTarget) {
  const packageEnabled = (packageId) => {
    const visited = new Set()
    let item = index.packages.get(packageId)
    while (item) {
      if (visited.has(item.id) || item.is_active === false) return false
      visited.add(item.id)
      item = item.parent_id ? index.packages.get(item.parent_id) : null
    }
    return true
  }
  const packageNode = (item, stack = new Set()) => {
    if (stack.has(item.id)) return { id: item.id, label: item.name, disabled: true, children: [] }
    const nextStack = new Set(stack).add(item.id)
    const packageChildren = (index.childrenByPackage.get(item.id) || []).sort(bySortOrder).map((child) => packageNode(child, nextStack))
    const memberChildren = (index.membersByPackage.get(item.id) || []).sort(bySortOrder).map((member) => ({
      id: member.id,
      label: index.states.get(member.state_id)?.name || member.state_id,
      disabled: !packageEnabled(item.id) || !memberEnabled(member, index, forTarget),
    }))
    const children = [...packageChildren, ...memberChildren]
    const hasSelectableDescendant = children.some((child) => !child.disabled || child.children?.some(hasSelectableNode))
    return {
      id: item.id,
      label: `${item.level === 1 ? '一级状态包' : '二级状态包'} · ${item.name}`,
      disabled: !packageEnabled(item.id) || !hasSelectableDescendant,
      children,
    }
  }
  const roots = [...index.packages.values()]
    .filter((item) => !item.parent_id || !index.packages.has(item.parent_id))
    .sort(bySortOrder)
    .map((item) => packageNode(item))
  const directStates = [...index.states.values()].sort(bySortOrder).map((state) => ({
    id: directStateNodeId(state.id),
    label: state.name,
    disabled: !stateEnabled(state.id, index, forTarget),
  }))
  return [...roots, { id: 'direct-state-root', label: '单个状态', disabled: !directStates.some((item) => !item.disabled), children: directStates }]
}

function hasSelectableNode(node) { return !node.disabled || (node.children || []).some(hasSelectableNode) }

function packageStateIds(packageId, index, forTarget, visited = new Set()) {
  if (visited.has(packageId)) return []
  const item = index.packages.get(packageId)
  if (!item || item.is_active === false) return []
  const nextVisited = new Set(visited).add(packageId)
  const values = []
  for (const member of index.membersByPackage.get(packageId) || []) {
    if (memberEnabled(member, index, forTarget)) values.push(member.state_id)
  }
  for (const child of index.childrenByPackage.get(packageId) || []) values.push(...packageStateIds(child.id, index, forTarget, nextVisited))
  return values
}

function selectedLeafStateIds(nodeIds, index) {
  const values = []
  for (const nodeId of nodeIds || []) {
    if (nodeId.startsWith('direct-state:')) values.push(nodeId.slice('direct-state:'.length))
    else if (index.memberships.has(nodeId)) values.push(index.memberships.get(nodeId).state_id)
  }
  return values
}

function expandSelectedStates(nodeIds, index, forTarget) {
  const values = selectedLeafStateIds(nodeIds, index)
  for (const nodeId of nodeIds || []) {
    if (index.packages.has(nodeId)) values.push(...packageStateIds(nodeId, index, forTarget))
    else if (nodeId === 'direct-state-root') {
      for (const state of index.states.values()) {
        if (!stateEnabled(state.id, index, forTarget)) continue
        values.push(state.id)
      }
    }
  }
  return [...new Set(values)].filter((stateId) => index.states.has(stateId)).sort()
}

function engineLabel(engine) { return { LEGACY: '旧引擎', ASTAR: 'Anytime A*', GA: '遗传算法 GA' }[engine] || engine }
function selectionCounts(current, target) {
  const currentIds = new Set(current)
  const satisfied = target.filter((id) => currentIds.has(id)).length
  return { current: current.length, target: target.length, satisfied, outstanding: target.length - satisfied }
}
function resourceLabel(resources) { return (resources || []).map((item) => `${item.name}×${item.quantity || 1}`).join('、') }
function objectiveSummary(objectives) {
  if (!objectives?.length) return '-'
  const labels = new Map(objectiveOptions.map((item) => [item.value, item.label]))
  return objectives.map((item) => `${labels.get(item.type) || item.type} × ${item.weight ?? 1}`).join('；')
}
function formatMetric(value) {
  if (Array.isArray(value)) return value.map((item) => Array.isArray(item) ? item.join('：') : String(item)).join('；') || '-'
  if (typeof value === 'number') return Number.isInteger(value) ? value : value.toFixed(3)
  if (typeof value === 'boolean') return value ? '是' : '否'
  return value ?? '-'
}
</script>

<style scoped>
.solve-workspace{display:grid;gap:16px}.solve-hero{display:flex;align-items:center;justify-content:space-between;padding:26px 30px;border-radius:18px;color:#fff;background:linear-gradient(130deg,#172554,#1e3a8a 62%,#0f766e);box-shadow:0 18px 45px rgba(30,58,138,.18)}.solve-hero h1{margin:3px 0 7px;font-size:28px}.solve-hero p{margin:0;color:#bfdbfe}.eyebrow{font-size:11px;letter-spacing:.16em;color:#5eead4!important}.eyebrow.dark{color:#0f766e!important}.control-card,.comparison-card,.result-card{padding:20px 22px;background:#fff;border:1px solid #e2e8f0;border-radius:14px}.control-grid{display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:14px}.state-control{grid-column:span 2}.objective-control{grid-column:1/-1}.objective-editor{display:grid;gap:8px;width:100%}.objective-row,.objective-hint{display:flex;align-items:center;gap:10px}.objective-hint{justify-content:space-between;color:#64748b;font-size:12px}.selection-alert{margin-bottom:12px}.selection-summary{display:flex;align-items:center;gap:18px;flex-wrap:wrap;padding:10px 12px;margin-bottom:12px;border-radius:10px;background:#f8fafc;color:#64748b;font-size:13px}.selection-summary strong{color:#0f766e}.selection-summary .el-button{margin-left:auto}.run-actions,.result-header,.section-title{display:flex;align-items:center;justify-content:space-between;gap:16px}.run-actions{border-top:1px solid #e2e8f0;padding-top:14px}.run-actions div{display:flex;gap:10px;align-items:center}.run-actions span,.run-summary span,.metric-strip span,.section-title p{color:#64748b;font-size:12px}.run-summary{display:flex;gap:32px;flex-wrap:wrap;padding:14px 20px;border-radius:12px;background:#eff6ff;border:1px solid #bfdbfe}.run-summary div{display:flex;gap:8px;align-items:center}.section-title h2,.result-header h2{margin:0}.section-title p{margin:4px 0 14px}.result-header{margin-bottom:16px}.result-header .eyebrow{margin:0 0 4px}.metric-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:12px}.metric-strip div{padding:12px;border:1px solid #dbeafe;border-radius:10px;background:#f8fbff;text-align:center}.metric-strip span{display:block}.metric-strip strong{font-size:20px;color:#1e3a8a}.result-tabs{min-height:360px}@media(max-width:1050px){.control-grid{grid-template-columns:1fr 1fr}.state-control{grid-column:span 1}.solve-hero,.result-header{align-items:flex-start;flex-direction:column}.metric-strip{grid-template-columns:1fr 1fr}}@media(max-width:700px){.control-grid,.metric-strip{grid-template-columns:1fr}.run-actions{align-items:flex-start;flex-direction:column}.selection-summary .el-button{margin-left:0}.objective-row{align-items:stretch;flex-direction:column}.objective-row .el-input-number{width:100%!important}}
</style>
