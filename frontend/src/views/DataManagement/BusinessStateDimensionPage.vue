<template>
  <div class="dimension-page">
    <div class="page-toolbar">
      <div>
        <h2>状态维度</h2>
        <p>按设备类型维护二元状态模板，例如模块安装、管线连接、调测验证。</p>
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
        <el-button type="primary" :icon="Plus" :disabled="!machineTypeId" @click="openCreate">
          新建模板
        </el-button>
      </div>
    </div>

    <el-empty v-if="!machineTypeId" description="先选择一个设备类型" />

    <el-table
      v-else
      v-loading="loading"
      :data="dimensions"
      empty-text="当前机型未配置状态维度模板"
      border
      size="small"
      class="dimension-table"
    >
      <el-table-column prop="feature_name" label="状态维度" min-width="180">
        <template #default="{ row }">{{ row.feature_name || row.feature_key }}</template>
      </el-table-column>
      <el-table-column label="二元取值" min-width="220">
        <template #default="{ row }">
          <div class="value-tags">
            <el-tag
              v-for="value in normalizeAllowedValues(row.allowed_values)"
              :key="value"
              size="small"
              type="info"
            >
              {{ value }}
            </el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="原子状态引用" width="120">
        <template #default="{ row }">{{ usageCount(row.feature_key) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button
            size="small"
            type="danger"
            :disabled="usageCount(row.feature_key) > 0"
            @click="remove(row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-drawer v-model="drawerVisible" :title="editId ? '编辑状态维度' : '新建状态维度'" size="440px">
      <el-form :model="form" label-width="104px" @submit.prevent>
        <el-form-item label="维度名称" required>
          <el-input v-model="form.feature_name" placeholder="例如 模块安装 / 管线连接 / 调测验证" />
        </el-form-item>
        <el-form-item label="二元取值" required>
          <div class="binary-values">
            <el-input v-model="form.allowed_values[0]" placeholder="取值 1，例如 已安装 / 已连接" />
            <el-input v-model="form.allowed_values[1]" placeholder="取值 2，例如 未安装 / 未连接" />
          </div>
        </el-form-item>
        <el-alert
          v-if="editId && usedValues.length"
          :closable="false"
          type="info"
          class="usage-alert"
          :title="`已有原子状态正在使用：${usedValues.join('、')}`"
        />
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
  deleteFeatureDef,
  getFeatureDefs,
  getMachineTypes,
  getStateNodes,
  updateFeatureDef,
} from '../../api/masterData'

const machineTypes = ref([])
const machineTypeId = ref(null)
const dimensions = ref([])
const stateNodes = ref([])
const loading = ref(false)
const saving = ref(false)
const drawerVisible = ref(false)
const editId = ref(null)
const form = ref(defaultForm())

const selectedMachineType = computed(() =>
  machineTypes.value.find((item) => item.id === machineTypeId.value) || null,
)
const usedValues = computed(() => {
  const key = form.value.feature_key
  return Array.from(
    new Set(
      stateNodes.value
        .filter((item) =>
          item.target_value &&
          (
            item.feature_key === key ||
            String(item.feature_key || '').startsWith(`${key}__`) ||
            item.metadata_json?.dimension_template_key === key
          ),
        )
        .map((item) => String(item.target_value)),
    ),
  )
})

function defaultForm() {
  return {
    feature_key: '',
    feature_name: '',
    allowed_values: ['', ''],
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

function normalizeBinaryValues(values) {
  const result = []
  for (const raw of values || []) {
    const value = String(raw ?? '').trim()
    if (value && !result.includes(value)) result.push(value)
    if (result.length === 2) break
  }
  return result
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

function generateFeatureKey() {
  const machineType = selectedMachineType.value
  const baseRaw = normalizeCodeToken(machineType?.code, `mt${machineTypeId.value}`)
  const maxBaseLength = Math.max(1, 64 - '_dim_0001'.length)
  const base = baseRaw.slice(0, maxBaseLength).replace(/^_+|_+$/g, '') || `mt${machineTypeId.value}`
  const prefix = `${base}_dim`
  const pattern = new RegExp(`^${prefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}_(\\d+)$`)
  const existing = new Set(dimensions.value.map((item) => item.feature_key))
  let maxSeq = 0
  for (const key of existing) {
    const match = pattern.exec(key)
    if (match) maxSeq = Math.max(maxSeq, Number(match[1]))
  }
  let seq = maxSeq + 1
  while (existing.has(`${prefix}_${String(seq).padStart(4, '0')}`)) seq += 1
  return `${prefix}_${String(seq).padStart(4, '0')}`
}

function usageCount(featureKey) {
  return stateNodes.value.filter((item) =>
    item.feature_key === featureKey ||
    String(item.feature_key || '').startsWith(`${featureKey}__`) ||
    item.metadata_json?.dimension_template_key === featureKey,
  ).length
}

async function loadAll() {
  if (!machineTypeId.value) return
  loading.value = true
  try {
    const [defs, nodes] = await Promise.all([
      getFeatureDefs(machineTypeId.value),
      getStateNodes(machineTypeId.value),
    ])
    dimensions.value = defs.filter(isDimensionTemplate)
    stateNodes.value = nodes
  } finally {
    loading.value = false
  }
}

async function onTypeChange() {
  editId.value = null
  drawerVisible.value = false
  dimensions.value = []
  stateNodes.value = []
  await loadAll()
}

function openCreate() {
  editId.value = null
  form.value = defaultForm()
  drawerVisible.value = true
}

function openEdit(row) {
  editId.value = row.id
  const values = normalizeAllowedValues(row.allowed_values)
  form.value = {
    feature_key: row.feature_key,
    feature_name: row.feature_name || '',
    allowed_values: [values[0] || '', values[1] || ''],
  }
  drawerVisible.value = true
}

async function save() {
  if (!machineTypeId.value) return ElMessage.warning('请先选择设备类型')
  const name = form.value.feature_name.trim()
  const values = normalizeBinaryValues(form.value.allowed_values)
  if (!name) return ElMessage.warning('维度名称不能为空')
  if (values.length !== 2) return ElMessage.warning('需要维护两个不同的二元取值')
  const missingUsed = usedValues.value.filter((value) => !values.includes(value))
  if (missingUsed.length) {
    return ElMessage.warning(`不能移除已有原子状态正在使用的取值：${missingUsed.join('、')}`)
  }

  saving.value = true
  try {
    const payload = {
      feature_key: editId.value ? form.value.feature_key : generateFeatureKey(),
      feature_name: name,
      value_type: 'enum',
      allowed_values: values,
    }
    if (editId.value) await updateFeatureDef(editId.value, payload)
    else {
      await createFeatureDef(machineTypeId.value, {
        machine_type_id: machineTypeId.value,
        ...payload,
      })
    }
    ElMessage.success('状态维度已保存')
    drawerVisible.value = false
    await loadAll()
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  if (usageCount(row.feature_key) > 0) {
    return ElMessage.warning('该维度已被原子状态引用，不能删除')
  }
  await ElMessageBox.confirm('确认删除这个状态维度？', '确认', { type: 'warning' })
  await deleteFeatureDef(row.id)
  ElMessage.success('状态维度已删除')
  await loadAll()
}

onMounted(async () => {
  machineTypes.value = await getMachineTypes()
})
</script>

<style scoped>
.dimension-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.page-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.page-toolbar h2 {
  margin: 0 0 6px;
  font-size: 20px;
}
.page-toolbar p {
  margin: 0;
  color: #606266;
}
.toolbar-controls {
  display: flex;
  gap: 8px;
  align-items: center;
}
.dimension-table {
  width: 100%;
}
.value-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.binary-values {
  width: 100%;
  display: grid;
  gap: 8px;
}
.usage-alert {
  margin-top: 8px;
}
@media (max-width: 900px) {
  .page-toolbar {
    flex-direction: column;
  }
  .toolbar-controls {
    width: 100%;
    flex-wrap: wrap;
  }
}
</style>
