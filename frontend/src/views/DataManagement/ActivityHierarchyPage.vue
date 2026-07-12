<template>
  <div class="hierarchy-page">
    <div class="hierarchy-toolbar">
      <h2>活动层级</h2>
      <div class="toolbar-controls">
        <el-select
          v-model="machineTypeId"
          placeholder="请选择设备类型"
          filterable
          style="width:360px"
          @change="onTypeChange"
        >
          <el-option
            v-for="mt in machineTypes"
            :key="mt.id"
            :label="`${mt.name} (${mt.code})`"
            :value="mt.id"
          />
        </el-select>
        <el-button :disabled="!machineTypeId" @click="loadNodes">刷新</el-button>
        <el-button type="primary" :disabled="!machineTypeId" @click="openCreateRoot">新增一级</el-button>
      </div>
    </div>

    <el-card v-loading="loading">
      <el-empty v-if="!machineTypeId" description="请先选择设备类型" />
      <el-table
        v-else
        :data="treeRows"
        row-key="id"
        size="small"
        border
        default-expand-all
        :tree-props="{ children: 'children' }"
      >
        <el-table-column prop="code" label="编码" min-width="210" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ row.code }}</span>
            <el-tag v-if="row.orphaned" size="small" type="warning" class="inline-tag">父级缺失</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="180" show-overflow-tooltip />
        <el-table-column label="层级" width="80">
          <template #default="{ row }">{{ row.level }}级</template>
        </el-table-column>
        <el-table-column prop="activity_category" label="分类" width="100" />
        <el-table-column prop="sort_order" label="排序" width="80" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.is_active ? 'success' : 'info'">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.level < 3" size="small" @click="openCreateChild(row)">添加子级</el-button>
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="remove(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="drawerVisible" :title="drawerTitle" size="420px">
      <el-form :model="form" label-width="96px" @submit.prevent>
        <el-form-item label="层级">
          <el-tag>{{ form.level }}级</el-tag>
        </el-form-item>
        <el-form-item v-if="form.level > 1" label="父活动" required>
          <el-tree-select
            v-model="form.parent_id"
            :data="parentTreeOptions"
            :props="treeProps"
            node-key="id"
            check-strictly
            filterable
            style="width:100%"
          />
        </el-form-item>
        <el-form-item label="编码" required>
          <el-input v-model="form.code" placeholder="例如 VAC_REPAIR" />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="例如 真空阀组维修维护" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.activity_category" style="width:100%">
            <el-option value="normal" label="普通" />
            <el-option value="repair" label="维修" />
            <el-option value="maintenance" label="维护" />
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" style="width:100%" />
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
import {
  createActivityNode,
  deleteActivityNode,
  getActivityNodes,
  getMachineTypes,
  updateActivityNode,
} from '../../api/masterData'
import { buildHierarchyTree, treeSelectProps } from '../../utils/hierarchyTree'

const treeProps = treeSelectProps
const machineTypes = ref([])
const machineTypeId = ref(null)
const nodes = ref([])
const loading = ref(false)
const saving = ref(false)
const drawerVisible = ref(false)
const editId = ref(null)
const form = ref(defaultForm())

const treeRows = computed(() => buildHierarchyTree(nodes.value))
const drawerTitle = computed(() => {
  if (editId.value) return `编辑活动：${form.value.code || ''}`
  return form.value.level === 1 ? '新增一级活动' : '新增子活动'
})
const parentTreeOptions = computed(() =>
  buildHierarchyTree(nodes.value, {
    disabled: (node) => node.level !== form.value.level - 1 || node.id === editId.value,
  }),
)

function defaultForm(machineTypeIdValue = machineTypeId.value) {
  return {
    machine_type_id: machineTypeIdValue,
    parent_id: null,
    level: 1,
    code: '',
    name: '',
    activity_category: 'normal',
    sort_order: 0,
    is_active: true,
    metadata_json: null,
  }
}

async function onTypeChange() {
  editId.value = null
  drawerVisible.value = false
  await loadNodes()
}

async function loadNodes() {
  if (!machineTypeId.value) {
    nodes.value = []
    return
  }
  loading.value = true
  try {
    nodes.value = await getActivityNodes(machineTypeId.value)
  } catch {
    nodes.value = []
  } finally {
    loading.value = false
  }
}

function openCreateRoot() {
  editId.value = null
  form.value = defaultForm()
  drawerVisible.value = true
}

function openCreateChild(parent) {
  editId.value = null
  form.value = {
    ...defaultForm(),
    parent_id: parent.id,
    level: parent.level + 1,
    activity_category: parent.activity_category || 'normal',
    sort_order: (parent.children?.length ?? 0) + 10,
  }
  drawerVisible.value = true
}

function openEdit(row) {
  editId.value = row.id
  form.value = { ...row, children: undefined, path: undefined }
  drawerVisible.value = true
}

async function save() {
  if (!machineTypeId.value || !form.value.code || !form.value.name) {
    return ElMessage.warning('设备类型、编码、名称不能为空')
  }
  if (form.value.level > 1 && !form.value.parent_id) {
    return ElMessage.warning('二级/三级活动必须选择父活动')
  }
  saving.value = true
  try {
    const payload = {
      machine_type_id: machineTypeId.value,
      parent_id: form.value.level === 1 ? null : form.value.parent_id,
      level: form.value.level,
      code: form.value.code.trim(),
      name: form.value.name.trim(),
      activity_category: form.value.activity_category,
      sort_order: form.value.sort_order,
      is_active: form.value.is_active,
      metadata_json: form.value.metadata_json ?? null,
    }
    if (editId.value) await updateActivityNode(editId.value, payload)
    else await createActivityNode(machineTypeId.value, payload)
    ElMessage.success('活动层级已保存')
    drawerVisible.value = false
    await loadNodes()
  } finally {
    saving.value = false
  }
}

async function remove(id) {
  await ElMessageBox.confirm('确定删除这个活动节点吗？', '确认', { type: 'warning' })
  await deleteActivityNode(id)
  ElMessage.success('已删除')
  await loadNodes()
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
.hierarchy-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.hierarchy-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
}

.hierarchy-toolbar h2 {
  margin: 0;
  font-size: 18px;
}

.toolbar-controls {
  display: flex;
  gap: 8px;
  align-items: center;
}

.inline-tag {
  margin-left: 8px;
}
</style>
