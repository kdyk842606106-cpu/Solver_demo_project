<template>
  <div>
    <h2>资源管理</h2>
    <el-row :gutter="16">
      <!-- Form -->
      <el-col :span="10">
        <el-card>
          <el-form :model="form" label-width="80px" @submit.prevent>
            <el-form-item label="编码" required>
              <el-input v-model="form.code" placeholder="例如 NITROGEN_GAS" />
            </el-form-item>
            <el-form-item label="名称" required>
              <el-input v-model="form.name" placeholder="例如 氮气供应" />
            </el-form-item>
            <el-form-item label="资源类型" required>
              <el-input v-model="form.resource_type" placeholder="例如 gas" />
            </el-form-item>
            <el-form-item label="容量">
              <el-input-number v-model="form.capacity" :min="1" style="width:100%" />
            </el-form-item>
            <el-form-item label="是否可用">
              <el-switch v-model="form.is_available" />
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
            <el-table-column prop="code" label="编码" width="140" />
            <el-table-column prop="name" label="名称" />
            <el-table-column prop="resource_type" label="类型" width="100" />
            <el-table-column prop="capacity" label="容量" width="70" />
            <el-table-column label="可用" width="70">
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
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getResources, createResource, updateResource, deleteResource } from '../../api/masterData'

const list = ref([])
const loading = ref(false)
const saving = ref(false)
const editId = ref(null)

const form = ref({ code: '', name: '', resource_type: '', capacity: 1, is_available: true })

async function load() {
  loading.value = true
  try { list.value = await getResources() } finally { loading.value = false }
}

async function save() {
  if (!form.value.code || !form.value.name || !form.value.resource_type) {
    return ElMessage.warning('编码、名称、类型不能为空')
  }
  saving.value = true
  try {
    const payload = {
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
  } finally { saving.value = false }
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
  form.value = { code: '', name: '', resource_type: '', capacity: 1, is_available: true }
}

onMounted(load)
</script>
