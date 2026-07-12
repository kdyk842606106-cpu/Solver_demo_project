<template>
  <div class="resource-page">
    <div class="resource-context">
      <el-form label-width="96px">
        <el-row :gutter="16">
          <el-col :span="10">
            <el-form-item label="设备类型">
              <el-select
                v-model="machineTypeId"
                clearable
                filterable
                placeholder="可先按设备类型过滤"
                style="width:100%"
                @change="loadMachines"
              >
                <el-option
                  v-for="item in machineTypes"
                  :key="item.id"
                  :label="`${item.name} (${item.code})`"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="10">
            <el-form-item label="具体机器" required>
              <el-select
                v-model="machineId"
                clearable
                filterable
                placeholder="选择机器后维护资源"
                style="width:100%"
                @change="onMachineChange"
              >
                <el-option
                  v-for="item in machines"
                  :key="item.id"
                  :label="`${item.name} (${item.code})`"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="4">
            <el-button class="refresh-button" @click="refreshContext">刷新</el-button>
          </el-col>
        </el-row>
      </el-form>
    </div>

    <el-alert
      v-if="!machineId"
      title="请先选择具体机器，再维护这台机器绑定的资源。"
      type="warning"
      :closable="false"
      class="context-alert"
    />

    <el-row :gutter="16">
      <el-col :span="10">
        <el-card>
          <template #header>资源表单</template>
          <el-form :model="form" label-width="92px" @submit.prevent>
            <el-form-item label="所属机器">
              <el-tag v-if="selectedMachineLabel" type="info">{{ selectedMachineLabel }}</el-tag>
              <span v-else class="muted">未选择</span>
            </el-form-item>
            <el-form-item label="编码" required>
              <el-input v-model="form.code" placeholder="例如 TECH-01" />
            </el-form-item>
            <el-form-item label="名称" required>
              <el-input v-model="form.name" placeholder="例如 技术员 01" />
            </el-form-item>
            <el-form-item label="资源类型" required>
              <el-input v-model="form.resource_type" placeholder="例如 TECHNICIAN" />
            </el-form-item>
            <el-form-item label="容量">
              <el-input-number v-model="form.capacity" :min="1" style="width:100%" />
            </el-form-item>
            <el-form-item label="是否可用">
              <el-switch v-model="form.is_available" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" :disabled="!machineId" @click="save">保存</el-button>
              <el-button @click="reset">清空</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="14">
        <el-card v-loading="loading">
          <template #header>当前机器资源</template>
          <el-empty v-if="!machineId" description="请选择机器" />
          <el-table v-else :data="list" size="small" border stripe>
            <el-table-column prop="code" label="编码" width="140" />
            <el-table-column prop="name" label="名称" />
            <el-table-column prop="resource_type" label="类型" width="120" />
            <el-table-column prop="capacity" label="容量" width="80" />
            <el-table-column label="可用" width="80">
              <template #default="{ row }">
                <el-tag :type="row.is_available ? 'success' : 'info'" size="small">
                  {{ row.is_available ? '是' : '否' }}
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
  createResource,
  deleteResource,
  getMachineTypes,
  getMachines,
  getResources,
  updateResource,
} from '../../api/masterData'

const machineTypes = ref([])
const machines = ref([])
const machineTypeId = ref(null)
const machineId = ref(null)
const list = ref([])
const loading = ref(false)
const saving = ref(false)
const editId = ref(null)

const selectedMachineLabel = computed(() => {
  const machine = machines.value.find((item) => item.id === machineId.value)
  return machine ? `${machine.name} (${machine.code})` : ''
})

const emptyForm = () => ({ code: '', name: '', resource_type: '', capacity: 1, is_available: true })
const form = ref(emptyForm())

async function refreshContext() {
  try {
    machineTypes.value = await getMachineTypes()
  } catch {
    machineTypes.value = []
  }
  await loadMachines()
}

async function loadMachines() {
  const params = machineTypeId.value ? { machine_type_id: machineTypeId.value } : {}
  try {
    machines.value = await getMachines(params)
    if (!machines.value.some((item) => item.id === machineId.value)) {
      machineId.value = null
      list.value = []
      reset()
    }
  } catch {
    machines.value = []
    machineId.value = null
    list.value = []
  }
}

async function onMachineChange() {
  reset()
  await load()
}

async function load() {
  if (!machineId.value) {
    list.value = []
    return
  }
  loading.value = true
  try {
    list.value = await getResources(machineId.value)
  } catch {
    list.value = []
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!machineId.value) return ElMessage.warning('请先选择具体机器')
  if (!form.value.code || !form.value.name || !form.value.resource_type) {
    return ElMessage.warning('编码、名称、类型不能为空')
  }
  saving.value = true
  try {
    const payload = {
      machine_id: machineId.value,
      code: form.value.code.trim(),
      name: form.value.name.trim(),
      resource_type: form.value.resource_type.trim(),
      capacity: form.value.capacity,
      is_available: form.value.is_available,
      meta: null,
    }
    if (editId.value) {
      await updateResource(editId.value, payload)
    } else {
      await createResource(payload)
    }
    ElMessage.success('资源已保存')
    reset()
    await load()
  } finally {
    saving.value = false
  }
}

function edit(row) {
  editId.value = row.id
  form.value = {
    code: row.code,
    name: row.name,
    resource_type: row.resource_type,
    capacity: row.capacity,
    is_available: row.is_available,
  }
}

async function remove(id) {
  await ElMessageBox.confirm('确定删除这个资源吗？', '确认', { type: 'warning' })
  await deleteResource(id)
  ElMessage.success('已删除')
  await load()
}

function reset() {
  editId.value = null
  form.value = emptyForm()
}

onMounted(refreshContext)
</script>

<style scoped>
.resource-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.resource-context { margin-bottom: 4px; }
.refresh-button { width: 100%; }
.context-alert { margin-bottom: 4px; }
.muted { color: #909399; }
</style>
