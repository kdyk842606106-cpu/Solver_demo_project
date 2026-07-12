<template>
  <div>
    <h2>作用域约束</h2>
    <el-row :gutter="16">
      <el-col :span="10">
        <el-card>
          <el-form :model="form" label-width="110px" @submit.prevent>
            <el-form-item label="设备类型" required>
              <el-select v-model="machineTypeId" style="width:100%" @change="onTypeChange">
                <el-option
                  v-for="mt in machineTypes"
                  :key="mt.id"
                  :label="`${mt.name} (${mt.code})`"
                  :value="mt.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="活动作用域" required>
              <el-tree-select
                v-model="form.activity_node_id"
                :data="activityTreeOptions"
                :props="treeProps"
                node-key="id"
                check-strictly
                style="width:100%"
                filterable
                @change="loadGuards"
              />
            </el-form-item>
            <el-form-item label="约束名称" required>
              <el-input v-model="form.name" placeholder="例如 进入真空维修前置" />
            </el-form-item>
            <el-form-item label="说明">
              <el-input v-model="form.description" type="textarea" :rows="2" />
            </el-form-item>
            <el-form-item label="启用">
              <el-switch v-model="form.is_active" />
            </el-form-item>

            <el-divider content-position="left">
              前置状态
              <el-button size="small" style="margin-left:8px" @click="addPrecondition">+ 新增</el-button>
            </el-divider>
            <div v-for="(pre, index) in form.preconditions" :key="index" class="dynamic-row">
              <el-row :gutter="8" align="middle">
                <el-col :span="12">
                  <el-tree-select
                    v-model="pre.state_node_id"
                    :data="stateTreeOptions"
                    :props="treeProps"
                    node-key="id"
                    check-strictly
                    size="small"
                    style="width:100%"
                    filterable
                  />
                </el-col>
                <el-col :span="5">
                  <el-select v-model="pre.operator" size="small" style="width:100%">
                    <el-option value="completed" label="完成" />
                    <el-option value="eq" label="=" />
                    <el-option value="gte" label="≥" />
                    <el-option value="lte" label="≤" />
                  </el-select>
                </el-col>
                <el-col :span="5">
                  <el-input
                    v-model="pre.expected_value"
                    size="small"
                    :disabled="pre.operator === 'completed'"
                    placeholder="值"
                  />
                </el-col>
                <el-col :span="2">
                  <el-button size="small" type="danger" circle @click="form.preconditions.splice(index, 1)">
                    ×
                  </el-button>
                </el-col>
              </el-row>
            </div>

            <el-form-item>
              <el-button type="primary" :loading="saving" @click="save">保存</el-button>
              <el-button @click="reset">清空</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="14">
        <el-card v-loading="loading">
          <el-empty v-if="!form.activity_node_id" description="请先选择活动作用域" />
          <el-table v-else :data="guards" size="small" border stripe>
            <el-table-column prop="name" label="名称" width="180" show-overflow-tooltip />
            <el-table-column label="前置状态" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.preconditions.map(formatPrecondition).join('；') }}
              </template>
            </el-table-column>
            <el-table-column label="状态" width="70">
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
  createScopeGuard,
  deleteScopeGuard,
  getActivityNodes,
  getMachineTypes,
  getScopeGuards,
  getStateNodes,
  updateScopeGuard,
} from '../../api/masterData'
import { buildHierarchyTree, treeSelectProps } from '../../utils/hierarchyTree'

const machineTypes = ref([])
const activityNodes = ref([])
const stateNodes = ref([])
const guards = ref([])
const machineTypeId = ref(null)
const loading = ref(false)
const saving = ref(false)
const editId = ref(null)

const form = ref(defaultForm())
const treeProps = treeSelectProps
const activityTreeOptions = computed(() =>
  buildHierarchyTree(activityNodes.value, { disabled: (node) => node.level > 2 }),
)

const selectedActivity = computed(() =>
  activityNodes.value.find((node) => node.id === form.value.activity_node_id)
)

const stateTreeOptions = computed(() =>
  buildHierarchyTree(stateNodes.value, {
    disabled: (node) => selectedActivity.value?.level === 1 ? node.level !== 1 : false,
  }),
)

function defaultForm(activityNodeId = null) {
  return {
    activity_node_id: activityNodeId,
    name: '',
    description: '',
    is_active: true,
    metadata_json: null,
    preconditions: [newPrecondition()],
  }
}

function newPrecondition() {
  return { state_node_id: null, operator: 'completed', expected_value: null, value_list: null }
}

function formatPrecondition(item) {
  const value = item.operator === 'completed' ? '完成' : `${item.operator} ${item.expected_value ?? ''}`
  return `${item.state_node_code || item.state_node_id}: ${value}`
}

function addPrecondition() {
  form.value.preconditions.push(newPrecondition())
}

async function onTypeChange() {
  form.value = defaultForm()
  guards.value = []
  if (!machineTypeId.value) {
    activityNodes.value = []
    stateNodes.value = []
    return
  }
  const [activities, states] = await Promise.all([
    getActivityNodes(machineTypeId.value),
    getStateNodes(machineTypeId.value),
  ])
  activityNodes.value = activities
  stateNodes.value = states
}

async function loadGuards() {
  if (!form.value.activity_node_id) {
    guards.value = []
    return
  }
  loading.value = true
  try {
    guards.value = await getScopeGuards(form.value.activity_node_id)
  } catch {
    guards.value = []
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!form.value.activity_node_id || !form.value.name) {
    return ElMessage.warning('活动作用域和约束名称不能为空')
  }
  const preconditions = form.value.preconditions
    .filter((item) => item.state_node_id)
    .map((item) => ({
      state_node_id: item.state_node_id,
      operator: item.operator,
      expected_value: item.operator === 'completed' ? null : item.expected_value,
      value_list: null,
    }))
  if (!preconditions.length) return ElMessage.warning('至少需要一个前置状态')

  saving.value = true
  try {
    const payload = {
      activity_node_id: form.value.activity_node_id,
      name: form.value.name.trim(),
      description: form.value.description.trim() || null,
      is_active: form.value.is_active,
      metadata_json: null,
      preconditions,
    }
    if (editId.value) {
      await updateScopeGuard(editId.value, payload)
    } else {
      await createScopeGuard(form.value.activity_node_id, payload)
    }
    ElMessage.success('作用域约束已保存')
    const activityNodeId = form.value.activity_node_id
    reset()
    form.value.activity_node_id = activityNodeId
    await loadGuards()
  } finally {
    saving.value = false
  }
}

function edit(row) {
  editId.value = row.id
  form.value = {
    activity_node_id: row.activity_node_id,
    name: row.name,
    description: row.description ?? '',
    is_active: row.is_active,
    metadata_json: null,
    preconditions: row.preconditions.length
      ? row.preconditions.map((item) => ({
          state_node_id: item.state_node_id,
          operator: item.operator,
          expected_value: item.expected_value,
          value_list: item.value_list,
        }))
      : [newPrecondition()],
  }
}

async function remove(id) {
  await ElMessageBox.confirm('确定删除这个作用域约束吗？', '确认', { type: 'warning' })
  await deleteScopeGuard(id)
  ElMessage.success('已删除')
  await loadGuards()
}

function reset() {
  editId.value = null
  form.value = defaultForm(form.value.activity_node_id)
}

onMounted(async () => {
  try {
    machineTypes.value = await getMachineTypes()
  } catch {
    machineTypes.value = []
  }
})
</script>

<style scoped>
.dynamic-row {
  margin-bottom: 8px;
}
</style>
