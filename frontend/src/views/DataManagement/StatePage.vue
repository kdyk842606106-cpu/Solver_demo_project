<!-- 4-3: StatePage — value_type-aware feature input controls -->
<template>
  <div>
    <h2>状态管理</h2>
    <el-row :gutter="16">
      <!-- Form -->
      <el-col :span="10">
        <el-card>
          <el-form :model="form" label-width="80px" @submit.prevent>
            <el-form-item label="设备" required>
              <el-select
                v-model="form.machine_id"
                placeholder="请选择设备"
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
            <el-form-item label="状态类型" required>
              <el-select v-model="form.state_type" style="width:100%">
                <el-option value="current" label="当前状态 (current)" />
                <el-option value="target" label="目标状态 (target)" />
                <el-option value="snapshot" label="快照 (snapshot)" />
              </el-select>
            </el-form-item>
            <el-form-item label="状态名称">
              <el-input v-model="form.label" placeholder="可选，便于识别" />
            </el-form-item>

            <!-- Dynamic feature fields — controlled by value_type (ANCHOR: no hardcoding) -->
            <template v-if="featureDefs.length > 0">
              <el-divider content-position="left">状态特征</el-divider>
              <el-form-item
                v-for="fd in featureDefs"
                :key="fd.feature_key"
                :label="fd.feature_name || fd.feature_key"
              >
                <!-- enum: select from allowed_values -->
                <el-select
                  v-if="fd.value_type === 'enum'"
                  v-model="form.features[fd.feature_key]"
                  style="width:100%"
                  clearable
                >
                  <el-option
                    v-for="v in (fd.allowed_values?.values ?? [])"
                    :key="v"
                    :value="v"
                    :label="v"
                  />
                </el-select>
                <!-- boolean: true/false select -->
                <el-select
                  v-else-if="fd.value_type === 'boolean'"
                  v-model="form.features[fd.feature_key]"
                  style="width:100%"
                  clearable
                >
                  <el-option value="true" label="是 (true)" />
                  <el-option value="false" label="否 (false)" />
                </el-select>
                <!-- number: numeric input -->
                <el-input
                  v-else-if="fd.value_type === 'number'"
                  v-model="form.features[fd.feature_key]"
                  type="number"
                  :placeholder="`${fd.unit ? fd.unit : ''}`"
                />
                <!-- string: text input -->
                <el-input
                  v-else
                  v-model="form.features[fd.feature_key]"
                  placeholder="字符串值"
                />
              </el-form-item>
            </template>
            <el-empty v-else-if="form.machine_id" description="该设备类型未配置特征定义" :image-size="60" />

            <el-form-item>
              <el-button type="primary" :loading="saving" @click="save">保存</el-button>
              <el-button @click="reset">清空</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- Table -->
      <el-col :span="14">
        <el-card v-loading="loading">
          <el-empty v-if="!form.machine_id" description="请先选择设备" />
          <el-table v-else :data="list" size="small" border stripe>
            <el-table-column prop="label" label="状态名称" />
            <el-table-column prop="state_type" label="类型" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="stateTypeColor(row.state_type)">{{ row.state_type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="特征摘要" show-overflow-tooltip>
              <template #default="{ row }">
                {{ Object.entries(row.features || {}).map(([k, v]) => `${k}: ${v}`).join(' | ') }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="140" fixed="right">
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
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getMachines,
  getMachineTypes,
  getFeatureDefs,
  getStates,
  createState,
  updateState,
  deleteState,
} from '../../api/masterData'

const machines = ref([])
const machineTypes = ref([])
const featureDefs = ref([])
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

function stateTypeColor(t) {
  return { current: 'primary', target: 'success', snapshot: 'info' }[t] ?? ''
}

async function onMachineChange() {
  editId.value = null
  featureDefs.value = []
  form.value.features = {}
  if (!form.value.machine_id) { list.value = []; return }

  const machine = machines.value.find((m) => m.id === form.value.machine_id)
  if (machine) {
    featureDefs.value = await getFeatureDefs(machine.machine_type_id)
    // Initialize feature fields to empty string
    form.value.features = Object.fromEntries(featureDefs.value.map((fd) => [fd.feature_key, '']))
  }

  loading.value = true
  try { const res = await getStates(form.value.machine_id); list.value = res.states ?? [] }
  finally { loading.value = false }
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
        Object.entries(form.value.features).filter(([, v]) => v !== '' && v != null)
      ),
    }
    if (editId.value) {
      await updateState(editId.value, { state_type: payload.state_type, label: payload.label, features: payload.features })
    } else {
      await createState(form.value.machine_id, payload)
    }
    ElMessage.success('状态已保存')
    const mid = form.value.machine_id
    reset()
    form.value.machine_id = mid
    await onMachineChange()
  } finally { saving.value = false }
}

function editRow(row) {
  editId.value = row.state_id
  form.value.state_type = row.state_type
  form.value.label = row.label ?? ''
  // Merge existing feature values
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
  ;[machines.value, machineTypes.value] = await Promise.all([getMachines(), getMachineTypes()])
})
</script>
