<template>
  <div>
    <h2>设备实例</h2>
    <el-row :gutter="16">
      <!-- Form -->
      <el-col :span="10">
        <el-card>
          <el-form :model="form" label-width="80px" @submit.prevent>
            <el-form-item label="设备类型" required>
              <el-select v-model="form.machine_type_id" placeholder="请选择" style="width:100%">
                <el-option
                  v-for="mt in machineTypes"
                  :key="mt.id"
                  :label="`${mt.name} (${mt.code})`"
                  :value="mt.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="编码" required>
              <el-input v-model="form.code" placeholder="例如 LW-001" />
            </el-form-item>
            <el-form-item label="名称" required>
              <el-input v-model="form.name" placeholder="例如 1号激光焊机" />
            </el-form-item>
            <el-form-item label="位置">
              <el-input v-model="form.location" placeholder="例如 车间A-1" />
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
          <el-table :data="list" size="small" border stripe>
            <el-table-column prop="code" label="编码" width="120" />
            <el-table-column prop="name" label="名称" />
            <el-table-column label="设备类型" width="140">
              <template #default="{ row }">
                {{ machineTypeLabel(row.machine_type_id) }}
              </template>
            </el-table-column>
            <el-table-column prop="location" label="位置" />
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
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getMachineTypes,
  getMachines,
  createMachine,
  updateMachine,
  deleteMachine,
} from '../../api/masterData'

const list = ref([])
const machineTypes = ref([])
const loading = ref(false)
const saving = ref(false)
const editId = ref(null)

const form = ref({ machine_type_id: null, code: '', name: '', location: '' })

function machineTypeLabel(id) {
  const mt = machineTypes.value.find((m) => m.id === id)
  return mt ? `${mt.name} (${mt.code})` : id
}

async function load() {
  loading.value = true
  try {
    ;[machineTypes.value, list.value] = await Promise.all([getMachineTypes(), getMachines()])
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!form.value.machine_type_id || !form.value.code || !form.value.name) {
    return ElMessage.warning('设备类型、编码、名称不能为空')
  }
  saving.value = true
  try {
    const payload = {
      machine_type_id: form.value.machine_type_id,
      code: form.value.code.trim(),
      name: form.value.name.trim(),
      location: form.value.location.trim() || null,
    }
    if (editId.value) {
      await updateMachine(editId.value, payload)
    } else {
      await createMachine(payload)
    }
    ElMessage.success('设备已保存')
    reset()
    await load()
  } finally {
    saving.value = false
  }
}

function edit(row) {
  editId.value = row.id
  form.value = {
    machine_type_id: row.machine_type_id,
    code: row.code,
    name: row.name,
    location: row.location ?? '',
  }
}

async function remove(id) {
  await ElMessageBox.confirm('确定删除这个设备吗？', '确认', { type: 'warning' })
  await deleteMachine(id)
  ElMessage.success('已删除')
  await load()
}

function reset() {
  editId.value = null
  form.value = { machine_type_id: null, code: '', name: '', location: '' }
}

onMounted(load)
</script>
