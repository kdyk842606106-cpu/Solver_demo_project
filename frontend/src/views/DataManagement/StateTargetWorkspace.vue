<template>
  <div class="state-workspace">
    <div class="workspace-toolbar">
      <div>
        <h2>状态目标</h2>
        <p>用多层状态树维护目标包和原子状态，叶子节点自动作为原子状态参与展开。</p>
      </div>
      <div class="toolbar-controls">
        <el-select
          v-model="machineTypeId"
          placeholder="选择设备类型"
          filterable
          style="width: 320px"
          @change="onTypeChange"
        >
          <el-option
            v-for="item in machineTypes"
            :key="item.id"
            :label="`${item.name} (${item.code})`"
            :value="item.id"
          />
        </el-select>
        <el-button :icon="Refresh" :disabled="!machineTypeId" @click="loadAll">刷新</el-button>
        <el-button type="primary" :icon="Plus" :disabled="!machineTypeId" @click="openCreateRoot">根状态</el-button>
      </div>
    </div>

    <el-empty v-if="!machineTypeId" description="先选择一个设备类型" />

    <div v-else class="workspace-grid">
      <section class="panel">
        <div class="panel-header">
          <span>状态树</span>
          <el-tag size="small" type="info">{{ nodes.length }} 个节点</el-tag>
        </div>
        <el-input v-model="keyword" placeholder="搜索编码或名称" clearable class="search-input" />
        <el-tree
          v-loading="loading"
          :data="filteredTree"
          node-key="id"
          default-expand-all
          highlight-current
          :expand-on-click-node="false"
          @node-click="selectNode"
        >
          <template #default="{ data }">
            <div class="tree-row">
              <span class="tree-title">{{ data.name }}</span>
              <el-tag size="small" :type="data.isLeaf ? 'success' : 'info'">
                {{ data.isLeaf ? '原子' : '状态包' }}
              </el-tag>
            </div>
          </template>
        </el-tree>
      </section>

      <section class="panel">
        <div class="panel-header">
          <span>{{ selectedNode ? selectedNode.name : '节点详情' }}</span>
          <div class="header-actions">
            <el-button v-if="selectedNode" size="small" :icon="Plus" @click="openCreateChild(selectedNode)">子节点</el-button>
            <el-button v-if="selectedNode" size="small" @click="openEdit(selectedNode)">编辑</el-button>
            <el-button v-if="selectedNode" size="small" type="danger" @click="removeSelected">删除</el-button>
          </div>
        </div>

        <el-empty v-if="!selectedNode" description="从左侧选择状态节点" />
        <template v-else>
          <div class="detail-stack">
            <el-descriptions :column="2" size="small" border>
              <el-descriptions-item label="编码">{{ selectedNode.code }}</el-descriptions-item>
              <el-descriptions-item label="层级">{{ selectedNode.level }}</el-descriptions-item>
              <el-descriptions-item label="类型">
                {{ selectedNode.isLeaf ? '原子状态' : '状态包' }}
              </el-descriptions-item>
              <el-descriptions-item label="启用">
                {{ selectedNode.is_active ? '是' : '否' }}
              </el-descriptions-item>
            </el-descriptions>

            <div v-if="selectedNode.isLeaf" class="fact-box">
              <span>业务状态维度</span>
              <strong>{{ atomicFactLabel(selectedNode) }} = {{ selectedNode.target_value || '-' }}</strong>
            </div>
            <div v-else class="fact-box">
              <span>展开为</span>
              <strong>{{ leafCount(selectedNode) }} 个原子状态</strong>
            </div>

            <el-table :data="preview.goal_facts || []" size="small" border>
              <el-table-column prop="state_node_code" label="原子状态" width="150" />
              <el-table-column label="业务状态维度">
                <template #default="{ row }">{{ dimensionLabel(row.feature_key) }}</template>
              </el-table-column>
              <el-table-column prop="target_value" label="目标值" width="120" />
            </el-table>
          </div>
        </template>
      </section>

      <section class="panel">
        <div class="panel-header">
          <span>关系与风险</span>
          <el-tag size="small" :type="blockingDiagnostics.length ? 'danger' : 'success'">
            {{ blockingDiagnostics.length ? '需处理' : '可保存' }}
          </el-tag>
        </div>
        <el-alert
          v-if="selectedNode && !selectedNode.isLeaf"
          title="状态包只表达聚合目标，求解前会展开为包下所有原子状态。"
          type="info"
          :closable="false"
          class="risk-alert"
        />
        <el-alert
          v-if="selectedNode?.isLeaf"
          title="原子状态绑定一个业务状态维度的二元取值；维度在“状态维度”页统一维护。"
          type="success"
          :closable="false"
          class="risk-alert"
        />
        <el-table :data="preview.diagnostics || []" size="small" border>
          <el-table-column prop="severity" label="级别" width="80" />
          <el-table-column prop="code" label="诊断" width="170" />
          <el-table-column prop="message" label="说明" show-overflow-tooltip />
        </el-table>
      </section>
    </div>

    <el-drawer v-model="drawerVisible" :title="drawerTitle" size="480px">
      <el-form :model="form" label-width="112px" @submit.prevent>
        <el-form-item label="父节点" v-if="form.level > 1">
          <el-tree-select
            v-model="form.parent_id"
            :data="treeRows"
            node-key="id"
            :props="treeProps"
            check-strictly
            filterable
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="节点类型">
          <el-segmented
            v-model="form.state_kind"
            :options="[
              { label: '状态包', value: 'aggregate' },
              { label: '原子状态', value: 'atomic' },
            ]"
            :disabled="formHasChildren"
          />
        </el-form-item>
        <template v-if="form.state_kind !== 'aggregate'">
          <el-form-item label="状态对象" required>
            <el-input v-model="form.state_object_name" placeholder="例如 模块A / 管线1 / 控制柜" />
          </el-form-item>
          <el-form-item label="通用状态维度" required>
            <el-select
              v-model="form.dimension_template_key"
              placeholder="选择已配置的通用状态维度"
              filterable
              default-first-option
              clearable
              style="width: 100%"
              @change="onDimensionTemplateChange"
            >
              <el-option
                v-for="item in dimensionTemplates"
                :key="item.feature_key"
                :label="item.feature_name || item.feature_key"
                :value="item.feature_key"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="目标取值" required>
            <el-select
              v-model="form.target_value"
              placeholder="选择当前原子状态对应的取值"
              default-first-option
              clearable
              :disabled="targetOptions.length < 2"
              style="width: 100%"
            >
              <el-option
                v-for="value in targetOptions"
                :key="value"
                :label="value"
                :value="value"
              />
            </el-select>
          </el-form-item>
        </template>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" style="width: 100%" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="drawerVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import {
  createFeatureDef,
  createStateNode,
  deleteStateNode,
  getFeatureDefs,
  getMachineTypes,
  getStateNodes,
  previewLayeredExpansion,
  updateFeatureDef,
  updateStateNode,
} from '../../api/masterData'
import { buildHierarchyTree, treeSelectProps } from '../../utils/hierarchyTree'

const treeProps = treeSelectProps
const machineTypes = ref([])
const machineTypeId = ref(null)
const nodes = ref([])
const featureDefs = ref([])
const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const selectedNode = ref(null)
const preview = ref({ goal_facts: [], diagnostics: [] })
const drawerVisible = ref(false)
const editId = ref(null)
const form = ref(defaultForm())

const selectedMachineType = computed(() =>
  machineTypes.value.find((item) => item.id === machineTypeId.value) || null,
)
const nodeById = computed(() => new Map(nodes.value.map((item) => [item.id, item])))
const childIds = computed(() => {
  const map = new Map()
  for (const item of nodes.value) {
    if (!map.has(item.parent_id)) map.set(item.parent_id, [])
    map.get(item.parent_id).push(item.id)
  }
  return map
})
const enrichedNodes = computed(() =>
  nodes.value.map((item) => ({
    ...item,
    isLeaf: !(childIds.value.get(item.id) || []).length,
  })),
)
const treeRows = computed(() => buildHierarchyTree(enrichedNodes.value))
const filteredTree = computed(() => {
  const text = keyword.value.trim().toLowerCase()
  if (!text) return treeRows.value
  const keep = (items) =>
    items
      .map((item) => ({ ...item, children: keep(item.children || []) }))
      .filter((item) =>
        item.code.toLowerCase().includes(text) ||
        item.name.toLowerCase().includes(text) ||
        item.children.length,
      )
  return keep(treeRows.value)
})
const blockingDiagnostics = computed(() =>
  (preview.value.diagnostics || []).filter((item) => item.severity === 'error'),
)
const drawerTitle = computed(() => (editId.value ? '编辑状态节点' : '新增状态节点'))
const formHasChildren = computed(() => !!editId.value && !!(childIds.value.get(editId.value) || []).length)
const featureDefByKey = computed(() =>
  new Map(featureDefs.value.map((item) => [item.feature_key, item])),
)
const dimensionTemplates = computed(() => featureDefs.value.filter(isDimensionTemplate))
const selectedFeatureDef = computed(() =>
  featureDefByKey.value.get(form.value.dimension_template_key) || null,
)
const targetOptions = computed(() => normalizeAllowedValues(selectedFeatureDef.value?.allowed_values))

function defaultForm() {
  return {
    machine_type_id: machineTypeId.value,
    parent_id: null,
    level: 1,
    code: '',
    name: '',
    feature_key: '',
    dimension_template_key: '',
    state_object_name: '',
    operator: 'eq',
    target_value: '',
    state_kind: 'aggregate',
    sort_order: 0,
    is_active: true,
    metadata_json: null,
  }
}

function normalizeAllowedValues(values) {
  if (Array.isArray(values)) return values.map((item) => String(item).trim()).filter(Boolean)
  if (typeof values === 'string') {
    try {
      const parsed = JSON.parse(values)
      if (Array.isArray(parsed)) return parsed.map((item) => String(item).trim()).filter(Boolean)
    } catch {
      return values.split(',').map((item) => item.trim()).filter(Boolean)
    }
  }
  return []
}

function isDimensionTemplate(def) {
  return String(def?.feature_key || '').includes('_dim_') &&
    !String(def?.feature_key || '').includes('__')
}

function normalizeCodeToken(value, fallback) {
  const token = String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^0-9a-z]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '')
  return token || fallback
}

function buildConcreteFeatureKey(templateKey, objectName) {
  const objectToken = normalizeCodeToken(objectName, 'object')
  const prefix = `${templateKey}__`
  const maxObjectLength = Math.max(1, 64 - prefix.length)
  return `${prefix}${objectToken.slice(0, maxObjectLength).replace(/^_+|_+$/g, '') || 'object'}`
}

function dimensionLabel(featureKey) {
  if (!featureKey) return '-'
  const def = featureDefByKey.value.get(featureKey)
  const templateKey = String(featureKey).split('__')[0]
  const template = featureDefByKey.value.get(templateKey)
  return def?.feature_name || template?.feature_name || featureKey
}

function atomicFactLabel(node) {
  if (!node?.feature_key) return '-'
  const objectName = node.metadata_json?.state_object_name
  const templateKey = node.metadata_json?.dimension_template_key || String(node.feature_key).split('__')[0]
  const template = featureDefByKey.value.get(templateKey)
  const templateName = template?.feature_name || dimensionLabel(node.feature_key)
  return objectName ? `${objectName} / ${templateName}` : templateName
}

function onDimensionTemplateChange() {
  form.value.target_value = ''
}

function leafCount(node) {
  if (!node) return 0
  const children = childIds.value.get(node.id) || []
  if (!children.length) return 1
  return children.reduce((sum, id) => sum + leafCount(nodeById.value.get(id)), 0)
}

async function loadAll() {
  if (!machineTypeId.value) return
  loading.value = true
  try {
    const [stateNodes, defs] = await Promise.all([
      getStateNodes(machineTypeId.value),
      getFeatureDefs(machineTypeId.value),
    ])
    nodes.value = stateNodes
    featureDefs.value = defs
    if (selectedNode.value) {
      selectedNode.value = enrichedNodes.value.find((item) => item.id === selectedNode.value.id) || null
    }
    await loadPreview()
  } finally {
    loading.value = false
  }
}

async function onTypeChange() {
  selectedNode.value = null
  featureDefs.value = []
  preview.value = { goal_facts: [], diagnostics: [] }
  await loadAll()
}

async function selectNode(node) {
  selectedNode.value = node
  await loadPreview()
}

async function loadPreview() {
  if (!machineTypeId.value || !selectedNode.value) return
  preview.value = await previewLayeredExpansion(machineTypeId.value, {
    target_state_node_ids: [selectedNode.value.id],
    activity_scope_node_ids: [],
    include_inactive: false,
  })
}

function openCreateRoot() {
  editId.value = null
  form.value = { ...defaultForm(), level: 1, parent_id: null }
  drawerVisible.value = true
}

function openCreateChild(parent) {
  editId.value = null
  form.value = {
    ...defaultForm(),
    parent_id: parent.id,
    level: parent.level + 1,
    sort_order: (childIds.value.get(parent.id) || []).length + 10,
  }
  drawerVisible.value = true
}

function openEdit(node) {
  editId.value = node.id
  const inferredTemplateKey = node.metadata_json?.dimension_template_key ||
    (String(node.feature_key || '').includes('__') ? String(node.feature_key).split('__')[0] : '')
  form.value = {
    ...defaultForm(),
    ...node,
    dimension_template_key: inferredTemplateKey,
    state_object_name: node.metadata_json?.state_object_name || '',
    state_kind: node.isLeaf && node.feature_key ? 'atomic' : 'aggregate',
  }
  drawerVisible.value = true
}

async function syncConcreteFeatureDef(featureKey, featureName, allowedValues) {
  const existing = featureDefByKey.value.get(featureKey)
  const payload = {
    feature_key: featureKey,
    feature_name: featureName,
    value_type: 'enum',
    allowed_values: allowedValues,
  }
  if (existing) {
    const updated = await updateFeatureDef(existing.id, payload)
    featureDefs.value = featureDefs.value.map((item) => (item.id === updated.id ? updated : item))
    return updated
  }
  const created = await createFeatureDef(machineTypeId.value, {
    machine_type_id: machineTypeId.value,
    ...payload,
  })
  featureDefs.value = [...featureDefs.value, created]
  return created
}

async function save() {
  if (!form.value.name.trim()) {
    return ElMessage.warning('名称不能为空')
  }
  if (form.value.level > 1 && !form.value.parent_id) {
    return ElMessage.warning('非根节点必须选择父节点')
  }
  const isAtomic = form.value.state_kind !== 'aggregate'
  const stateObjectName = String(form.value.state_object_name || '').trim()
  const templateKey = String(form.value.dimension_template_key || '').trim()
  const template = featureDefByKey.value.get(templateKey)
  const featureKey = isAtomic ? buildConcreteFeatureKey(templateKey, stateObjectName) : ''
  const targetValue = String(form.value.target_value || '').trim()
  if (isAtomic && !stateObjectName) {
    return ElMessage.warning('原子状态需要填写状态对象')
  }
  if (isAtomic && !templateKey) {
    return ElMessage.warning('原子状态需要选择通用状态维度')
  }
  if (isAtomic && targetOptions.value.length !== 2) {
    return ElMessage.warning('通用状态维度需要先配置两个二元取值')
  }
  if (isAtomic && !targetOptions.value.includes(targetValue)) {
    return ElMessage.warning('目标取值必须从该通用状态维度的二元取值中选择')
  }
  saving.value = true
  try {
    if (isAtomic) {
      await syncConcreteFeatureDef(
        featureKey,
        `${stateObjectName} / ${template?.feature_name || templateKey}`,
        targetOptions.value,
      )
    }
    const payload = {
      machine_type_id: machineTypeId.value,
      parent_id: form.value.level === 1 ? null : form.value.parent_id,
      level: form.value.level,
      name: form.value.name.trim(),
      feature_key: isAtomic ? featureKey : null,
      operator: 'eq',
      target_value: isAtomic ? targetValue : null,
      state_kind: isAtomic ? 'atomic' : 'aggregate',
      sort_order: form.value.sort_order,
      is_active: form.value.is_active,
      metadata_json: isAtomic
        ? {
            ...(form.value.metadata_json || {}),
            state_object_name: stateObjectName,
            dimension_template_key: templateKey,
          }
        : null,
    }
    if (editId.value) await updateStateNode(editId.value, payload)
    else await createStateNode(machineTypeId.value, payload)
    ElMessage.success('状态节点已保存')
    drawerVisible.value = false
    await loadAll()
  } finally {
    saving.value = false
  }
}

async function removeSelected() {
  if (!selectedNode.value) return
  await ElMessageBox.confirm('确认删除当前状态节点？', '确认', { type: 'warning' })
  await deleteStateNode(selectedNode.value.id)
  selectedNode.value = null
  await loadAll()
}

onMounted(async () => {
  machineTypes.value = await getMachineTypes()
})
</script>

<style scoped>
.state-workspace {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.workspace-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.workspace-toolbar h2 {
  margin: 0 0 6px;
  font-size: 20px;
}
.workspace-toolbar p {
  margin: 0;
  color: #606266;
}
.toolbar-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}
.workspace-grid {
  display: grid;
  grid-template-columns: minmax(280px, 0.9fr) minmax(360px, 1.2fr) minmax(300px, 0.9fr);
  gap: 14px;
}
.panel {
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  padding: 12px;
  min-height: 520px;
  background: #fff;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
  font-weight: 600;
}
.header-actions {
  display: flex;
  gap: 6px;
}
.search-input {
  margin-bottom: 10px;
}
.tree-row {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-right: 8px;
}
.tree-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.detail-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.fact-box {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.fact-box span {
  color: #606266;
  font-size: 13px;
}
.binary-values {
  width: 100%;
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}
.risk-alert {
  margin-bottom: 12px;
}
@media (max-width: 1200px) {
  .workspace-grid {
    grid-template-columns: 1fr;
  }
}
</style>
