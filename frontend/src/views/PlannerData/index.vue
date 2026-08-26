<template>
  <div class="planner-workspace">
    <section class="hero-card">
      <div>
        <p class="eyebrow">PLANNER SHARED SCENARIO</p>
        <h1>场景与活动网络</h1>
        <p>维护活动、活动包和基础状态；本次求解目标在多引擎求解页选择。</p>
      </div>
      <div class="hero-actions">
        <el-select v-model="scenarioId" filterable placeholder="选择场景" style="width: 280px" @change="loadScenario">
          <el-option v-for="item in scenarios" :key="item.id" :value="item.id" :label="`${item.display_code} · ${item.name}`" />
        </el-select>
        <el-button @click="scenarioDialog = true">新建场景</el-button>
        <template v-if="scenarioId">
          <el-button v-if="!editing" type="primary" @click="enterEdit">进入编辑</el-button>
          <el-button v-else @click="cancelEdit">取消编辑</el-button>
          <el-button v-if="editing" type="success" :disabled="!drafts.length" :loading="saving" @click="commitDraft">统一提交（{{ drafts.length }}）</el-button>
        </template>
      </div>
    </section>

    <el-empty v-if="!scenarioId" description="新建或选择一个 Planner 场景" />
    <template v-else>
      <section class="summary-strip">
        <div><strong>{{ scenario.activities?.length || 0 }}</strong><span>活动</span></div>
        <div><strong>{{ scenario.activity_packages?.length || 0 }}</strong><span>活动包</span></div>
        <div><strong>{{ scenario.resources?.length || 0 }}</strong><span>容量资源</span></div>
        <div><strong>{{ scenario.external_events?.length || 0 }}</strong><span>外部事件</span></div>
        <el-tag :type="editing ? 'warning' : 'info'">{{ editing ? '编辑草稿' : '只读预览' }}</el-tag>
        <span class="snapshot">快照 {{ shortHash }}</span>
      </section>

      <el-alert v-if="editing && drafts.length" type="warning" :closable="false" class="draft-alert">
        <template #title>当前有 {{ drafts.length }} 项未提交变更；只有“统一提交”会写入数据库。</template>
      </el-alert>

      <el-tabs v-model="activeTab" class="workspace-tabs" @tab-change="onTabChange">
        <el-tab-pane label="活动与活动包" name="model">
          <div class="model-grid">
            <section class="panel">
              <header class="panel-title">
                <div><h2>活动包</h2><p>两级组织结构，状态包在后台同步镜像。</p></div>
                <el-dropdown :disabled="!editing" @command="openPackageDialog">
                  <el-button type="primary" plain>新增包</el-button>
                  <template #dropdown><el-dropdown-menu><el-dropdown-item command="root">一级活动包</el-dropdown-item><el-dropdown-item command="child">二级活动包</el-dropdown-item></el-dropdown-menu></template>
                </el-dropdown>
              </header>
              <el-table :data="packageRows" size="small" row-key="id" default-expand-all>
                <el-table-column prop="display_code" label="编号" width="100" />
                <el-table-column prop="name" label="名称" />
                <el-table-column label="层级" width="90"><template #default="{ row }">{{ row.level === 1 ? '一级' : '二级' }}</template></el-table-column>
                <el-table-column label="成员" width="80"><template #default="{ row }">{{ memberCount(row.id) }}</template></el-table-column>
                <el-table-column label="操作" width="80"><template #default="{ row }"><el-button link type="danger" :disabled="!editing" @click="queueDeletePackage(row)">删除</el-button></template></el-table-column>
              </el-table>
            </section>

            <section class="panel">
              <header class="panel-title">
                <div><h2>活动</h2><p>活动编号和运行所需的内部信息由系统生成。</p></div>
                <el-button type="primary" :disabled="!editing" @click="openActivityDialog">新增活动</el-button>
              </header>
              <el-table :data="scenario.activities || []" size="small" row-key="id">
                <el-table-column prop="display_code" label="编号" width="105" />
                <el-table-column prop="name" label="活动" min-width="150" />
                <el-table-column prop="duration" label="工期" width="70" />
                <el-table-column label="前置" width="70"><template #default="{ row }">{{ row.preconditions?.length || 0 }}</template></el-table-column>
                <el-table-column label="所属包" min-width="150"><template #default="{ row }">{{ packageNames(row.id) || '未归属' }}</template></el-table-column>
                <el-table-column label="操作" width="125"><template #default="{ row }"><el-button link :disabled="!editing" @click="queueClone(row)">复制</el-button><el-button link type="danger" :disabled="!editing" @click="queueDeleteActivity(row)">删除</el-button></template></el-table-column>
              </el-table>
            </section>
          </div>
        </el-tab-pane>

        <el-tab-pane label="活动网络" name="network">
          <PlannerX6ActivityCanvas
            :graph="graph"
            :editable="editing"
            @select-activity="selectActivity"
            @connect-activities="queueConnection"
            @remove-connection="queueRemoveConnection"
            @layout-change="queueLayout"
          />
        </el-tab-pane>

        <el-tab-pane label="资源与事件" name="conditions">
          <div class="model-grid">
            <section class="panel">
              <header class="panel-title"><div><h2>容量资源</h2><p>本期不分配具体资源实例。</p></div><el-button :disabled="!editing" @click="resourceDialog = true">新增资源</el-button></header>
              <el-table :data="scenario.resources || []" size="small"><el-table-column prop="name" label="资源"/><el-table-column prop="capacity" label="总容量" width="100"/></el-table>
            </section>
            <section class="panel">
              <header class="panel-title"><div><h2>外部事件</h2><p>按场景相对时间激活或移除状态。</p></div><el-button :disabled="!editing" @click="eventDialog = true">新增事件</el-button></header>
              <el-table :data="scenario.external_events || []" size="small"><el-table-column prop="name" label="事件"/><el-table-column prop="time" label="发生时间" width="100"/><el-table-column label="增加状态"><template #default="{ row }">{{ stateNames(row.add_state_ids) }}</template></el-table-column></el-table>
            </section>
            <section class="panel full-panel">
              <header class="panel-title"><div><h2>基础状态</h2><p>管理人工创建、可用于活动前置和求解选择的业务事实。</p></div><el-button :disabled="!editing" @click="seedDialog = true">新增基础状态</el-button></header>
              <el-table :data="baseStates" size="small"><el-table-column prop="name" label="名称"/></el-table>
            </section>
          </div>
        </el-tab-pane>

        <el-tab-pane label="校验与导入导出" name="validation">
          <section class="panel">
            <header class="panel-title"><div><h2>求解预检</h2><p>阻断问题修复前不能启动任何引擎。</p></div><div><el-button @click="runValidation">执行校验</el-button><el-button @click="downloadJson">导出 JSON</el-button><el-button @click="importDialog = true">导入 JSON</el-button><el-button @click="downloadExcel">导出 Excel</el-button><el-button @click="excelInput?.click()">导入 Excel</el-button><input ref="excelInput" class="hidden-input" type="file" accept=".xlsx" @change="doExcelImport"/></div></header>
            <el-result v-if="validation && validation.valid" icon="success" title="场景校验通过" :sub-title="`快照 ${validation.scenario_hash.slice(0, 12)}`" />
            <el-table v-else-if="validation" :data="validation.issues" size="small"><el-table-column prop="code" label="问题代码" width="210"/><el-table-column prop="message" label="说明"/><el-table-column prop="object_id" label="对象"/></el-table>
            <el-empty v-else description="尚未执行校验" />
          </section>
        </el-tab-pane>
      </el-tabs>
    </template>

    <el-dialog v-model="scenarioDialog" title="新建 Planner 场景" width="420px"><el-input v-model="scenarioName" placeholder="场景名称"/><template #footer><el-button @click="scenarioDialog=false">取消</el-button><el-button type="primary" @click="saveScenario">创建</el-button></template></el-dialog>
    <el-dialog v-model="packageDialog" :title="packageForm.level === 1 ? '新增一级活动包' : '新增二级活动包'" width="460px"><el-form label-position="top"><el-form-item label="名称"><el-input v-model="packageForm.name"/></el-form-item><el-form-item v-if="packageForm.level===2" label="所属一级包"><el-select v-model="packageForm.parent_id" style="width:100%"><el-option v-for="item in rootPackages" :key="item.id" :value="item.id" :label="item.name"/></el-select></el-form-item></el-form><template #footer><el-button @click="packageDialog=false">取消</el-button><el-button type="primary" @click="queuePackage">加入草稿</el-button></template></el-dialog>
    <el-dialog v-model="activityDialog" title="新增活动" width="640px">
      <el-form label-position="top">
        <el-form-item label="活动名称"><el-input v-model="activityForm.name"/></el-form-item>
        <el-form-item label="工期"><el-input-number v-model="activityForm.duration" :min="1" style="width:100%"/></el-form-item>
        <el-form-item label="所属二级活动包"><el-select v-model="activityForm.package_id" clearable style="width:100%"><el-option v-for="item in childPackages" :key="item.id" :value="item.id" :label="item.name"/></el-select></el-form-item>
        <el-form-item label="前置状态绑定">
          <div class="state-binding-list" data-testid="activity-state-bindings">
            <div v-for="(binding, index) in activityForm.preconditions" :key="index" class="state-binding-row">
              <el-select v-model="binding.state_id" clearable filterable placeholder="选择已有状态" class="state-binding-select">
                <el-option v-for="item in selectableStates" :key="item.id" :value="item.id" :label="item.name" :disabled="isActivityStateDisabled(item.id, index)"/>
              </el-select>
              <el-radio-group v-model="binding.relation_role" class="state-binding-role">
                <el-radio-button value="transition">替换旧状态</el-radio-button>
                <el-radio-button value="required">执行后保留</el-radio-button>
              </el-radio-group>
              <el-button plain type="danger" aria-label="移除状态绑定" @click="removeActivityPrecondition(index)">移除</el-button>
            </div>
            <el-button data-testid="add-activity-state-binding" plain type="primary" @click="addActivityPrecondition">添加状态绑定</el-button>
            <span class="state-binding-help">可绑定多个前置状态；留空表示没有前置状态。</span>
          </div>
        </el-form-item>
        <el-form-item label="外部事件绑定">
          <el-select
            v-model="activityForm.event_reqs"
            multiple
            clearable
            filterable
            collapse-tags
            :disabled="!selectableEvents.length"
            :placeholder="selectableEvents.length ? '选择活动必须等待的外部事件' : '当前场景没有外部事件'"
            data-testid="activity-event-bindings"
            style="width:100%"
          >
            <el-option v-for="item in selectableEvents" :key="item.id" :value="item.id" :label="`${item.name}（T+${item.time}）`"/>
          </el-select>
          <span class="state-binding-help">活动只能在所选事件发生后开始；可绑定多个事件。</span>
        </el-form-item>
        <el-alert title="活动类型由前置关系自动识别；活动编号和运行所需信息由系统管理。" type="info" :closable="false"/>
      </el-form>
      <template #footer><el-button @click="activityDialog=false">取消</el-button><el-button type="primary" @click="queueActivity">加入草稿</el-button></template>
    </el-dialog>
    <el-dialog v-model="seedDialog" title="新增基础状态" width="420px"><el-form label-position="top"><el-form-item label="名称"><el-input v-model="seedForm.name"/></el-form-item></el-form><template #footer><el-button @click="seedDialog=false">取消</el-button><el-button type="primary" @click="queueSeed">加入草稿</el-button></template></el-dialog>
    <el-dialog v-model="resourceDialog" title="新增容量资源" width="420px"><el-form label-position="top"><el-form-item label="名称"><el-input v-model="resourceForm.name"/></el-form-item><el-form-item label="总容量"><el-input-number v-model="resourceForm.capacity" :min="1" style="width:100%"/></el-form-item></el-form><template #footer><el-button @click="resourceDialog=false">取消</el-button><el-button type="primary" @click="queueResource">加入草稿</el-button></template></el-dialog>
    <el-dialog v-model="eventDialog" title="新增外部事件" width="480px"><el-form label-position="top"><el-form-item label="名称"><el-input v-model="eventForm.name"/></el-form-item><el-form-item label="发生时间"><el-input-number v-model="eventForm.time" :min="0" style="width:100%"/></el-form-item><el-form-item label="增加状态"><el-select v-model="eventForm.add_state_ids" multiple style="width:100%"><el-option v-for="item in selectableStates" :key="item.id" :value="item.id" :label="item.name"/></el-select></el-form-item></el-form><template #footer><el-button @click="eventDialog=false">取消</el-button><el-button type="primary" @click="queueEvent">加入草稿</el-button></template></el-dialog>
    <el-dialog v-model="importDialog" title="导入 Planner JSON" width="640px"><el-input v-model="importText" type="textarea" :rows="16" placeholder="粘贴导出的 scenario 对象或完整导出结果"/><template #footer><el-button @click="importDialog=false">取消</el-button><el-button type="primary" @click="doImport">导入并生成新 ID</el-button></template></el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PlannerX6ActivityCanvas from './PlannerX6ActivityCanvas.vue'
import { commitPlannerDraft, createPlannerScenario, exportPlannerScenario, getPlannerGraph, getPlannerScenario, importPlannerExcel, importPlannerScenario, listPlannerScenarios, plannerExcelExportUrl, validatePlannerScenario } from '../../api/planner'

const scenarios = ref([]), scenarioId = ref(''), current = ref({ revision: 0, scenario: {} }), graph = ref({ containers: [], nodes: [], edges: [] })
const activeTab = ref('model'), editing = ref(false), drafts = ref([]), saving = ref(false), validation = ref(null)
const scenarioDialog = ref(false), packageDialog = ref(false), activityDialog = ref(false), seedDialog = ref(false), resourceDialog = ref(false), eventDialog = ref(false), importDialog = ref(false)
const excelInput = ref(null)
const scenarioName = ref(''), importText = ref('')
const packageForm = reactive({ level: 1, name: '', parent_id: null })
const activityForm = reactive({ name: '', duration: 1, package_id: null, preconditions: [], event_reqs: [] })
const seedForm = reactive({ name: '' }), resourceForm = reactive({ name: '', capacity: 1 }), eventForm = reactive({ name: '', time: 0, add_state_ids: [] })
const scenario = computed(() => current.value.scenario || {})
const shortHash = computed(() => (current.value.scenario_hash || '').slice(0, 12))
const rootPackages = computed(() => (scenario.value.activity_packages || []).filter((item) => item.level === 1))
const childPackages = computed(() => (scenario.value.activity_packages || []).filter((item) => item.level === 2))
const packageRows = computed(() => [...rootPackages.value, ...childPackages.value])
const baseStates = computed(() => (scenario.value.states || []).filter((item) => item.state_kind === 'seed'))
const selectableStates = computed(() => scenario.value.states || [])
const selectableEvents = computed(() => scenario.value.external_events || [])

onMounted(loadScenarios)
async function loadScenarios() { scenarios.value = await listPlannerScenarios() }
async function loadScenario() { if (!scenarioId.value) return; current.value = await getPlannerScenario(scenarioId.value); validation.value = null; await loadGraph() }
async function loadGraph() { graph.value = await getPlannerGraph(scenarioId.value) }
async function onTabChange(name) { if (name === 'network') await loadGraph() }
async function saveScenario() { if (!scenarioName.value.trim()) return; const created = await createPlannerScenario({ name: scenarioName.value.trim() }); scenarioDialog.value = false; scenarioName.value = ''; await loadScenarios(); scenarioId.value = created.id; await loadScenario() }
function enterEdit() { editing.value = true; drafts.value = [] }
function cancelEdit() { drafts.value = []; editing.value = false }
function addDraft(operation, description) { drafts.value.push({ ...operation, description }); ElMessage.success(`已加入草稿：${description}`) }
function replaceDraft(predicate, operation, description) { const index = drafts.value.findIndex(predicate); const item = { ...operation, description }; if (index >= 0) drafts.value.splice(index, 1, item); else drafts.value.push(item); ElMessage.success(`已加入草稿：${description}`) }
async function commitDraft() { saving.value = true; try { await commitPlannerDraft(scenarioId.value, { expected_revision: current.value.revision, operations: drafts.value.map(({ description, ...item }) => item) }); ElMessage.success('全部草稿已在一个事务中提交'); drafts.value = []; editing.value = false; await loadScenario() } finally { saving.value = false } }
function openPackageDialog(kind) { packageForm.level = kind === 'root' ? 1 : 2; packageForm.name = ''; packageForm.parent_id = null; packageDialog.value = true }
function queuePackage() { if (!packageForm.name.trim() || (packageForm.level === 2 && !packageForm.parent_id)) return ElMessage.warning('请填写完整'); addDraft({ operation: 'create_package', client_ref: `draft:package:${Date.now()}`, payload: { name: packageForm.name.trim(), parent_id: packageForm.level === 2 ? packageForm.parent_id : null } }, `新建活动包 ${packageForm.name}`); packageDialog.value = false }
function emptyActivityPrecondition() { return { state_id: null, relation_role: 'transition' } }
function openActivityDialog() { Object.assign(activityForm, { name: '', duration: 1, package_id: null, preconditions: [emptyActivityPrecondition()], event_reqs: [] }); activityDialog.value = true }
function addActivityPrecondition() { activityForm.preconditions.push(emptyActivityPrecondition()) }
function removeActivityPrecondition(index) { activityForm.preconditions.splice(index, 1) }
function isActivityStateDisabled(stateId, currentIndex) { return activityForm.preconditions.some((item, index) => index !== currentIndex && item.state_id === stateId) }
function queueActivity() {
  if (!activityForm.name.trim()) return ElMessage.warning('请填写活动名称')
  const preconditions = activityForm.preconditions
    .filter((item) => item.state_id)
    .map((item) => ({ state_id: item.state_id, relation_role: item.relation_role }))
  if (new Set(preconditions.map((item) => item.state_id)).size !== preconditions.length) return ElMessage.warning('同一前置状态只能绑定一次')
  const ref = `draft:activity:${Date.now()}`
  addDraft({ operation: 'create_activity', client_ref: ref, payload: { name: activityForm.name.trim(), duration: activityForm.duration, preconditions, event_reqs: [...activityForm.event_reqs] } }, `新建活动 ${activityForm.name}`)
  if (activityForm.package_id) addDraft({ operation: 'add_membership', payload: { package_id: activityForm.package_id, activity_id: ref } }, '加入活动包')
  activityDialog.value = false
}
function pendingPreconditions(activity) { return drafts.value.findLast((item) => item.operation === 'update_activity' && item.object_id === activity.id && item.payload.preconditions)?.payload.preconditions || activity.preconditions || [] }
function queueConnection({ sourceActivityId, targetActivityId }) { const source = (scenario.value.activities || []).find((item) => item.id === sourceActivityId); const target = (scenario.value.activities || []).find((item) => item.id === targetActivityId); if (!source || !target) return; const preconditions = [...pendingPreconditions(target)]; if (preconditions.some((item) => item.state_id === source.output_state_id)) return ElMessage.warning('这条活动依赖已经存在'); preconditions.push({ state_id: source.output_state_id, relation_role: 'transition' }); replaceDraft((item) => item.operation === 'update_activity' && item.object_id === target.id && item.payload.preconditions, { operation: 'update_activity', object_id: target.id, payload: { preconditions } }, `连接 ${source.name} → ${target.name}`) }
function queueRemoveConnection(edge) { const targetRef = (graph.value.nodes || []).find((item) => item.id === edge.target); const target = (scenario.value.activities || []).find((item) => item.id === targetRef?.canonical_activity_id); if (!target) return; const preconditions = pendingPreconditions(target).filter((item) => !(item.state_id === edge.state_id && item.relation_role === edge.relation_role)); replaceDraft((item) => item.operation === 'update_activity' && item.object_id === target.id && item.payload.preconditions, { operation: 'update_activity', object_id: target.id, payload: { preconditions } }, `移除指向 ${target.name} 的依赖`) }
function queueLayout(layout) {
  const existing = drafts.value.find((item) => item.operation === 'update_layout')
  const activityRefs = new Map((existing?.payload.activity_refs || []).map((item) => [item.id, item]))
  const packageContainers = new Map((existing?.payload.package_containers || []).map((item) => [item.id, item]))
  const updates = layout.updates?.length ? layout.updates : [layout]
  for (const item of updates) {
    const target = item.kind === 'package' ? packageContainers : activityRefs
    const next = { ...(target.get(item.id) || {}), id: item.id }
    if (item.x != null && item.y != null) {
      next.x = item.x
      next.y = item.y
    }
    if (item.kind === 'package' && item.width != null && item.height != null) {
      next.width = item.width
      next.height = item.height
    }
    target.set(item.id, next)
  }
  replaceDraft(
    (item) => item.operation === 'update_layout',
    {
      operation: 'update_layout',
      payload: {
        activity_refs: [...activityRefs.values()],
        package_containers: [...packageContainers.values()],
      },
    },
    layout.reason === 'auto-arrange'
      ? '自动整理活动网络'
      : (updates.some((item) => item.kind === 'package') ? '调整活动包布局' : '调整活动布局'),
  )
}
function queueClone(row) { const ref = `draft:activity:${Date.now()}`; addDraft({ operation: 'create_activity', client_ref: ref, payload: { name: `${row.name}副本`, duration: row.duration, preconditions: row.preconditions, additional_output_state_ids: row.additional_output_state_ids, resource_reqs: row.resource_reqs, event_reqs: row.event_reqs, max_instances: row.max_instances } }, `复制 ${row.name}`) }
async function queueDeletePackage(row) { await ElMessageBox.confirm(`删除活动包“${row.name}”？活动本体不会删除。`, '确认'); addDraft({ operation: 'delete_package', object_id: row.id }, `删除包 ${row.name}`) }
async function queueDeleteActivity(row) { await ElMessageBox.confirm(`删除活动“${row.name}”？被其他活动依赖时提交会被阻止。`, '确认'); addDraft({ operation: 'delete_activity', object_id: row.id }, `删除活动 ${row.name}`) }
function queueSeed() { if (!seedForm.name.trim()) return; addDraft({ operation: 'create_seed_state', payload: { name: seedForm.name.trim() } }, `新增基础状态 ${seedForm.name}`); seedDialog.value = false; seedForm.name = '' }
function queueResource() { if (!resourceForm.name.trim()) return; addDraft({ operation: 'create_resource', payload: { name: resourceForm.name.trim(), capacity: resourceForm.capacity, is_active: true } }, `新增容量资源 ${resourceForm.name}`); resourceDialog.value = false }
function queueEvent() { if (!eventForm.name.trim()) return; addDraft({ operation: 'create_event', payload: { name: eventForm.name.trim(), time: eventForm.time, add_state_ids: [...eventForm.add_state_ids], remove_state_ids: [] } }, `新增事件 ${eventForm.name}`); eventDialog.value = false }
async function runValidation() { validation.value = await validatePlannerScenario(scenarioId.value); validation.value.valid ? ElMessage.success('校验通过') : ElMessage.error(`发现 ${validation.value.issues.length} 个阻断问题`) }
async function downloadJson() { const data = await exportPlannerScenario(scenarioId.value); const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${scenario.value.display_code || 'planner-scenario'}.json`; anchor.click(); URL.revokeObjectURL(url) }
function downloadExcel() { window.location.assign(plannerExcelExportUrl(scenarioId.value)) }
async function doExcelImport(event) { const file = event.target.files?.[0]; if (!file) return; try { const imported = await importPlannerExcel(file); await loadScenarios(); scenarioId.value = imported.id; await loadScenario(); ElMessage.success('Excel 导入完成，内部引用已自动转换') } finally { event.target.value = '' } }
async function doImport() { try { const parsed = JSON.parse(importText.value); const imported = await importPlannerScenario({ scenario: parsed.scenario || parsed, preserve_ids: false }); importDialog.value = false; importText.value = ''; await loadScenarios(); scenarioId.value = imported.id; await loadScenario(); ElMessage.success('导入完成，内部引用已自动重建') } catch (error) { ElMessage.error(error?.response?.data?.error_message || error.message || '导入失败') } }
function memberCount(packageId) { return (scenario.value.activity_package_memberships || []).filter((item) => item.package_id === packageId).length }
function packageNames(activityId) { const ids = (scenario.value.activity_package_memberships || []).filter((item) => item.activity_id === activityId).map((item) => item.package_id); return (scenario.value.activity_packages || []).filter((item) => ids.includes(item.id)).map((item) => item.name).join('、') }
function stateNames(ids = []) { const byId = Object.fromEntries((scenario.value.states || []).map((item) => [item.id, item.name])); return ids.map((id) => byId[id] || '未知状态').join('、') || '-' }
function selectActivity(id) { const item = (scenario.value.activities || []).find((row) => row.id === id); if (item) ElMessage.info(`${item.display_code} ${item.name}`) }
</script>

<style scoped>
.planner-workspace { display: grid; gap: 16px; }.hero-card { display: flex; justify-content: space-between; gap: 24px; align-items: center; padding: 24px 28px; border-radius: 18px; color: #fff; background: linear-gradient(125deg,#0f172a,#134e4a 68%,#0f766e); box-shadow: 0 18px 45px rgba(15,23,42,.18); }.hero-card h1 { margin: 3px 0 7px; font-size: 27px; }.hero-card p { margin: 0; color: #cbd5e1; }.eyebrow { font-size: 11px; letter-spacing: .16em; color: #5eead4!important; }.hero-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }
.summary-strip { display: flex; gap: 24px; align-items: center; padding: 13px 18px; background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; }.summary-strip div { display:flex;gap:6px;align-items:baseline}.summary-strip strong{font-size:20px;color:#0f766e}.summary-strip span{font-size:12px;color:#64748b}.summary-strip .snapshot{margin-left:auto}.draft-alert{margin:0}.workspace-tabs{background:#fff;border-radius:14px;padding:0 18px 18px;box-shadow:0 7px 24px rgba(15,23,42,.05)}
.model-grid{display:grid;grid-template-columns:1fr 1.4fr;gap:16px}.panel{padding:18px;border:1px solid #e2e8f0;border-radius:12px;background:#fff}.full-panel{grid-column:1/-1}.panel-title{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:14px}.panel-title h2{margin:0 0 4px;font-size:17px}.panel-title p{margin:0;color:#64748b;font-size:12px}.target-form{margin-top:18px}.muted{color:#64748b}
.hidden-input{display:none}
.state-binding-list{display:grid;gap:10px;width:100%}.state-binding-row{display:grid;grid-template-columns:minmax(180px,1fr) auto auto;gap:8px;align-items:center}.state-binding-select{width:100%}.state-binding-help{font-size:12px;color:#64748b}.state-binding-list>[data-testid="add-activity-state-binding"]{justify-self:start}
@media(max-width:1000px){.hero-card{align-items:flex-start;flex-direction:column}.hero-actions{justify-content:flex-start}.model-grid{grid-template-columns:1fr}}
@media(max-width:680px){.state-binding-row{grid-template-columns:1fr}.state-binding-role{justify-self:start}}
</style>
