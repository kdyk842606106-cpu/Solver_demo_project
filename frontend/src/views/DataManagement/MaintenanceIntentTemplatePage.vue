<template>
  <div class="maintenance-intent-page">
    <h2>维修维护意图</h2>
    <el-row :gutter="16">
      <el-col :span="10">
        <el-card>
          <el-form :model="form" label-width="118px" @submit.prevent>
            <el-form-item label="设备类型" required>
              <el-select v-model="machineTypeId" style="width:100%" filterable @change="onTypeChange">
                <el-option
                  v-for="mt in machineTypes"
                  :key="mt.id"
                  :label="`${mt.name} (${mt.code})`"
                  :value="mt.id"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="问题类型" required>
              <el-input v-model="form.issue_type" placeholder="例如 vacuum_leak" />
            </el-form-item>
            <el-form-item label="名称" required>
              <el-input v-model="form.name" placeholder="例如 真空泄漏维护" />
            </el-form-item>
            <el-form-item label="二级活动" required>
              <el-tree-select
                v-model="form.scope_activity_node_id"
                :data="level2ActivityTreeOptions"
                :props="treeProps"
                node-key="id"
                check-strictly
                filterable
                style="width:100%"
              />
            </el-form-item>
            <el-form-item label="目标状态">
              <el-tree-select
                v-model="form.target_state_node_ids"
                :data="stateTreeOptions"
                :props="treeProps"
                node-key="id"
                style="width:100%"
                multiple
                show-checkbox
                check-strictly
                filterable
                collapse-tags
                collapse-tags-tooltip
              />
            </el-form-item>
            <el-form-item label="候选活动范围">
              <el-tree-select
                v-model="form.candidate_activity_scope_ids"
                :data="activityScopeTreeOptions"
                :props="treeProps"
                node-key="id"
                style="width:100%"
                multiple
                show-checkbox
                check-strictly
                filterable
                collapse-tags
                collapse-tags-tooltip
                placeholder="为空时默认使用二级活动"
              />
            </el-form-item>

            <el-divider content-position="left">
              观测事实
              <el-button size="small" style="margin-left:8px" @click="addObservedFact">新增</el-button>
            </el-divider>
            <div v-for="(fact, index) in form.observed_fact_templates" :key="`observed-${index}`" class="fact-row">
              <el-select v-model="fact.feature_key" size="small" filterable placeholder="特征">
                <el-option
                  v-for="feature in featureDefs"
                  :key="feature.feature_key"
                  :label="`${feature.feature_key} ${feature.feature_name}`"
                  :value="feature.feature_key"
                />
              </el-select>
              <el-input v-model="fact.value" size="small" placeholder="值" />
              <el-button size="small" type="danger" @click="form.observed_fact_templates.splice(index, 1)">
                删除
              </el-button>
            </div>

            <el-divider content-position="left">
              期望事实
              <el-button size="small" style="margin-left:8px" @click="addDesiredFact">新增</el-button>
            </el-divider>
            <div v-for="(fact, index) in form.desired_fact_templates" :key="`desired-${index}`" class="fact-row">
              <el-select v-model="fact.feature_key" size="small" filterable placeholder="特征">
                <el-option
                  v-for="feature in featureDefs"
                  :key="feature.feature_key"
                  :label="`${feature.feature_key} ${feature.feature_name}`"
                  :value="feature.feature_key"
                />
              </el-select>
              <el-input v-model="fact.value" size="small" placeholder="值" />
              <el-button size="small" type="danger" @click="form.desired_fact_templates.splice(index, 1)">
                删除
              </el-button>
            </div>

            <el-form-item label="说明">
              <el-input v-model="form.description" type="textarea" :rows="2" />
            </el-form-item>
            <el-form-item label="启用">
              <el-switch v-model="form.is_active" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="save">保存</el-button>
              <el-button @click="reset">清空</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="14">
        <el-card v-loading="loading">
          <el-empty v-if="!machineTypeId" description="请先选择设备类型" />
          <el-table v-else :data="templates" size="small" border stripe>
            <el-table-column prop="issue_type" label="问题类型" width="150" show-overflow-tooltip />
            <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
            <el-table-column label="二级活动" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">{{ activityLabel(row.scope_activity_node_id) }}</template>
            </el-table-column>
            <el-table-column label="目标" min-width="170" show-overflow-tooltip>
              <template #default="{ row }">{{ formatNodeIds(row.target_state_node_ids, stateNodes) }}</template>
            </el-table-column>
            <el-table-column label="事实" min-width="190" show-overflow-tooltip>
              <template #default="{ row }">
                {{ formatFacts(row.observed_fact_templates, '观测') }}
                {{ formatFacts(row.desired_fact_templates, '期望') }}
              </template>
            </el-table-column>
            <el-table-column label="状态" width="74">
              <template #default="{ row }">
                <el-tag size="small" :type="row.is_active ? 'success' : 'info'">
                  {{ row.is_active ? '启用' : '停用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="140" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="edit(row)">编辑</el-button>
                <el-button size="small" type="danger" @click="remove(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createMaintenanceIntentTemplate,
  deleteMaintenanceIntentTemplate,
  getActivityNodes,
  getFeatureDefs,
  getMachineTypes,
  getMaintenanceIntentTemplates,
  getStateNodes,
  updateMaintenanceIntentTemplate,
} from '../../api/masterData'
import { buildHierarchyTree, treeSelectProps } from '../../utils/hierarchyTree'

const machineTypes = ref([])
const machineTypeId = ref(null)
const activityNodes = ref([])
const stateNodes = ref([])
const featureDefs = ref([])
const templates = ref([])
const loading = ref(false)
const saving = ref(false)
const editId = ref(null)
const form = ref(defaultForm())
const treeProps = treeSelectProps
const level2ActivityTreeOptions = computed(() =>
  buildHierarchyTree(activityNodes.value, { disabled: (node) => node.level !== 2 }),
)
const activityScopeTreeOptions = computed(() =>
  buildHierarchyTree(activityNodes.value, { disabled: (node) => node.level > 2 }),
)
const stateTreeOptions = computed(() =>
  buildHierarchyTree(stateNodes.value, { disabled: (node) => node.level < 2 }),
)

function defaultForm() {
  return {
    issue_type: '',
    name: '',
    description: '',
    scope_activity_node_id: null,
    target_state_node_ids: [],
    candidate_activity_scope_ids: [],
    observed_fact_templates: [],
    desired_fact_templates: [],
    is_active: true,
    metadata_json: null,
  }
}

function newFact() {
  return { feature_key: '', operator: 'eq', value: '', value_list: null }
}

function addObservedFact() {
  form.value.observed_fact_templates.push(newFact())
}

function addDesiredFact() {
  form.value.desired_fact_templates.push(newFact())
}

function nodeLabel(node) {
  return `${node.level}级 ${node.code} ${node.name}`
}

function activityLabel(id) {
  const node = activityNodes.value.find((item) => item.id === id)
  return node ? nodeLabel(node) : '-'
}

function formatNodeIds(ids, nodes) {
  if (!ids?.length) return '-'
  return ids
    .map((id) => nodes.find((node) => node.id === id))
    .filter(Boolean)
    .map((node) => node.code)
    .join(' / ')
}

function formatFacts(facts, label) {
  if (!facts?.length) return ''
  return `${label}: ${facts.map((fact) => `${fact.feature_key}=${fact.value}`).join(' / ')}`
}

function normalizeFacts(facts) {
  return facts
    .filter((fact) => fact.feature_key && fact.value !== '')
    .map((fact) => ({
      feature_key: fact.feature_key,
      operator: 'eq',
      value: String(fact.value),
      value_list: null,
    }))
}

async function onTypeChange() {
  reset()
  templates.value = []
  activityNodes.value = []
  stateNodes.value = []
  featureDefs.value = []
  if (!machineTypeId.value) return
  loading.value = true
  try {
    const [activities, states, features, templateRows] = await Promise.all([
      getActivityNodes(machineTypeId.value),
      getStateNodes(machineTypeId.value),
      getFeatureDefs(machineTypeId.value),
      getMaintenanceIntentTemplates(machineTypeId.value),
    ])
    activityNodes.value = activities
    stateNodes.value = states
    featureDefs.value = features
    templates.value = templateRows
  } finally {
    loading.value = false
  }
}

async function reloadTemplates() {
  if (!machineTypeId.value) return
  templates.value = await getMaintenanceIntentTemplates(machineTypeId.value)
}

async function save() {
  if (!machineTypeId.value || !form.value.issue_type || !form.value.name || !form.value.scope_activity_node_id) {
    return ElMessage.warning('设备类型、问题类型、名称和二级活动不能为空')
  }
  const observed = normalizeFacts(form.value.observed_fact_templates)
  const desired = normalizeFacts(form.value.desired_fact_templates)
  if (!form.value.target_state_node_ids.length && !desired.length) {
    return ElMessage.warning('至少需要一个目标状态或期望事实')
  }
  saving.value = true
  try {
    const payload = {
      machine_type_id: machineTypeId.value,
      scope_activity_node_id: form.value.scope_activity_node_id,
      issue_type: form.value.issue_type.trim(),
      name: form.value.name.trim(),
      description: form.value.description.trim() || null,
      target_state_node_ids: form.value.target_state_node_ids,
      candidate_activity_scope_ids: form.value.candidate_activity_scope_ids,
      observed_fact_templates: observed,
      desired_fact_templates: desired,
      is_active: form.value.is_active,
      metadata_json: null,
    }
    if (editId.value) {
      await updateMaintenanceIntentTemplate(editId.value, payload)
    } else {
      await createMaintenanceIntentTemplate(machineTypeId.value, payload)
    }
    ElMessage.success('维护意图已保存')
    reset()
    await reloadTemplates()
  } finally {
    saving.value = false
  }
}

function edit(row) {
  editId.value = row.id
  form.value = {
    issue_type: row.issue_type,
    name: row.name,
    description: row.description ?? '',
    scope_activity_node_id: row.scope_activity_node_id,
    target_state_node_ids: [...(row.target_state_node_ids ?? [])],
    candidate_activity_scope_ids: [...(row.candidate_activity_scope_ids ?? [])],
    observed_fact_templates: (row.observed_fact_templates ?? []).map((fact) => ({ ...fact })),
    desired_fact_templates: (row.desired_fact_templates ?? []).map((fact) => ({ ...fact })),
    is_active: row.is_active,
    metadata_json: row.metadata_json ?? null,
  }
}

async function remove(id) {
  await ElMessageBox.confirm('确定删除这个维护意图模板吗？', '确认', { type: 'warning' })
  await deleteMaintenanceIntentTemplate(id)
  ElMessage.success('已删除')
  await reloadTemplates()
}

function reset() {
  editId.value = null
  form.value = defaultForm()
}

onMounted(async () => {
  machineTypes.value = await getMachineTypes()
})
</script>

<style scoped>
.maintenance-intent-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.maintenance-intent-page h2 {
  margin: 0;
  font-size: 18px;
}

.fact-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 120px auto;
  gap: 8px;
  margin-bottom: 8px;
}
</style>
