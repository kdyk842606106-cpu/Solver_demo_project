<!-- 4-1: FeatureDefinitionPage — manages StateFeatureDef per machine type -->
<template>
  <div>
    <h2>特征定义</h2>
    <el-row :gutter="16">
      <!-- Form -->
      <el-col :span="10">
        <el-card>
          <el-form :model="form" label-width="100px" @submit.prevent>
            <el-form-item label="设备类型" required>
              <el-select
                v-model="form.machine_type_id"
                placeholder="请选择"
                style="width:100%"
                @change="onTypeChange"
              >
                <el-option
                  v-for="mt in machineTypes"
                  :key="mt.id"
                  :label="`${mt.name} (${mt.code})`"
                  :value="mt.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="特征键" required>
              <el-input v-model="form.feature_key" placeholder="例如 pressure_bar" />
            </el-form-item>
            <el-form-item label="显示名称">
              <el-input v-model="form.feature_name" placeholder="例如 压力（bar）" />
            </el-form-item>
            <el-form-item label="值类型" required>
              <el-select v-model="form.value_type" style="width:100%">
                <el-option value="enum" label="枚举（enum）" />
                <el-option value="string" label="字符串（string）" />
                <el-option value="number" label="数字（number）" />
                <el-option value="boolean" label="布尔（boolean）" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="form.value_type === 'enum'" label="枚举值">
              <el-input
                v-model="form.allowedValuesRaw"
                placeholder="逗号分隔，例如 cold,warm,hot"
              />
            </el-form-item>
            <el-form-item label="单位">
              <el-input v-model="form.unit" placeholder="例如 bar、℃" />
            </el-form-item>
            <el-form-item label="说明">
              <el-input v-model="form.description" type="textarea" :rows="2" />
            </el-form-item>
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
          <el-empty v-if="!form.machine_type_id" description="请先选择设备类型" />
          <el-table v-else :data="list" size="small" border stripe>
            <el-table-column prop="feature_key" label="特征键" width="150" />
            <el-table-column prop="feature_name" label="显示名称" />
            <el-table-column prop="value_type" label="值类型" width="100">
              <template #default="{ row }">
                <el-tag size="small" type="info">{{ row.value_type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="枚举值" show-overflow-tooltip>
              <template #default="{ row }">
                {{ normalizeAllowedValues(row.allowed_values).join(', ') }}
              </template>
            </el-table-column>
            <el-table-column prop="unit" label="单位" width="80" />
            <el-table-column label="操作" width="140" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="editRow(row)">编辑</el-button>
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
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getMachineTypes,
  getFeatureDefs,
  createFeatureDef,
  updateFeatureDef,
  deleteFeatureDef,
} from '../../api/masterData'

const list = ref([])
const machineTypes = ref([])
const loading = ref(false)
const saving = ref(false)
const editId = ref(null)

const form = ref({
  machine_type_id: null,
  feature_key: '',
  feature_name: '',
  value_type: 'enum',
  allowedValuesRaw: '',
  unit: '',
  description: '',
})

function normalizeAllowedValues(allowedValues) {
  if (Array.isArray(allowedValues)) return allowedValues
  if (Array.isArray(allowedValues?.values)) return allowedValues.values
  return []
}

async function onTypeChange() {
  editId.value = null
  if (!form.value.machine_type_id) { list.value = []; return }
  loading.value = true
  try {
    list.value = await getFeatureDefs(form.value.machine_type_id)
  } catch {
    list.value = []
  }
  finally { loading.value = false }
}

async function save() {
  if (!form.value.machine_type_id || !form.value.feature_key) {
    return ElMessage.warning('请选择设备类型并填写特征键')
  }
  saving.value = true
  try {
    const vals = form.value.allowedValuesRaw.split(',').map((v) => v.trim()).filter(Boolean)
    const payload = {
      feature_key: form.value.feature_key.trim(),
      feature_name: form.value.feature_name.trim() || null,
      value_type: form.value.value_type,
      allowed_values: form.value.value_type === 'enum' && vals.length ? vals : null,
    }
    if (editId.value) {
      await updateFeatureDef(editId.value, payload)
    } else {
      await createFeatureDef(form.value.machine_type_id, {
        machine_type_id: form.value.machine_type_id,
        ...payload,
      })
    }
    ElMessage.success('特征定义已保存')
    const mtId = form.value.machine_type_id
    reset()
    form.value.machine_type_id = mtId
    await onTypeChange()
  } finally { saving.value = false }
}

function editRow(row) {
  editId.value = row.id
  form.value = {
    machine_type_id: row.machine_type_id,
    feature_key: row.feature_key,
    feature_name: row.feature_name ?? '',
    value_type: row.value_type,
    allowedValuesRaw: normalizeAllowedValues(row.allowed_values).join(', '),
    unit: row.unit ?? '',
    description: row.description ?? '',
  }
}

async function remove(id) {
  await ElMessageBox.confirm('确定删除这个特征定义吗？', '确认', { type: 'warning' })
  await deleteFeatureDef(id)
  ElMessage.success('已删除')
  await onTypeChange()
}

function reset() {
  editId.value = null
  form.value = {
    machine_type_id: form.value.machine_type_id,
    feature_key: '',
    feature_name: '',
    value_type: 'enum',
    allowedValuesRaw: '',
    unit: '',
    description: '',
  }
}

onMounted(async () => {
  try {
    machineTypes.value = await getMachineTypes()
  } catch {
    machineTypes.value = []
  }
})
</script>
