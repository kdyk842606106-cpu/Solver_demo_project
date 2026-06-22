<template>
  <div class="hierarchy-page">
    <div class="hierarchy-toolbar">
      <h2>状态层级</h2>
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
        <el-table-column label="目标" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.level === 3">{{ row.feature_key }} {{ row.operator }} {{ row.target_value }}</span>
            <span v-else>聚合状态</span>
          </template>
        </el-table-column>
        <el-table-column prop="state_kind" label="类型" width="100" />
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

    <el-drawer v-model="drawerVisible" :title="drawerTitle" size="460px">
      <el-form :model="form" label-width="96px" @submit.prevent>
        <el-form-item label="层级">
          <el-tag>{{ form.level }}级</el-tag>
        </el-form-item>
        <el-form-item v-if="form.level > 1" label="父状态" required>
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
          <el-input v-model="form.code" placeholder="例如 VAC_READY" />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="例如 真空系统就绪" />
        </el-form-item>

        <template v-if="form.level === 3">
          <el-form-item label="特征键" required>
            <el-select v-model="form.feature_key" style="width:100%" filterable>
              <el-option
                v-for="fd in featureDefs"
                :key="fd.feature_key"
                :label="`${fd.feature_name || fd.feature_key} (${fd.feature_key})`"
                :value="fd.feature_key"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="操作符">
            <el-select v-model="form.operator" style="width:100%">
              <el-option value="eq" label="= 等于" />
              <el-option value="gt" label="> 大于" />
              <el-option value="gte" label="≥ 大于等于" />
              <el-option value="lt" label="< 小于" />
              <el-option value="lte" label="≤ 小于等于" />
            </el-select>
          </el-form-item>
          <el-form-item label="目标值" required>
            <el-input v-model="form.target_value" placeholder="例如 true / on / 80" />
          </el-form-item>
          <el-form-item label="状态类型">
            <el-select v-model="form.state_kind" style="width:100%">
              <el-option value="atomic" label="原子状态" />
              <el-option value="external" label="外部同步" />
              <el-option value="manual" label="人工维护" />
            </el-select>
          </el-form-item>
        </template>
        <el-alert v-else title="一级和二级状态为聚合节点，不绑定具体特征。" type="info" :closable="false" class="form-alert" />

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
  createStateNode,
  deleteStateNode,
  getFeatureDefs,
  getMachineTypes,
  getStateNodes,
  updateStateNode,
} from '../../api/masterData'
import { buildHierarchyTree, treeSelectProps } from '../../utils/hierarchyTree'

const treeProps = treeSelectProps
const machineTypes = ref([])
const featureDefs = ref([])
const machineTypeId = ref(null)
const nodes = ref([])
const loading = ref(false)
const saving = ref(false)
const drawerVisible = ref(false)
const editId = ref(null)
const form = ref(defaultForm())

const treeRows = computed(() => buildHierarchyTree(nodes.value))
const drawerTitle = computed(() => {
  if (editId.value) return `编辑状态：${form.value.code || ''}`
  return form.value.level === 1 ? '新增一级状态' : '新增子状态'
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
    feature_key: null,
    operator: 'eq',
    target_value: null,
    state_kind: 'aggregate',
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
    featureDefs.value = []
    return
  }
  loading.value = true
  try {
    const [stateNodes, defs] = await Promise.all([
      getStateNodes(machineTypeId.value),
      getFeatureDefs(machineTypeId.value),
    ])
    nodes.value = stateNodes
    featureDefs.value = defs
  } catch {
    nodes.value = []
    featureDefs.value = []
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
  const level = parent.level + 1
  form.value = {
    ...defaultForm(),
    parent_id: parent.id,
    level,
    state_kind: level === 3 ? 'atomic' : 'aggregate',
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
    return ElMessage.warning('二级/三级状态必须选择父状态')
  }
  if (form.value.level === 3 && (!form.value.feature_key || form.value.target_value == null || form.value.target_value === '')) {
    return ElMessage.warning('三级状态必须配置特征键和目标值')
  }
  saving.value = true
  try {
    const isLeaf = form.value.level === 3
    const payload = {
      machine_type_id: machineTypeId.value,
      parent_id: form.value.level === 1 ? null : form.value.parent_id,
      level: form.value.level,
      code: form.value.code.trim(),
      name: form.value.name.trim(),
      feature_key: isLeaf ? form.value.feature_key : null,
      operator: isLeaf ? form.value.operator : 'eq',
      target_value: isLeaf ? String(form.value.target_value) : null,
      state_kind: isLeaf ? form.value.state_kind : 'aggregate',
      sort_order: form.value.sort_order,
      is_active: form.value.is_active,
      metadata_json: form.value.metadata_json ?? null,
    }
    if (editId.value) await updateStateNode(editId.value, payload)
    else await createStateNode(machineTypeId.value, payload)
    ElMessage.success('状态层级已保存')
    drawerVisible.value = false
    await loadNodes()
  } finally {
    saving.value = false
  }
}

async function remove(id) {
  await ElMessageBox.confirm('确定删除这个状态节点吗？', '确认', { type: 'warning' })
  await deleteStateNode(id)
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

.form-alert {
  margin: 8px 0 18px;
}
</style>
