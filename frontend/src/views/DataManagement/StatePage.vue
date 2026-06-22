<template>
  <div class="state-page">
    <h2>状态管理</h2>

    <el-card>
      <el-form :model="form" label-position="top" @submit.prevent>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="设备" required>
              <el-select
                v-model="form.machine_id"
                placeholder="请选择设备"
                filterable
                style="width:100%"
                @change="onMachineChange"
              >
                <el-option
                  v-for="m in machines"
                  :key="m.id"
                  :label="`${m.name} (${m.code})`"
                  :value="m.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="状态类型" required>
              <el-select v-model="form.state_type" style="width:100%">
                <el-option value="current" label="当前状态" />
                <el-option value="target" label="目标状态" />
                <el-option value="snapshot" label="快照" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="7">
            <el-form-item label="状态名称">
              <el-input v-model="form.label" placeholder="可选，便于识别" />
            </el-form-item>
          </el-col>
          <el-col :span="4">
            <el-form-item label="操作">
              <div class="button-row">
                <el-button type="primary" :loading="saving" :disabled="!form.machine_id" @click="save">保存</el-button>
                <el-button @click="reset">清空</el-button>
              </div>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <el-row :gutter="16" class="state-workbench">
      <el-col :span="15">
        <el-card v-loading="loading">
          <template #header>
            <div class="card-header">
              <span>状态特征</span>
              <el-tag v-if="editId" type="primary" size="small">编辑中</el-tag>
            </div>
          </template>
          <el-empty v-if="!form.machine_id" description="请先选择设备" />
          <el-empty v-else-if="!featureDefs.length" description="该设备类型未配置特征定义" />
          <div v-else class="feature-groups">
            <div v-for="group in featureGroups" :key="group.key" class="feature-group">
              <div class="group-title">
                <span>{{ group.title }}</span>
                <el-tag v-if="group.kind" size="small" type="info">{{ group.kind }}</el-tag>
              </div>
              <el-table :data="group.rows" size="small" border>
                <el-table-column label="状态/特征" min-width="210" show-overflow-tooltip>
                  <template #default="{ row }">
                    <div class="feature-name">{{ row.label }}</div>
                    <div class="feature-key">{{ row.feature_key }}</div>
                  </template>
                </el-table-column>
                <el-table-column label="参考目标" min-width="150" show-overflow-tooltip>
                  <template #default="{ row }">{{ row.targetHint || '-' }}</template>
                </el-table-column>
                <el-table-column label="取值" min-width="220">
                  <template #default="{ row }">
                    <el-select
                      v-if="row.value_type === 'enum'"
                      v-model="form.features[row.feature_key]"
                      style="width:100%"
                      clearable
                    >
                      <el-option
                        v-for="v in normalizeAllowedValues(row.allowed_values)"
                        :key="v"
                        :value="v"
                        :label="v"
                      />
                    </el-select>
                    <el-select
                      v-else-if="row.value_type === 'boolean'"
                      v-model="form.features[row.feature_key]"
                      style="width:100%"
                      clearable
                    >
                      <el-option value="true" label="是 (true)" />
                      <el-option value="false" label="否 (false)" />
                    </el-select>
                    <el-input
                      v-else-if="row.value_type === 'number'"
                      v-model="form.features[row.feature_key]"
                      type="number"
                      :placeholder="row.unit || 'number'"
                    />
                    <el-input
                      v-else
                      v-model="form.features[row.feature_key]"
                      placeholder="字符串值"
                    />
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="9">
        <el-card v-loading="loading">
          <template #header>状态快照</template>
          <el-empty v-if="!form.machine_id" description="请先选择设备" />
          <el-table v-else :data="list" size="small" border stripe>
            <el-table-column prop="label" label="状态名称" min-width="120" show-overflow-tooltip />
            <el-table-column prop="state_type" label="类型" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="stateTypeColor(row.state_type)">{{ row.state_type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="特征" width="70">
              <template #default="{ row }">{{ Object.keys(row.features || {}).length }}</template>
            </el-table-column>
            <el-table-column label="操作" width="130" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="editRow(row)">编辑</el-button>
                <el-button size="small" type="danger" @click="remove(row.state_id)">删除</el-button>
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
  createState,
  deleteState,
  getFeatureDefs,
  getMachines,
  getMachineTypes,
  getStateNodes,
  getStates,
  updateState,
} from '../../api/masterData'
import { buildHierarchyTree } from '../../utils/hierarchyTree'

const machines = ref([])
const machineTypes = ref([])
const featureDefs = ref([])
const stateNodes = ref([])
const list = ref([])
const loading = ref(false)
const saving = ref(false)
const editId = ref(null)

const form = ref({
  machine_id: null,
  state_type: 'current',
  label: '',
  features: {},
})

const featureDefByKey = computed(() =>
  new Map(featureDefs.value.map((fd) => [fd.feature_key, fd])),
)

const featureGroups = computed(() => {
  const used = new Set()
  const tree = buildHierarchyTree(stateNodes.value)
  const groups = []
  const collectLeafRows = (node) => {
    if (node.level === 3 && node.feature_key) {
      const fd = featureDefByKey.value.get(node.feature_key)
      if (!fd) return []
      used.add(node.feature_key)
      return [{
        ...fd,
        label: node.name,
        feature_key: node.feature_key,
        targetHint: `${node.operator || 'eq'} ${node.target_value ?? ''}`.trim(),
      }]
    }
    return (node.children || []).flatMap(collectLeafRows)
  }

  for (const root of tree) {
    for (const group of root.children || []) {
      const rows = collectLeafRows(group)
      if (rows.length) {
        groups.push({
          key: `group-${group.id}`,
          title: `${root.name} / ${group.name}`,
          kind: '状态层级',
          rows,
        })
      }
    }
    const directRows = root.children?.length ? [] : collectLeafRows(root)
    if (directRows.length) {
      groups.push({
        key: `root-${root.id}`,
        title: root.name,
        kind: '状态层级',
        rows: directRows,
      })
    }
  }

  const uncategorized = featureDefs.value
    .filter((fd) => !used.has(fd.feature_key))
    .map((fd) => ({
      ...fd,
      label: fd.feature_name || fd.feature_key,
      targetHint: '',
    }))
  if (uncategorized.length) {
    groups.push({
      key: 'uncategorized',
      title: '未归类特征',
      kind: 'FeatureDefs',
      rows: uncategorized,
    })
  }
  return groups
})

function stateTypeColor(t) {
  return { current: 'primary', target: 'success', snapshot: 'info' }[t] ?? ''
}

function normalizeAllowedValues(allowedValues) {
  if (Array.isArray(allowedValues)) return allowedValues
  if (Array.isArray(allowedValues?.values)) return allowedValues.values
  if (typeof allowedValues === 'string') return allowedValues.split(',').map((item) => item.trim()).filter(Boolean)
  return []
}

async function onMachineChange() {
  editId.value = null
  featureDefs.value = []
  stateNodes.value = []
  form.value.features = {}
  if (!form.value.machine_id) {
    list.value = []
    return
  }

  const machine = machines.value.find((m) => m.id === form.value.machine_id)
  if (!machine?.machine_type_id) return

  loading.value = true
  try {
    const [defs, hierarchy, states] = await Promise.all([
      getFeatureDefs(machine.machine_type_id),
      getStateNodes(machine.machine_type_id),
      getStates(form.value.machine_id),
    ])
    featureDefs.value = defs
    stateNodes.value = hierarchy
    list.value = states.states ?? []
    form.value.features = Object.fromEntries(defs.map((fd) => [fd.feature_key, '']))
  } catch {
    featureDefs.value = []
    stateNodes.value = []
    list.value = []
    form.value.features = {}
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!form.value.machine_id) return ElMessage.warning('请先选择设备')
  saving.value = true
  try {
    const payload = {
      machine_id: form.value.machine_id,
      state_type: form.value.state_type,
      label: form.value.label.trim() || null,
      features: Object.fromEntries(
        Object.entries(form.value.features).filter(([, value]) => value !== '' && value != null),
      ),
    }
    if (editId.value) {
      await updateState(editId.value, { state_type: payload.state_type, label: payload.label, features: payload.features })
    } else {
      await createState(form.value.machine_id, payload)
    }
    ElMessage.success('状态已保存')
    const machineId = form.value.machine_id
    reset()
    form.value.machine_id = machineId
    await onMachineChange()
  } finally {
    saving.value = false
  }
}

function editRow(row) {
  editId.value = row.state_id
  form.value.state_type = row.state_type
  form.value.label = row.label ?? ''
  const merged = Object.fromEntries(featureDefs.value.map((fd) => [fd.feature_key, '']))
  Object.assign(merged, row.features ?? {})
  form.value.features = merged
}

async function remove(id) {
  await ElMessageBox.confirm('确定删除这个状态吗？', '确认', { type: 'warning' })
  await deleteState(id)
  ElMessage.success('已删除')
  await onMachineChange()
}

function reset() {
  editId.value = null
  form.value.state_type = 'current'
  form.value.label = ''
  form.value.features = Object.fromEntries(featureDefs.value.map((fd) => [fd.feature_key, '']))
}

onMounted(async () => {
  try {
    ;[machines.value, machineTypes.value] = await Promise.all([getMachines(), getMachineTypes()])
  } catch {
    machines.value = []
    machineTypes.value = []
  }
})
</script>

<style scoped>
.state-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.state-page h2 {
  margin: 0;
  font-size: 18px;
}

.state-workbench {
  align-items: flex-start;
}

.button-row {
  display: flex;
  gap: 8px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.feature-groups {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-weight: 600;
}

.feature-name {
  font-weight: 500;
}

.feature-key {
  margin-top: 2px;
  color: #909399;
  font-size: 12px;
}
</style>
