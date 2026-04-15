<template>
  <div>
    <h2>设备类型</h2>
    <el-row :gutter="16">
      <!-- Form -->
      <el-col :span="10">
        <el-card>
          <el-form :model="form" label-width="80px" @submit.prevent>
            <el-form-item label="编码" required>
              <el-input v-model="form.code" placeholder="例如 LASER_WELDER" />
            </el-form-item>
            <el-form-item label="名称" required>
              <el-input v-model="form.name" placeholder="例如 激光焊机" />
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
          <el-table :data="list" size="small" border stripe>
            <el-table-column prop="code" label="编码" width="150" />
            <el-table-column prop="name" label="名称" />
            <el-table-column prop="description" label="说明" show-overflow-tooltip />
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
  createMachineType,
  updateMachineType,
  deleteMachineType,
} from '../../api/masterData'

const list = ref([])
const loading = ref(false)
const saving = ref(false)
const editId = ref(null)

const form = ref({ code: '', name: '', description: '' })

async function load() {
  loading.value = true
  try { list.value = await getMachineTypes() } finally { loading.value = false }
}

async function save() {
  if (!form.value.code || !form.value.name) {
    return ElMessage.warning('编码和名称不能为空')
  }
  saving.value = true
  try {
    const payload = {
      code: form.value.code.trim(),
      name: form.value.name.trim(),
      description: form.value.description.trim() || null,
    }
    if (editId.value) {
      await updateMachineType(editId.value, payload)
    } else {
      await createMachineType(payload)
    }
    ElMessage.success('设备类型已保存')
    reset()
    await load()
  } finally { saving.value = false }
}

function edit(row) {
  editId.value = row.id
  form.value = { code: row.code, name: row.name, description: row.description ?? '' }
}

async function remove(id) {
  await ElMessageBox.confirm('确定删除这个设备类型吗？', '确认', { type: 'warning' })
  await deleteMachineType(id)
  ElMessage.success('已删除')
  await load()
}

function reset() {
  editId.value = null
  form.value = { code: '', name: '', description: '' }
}

onMounted(load)
</script>
