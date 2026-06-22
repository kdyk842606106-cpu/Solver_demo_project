<template>
  <div class="validation-workspace">
    <el-card>
      <el-form label-width="110px">
        <el-row :gutter="16">
          <el-col :span="10">
            <el-form-item label="设备类型" required>
              <el-select
                v-model="machineTypeId"
                clearable
                filterable
                placeholder="选择设备类型"
                style="width:100%"
                @change="loadOptions"
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
        </el-row>
        <el-row :gutter="16">
          <el-col :span="10">
            <el-form-item label="目标状态">
              <el-tree-select
                v-model="form.target_state_node_ids"
                :data="stateTreeOptions"
                :props="treeProps"
                node-key="id"
                multiple
                show-checkbox
                check-strictly
                filterable
                :disabled="!machineTypeId"
                placeholder="选择状态节点"
                style="width:100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="10">
            <el-form-item label="活动范围">
              <el-tree-select
                v-model="form.activity_scope_node_ids"
                :data="activityTreeOptions"
                :props="treeProps"
                node-key="id"
                multiple
                show-checkbox
                check-strictly
                filterable
                :disabled="!machineTypeId"
                placeholder="选择活动节点"
                style="width:100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="4">
            <el-form-item label="包含停用">
              <el-switch v-model="form.include_inactive" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-button type="primary" :loading="running" :disabled="!canRun" @click="runValidation">
          运行验证
        </el-button>
      </el-form>
    </el-card>

    <el-row :gutter="16" class="result-grid">
      <el-col :span="12">
        <el-card>
          <template #header>展开预览</template>
          <el-empty v-if="!expansionResult" description="尚未运行" />
          <pre v-else class="json-view">{{ expansionResult }}</pre>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header>健康检查</template>
          <el-empty v-if="!healthResult" description="尚未运行" />
          <pre v-else class="json-view">{{ healthResult }}</pre>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  checkLayeredHealth,
  getActivityNodes,
  getMachineTypes,
  getStateNodes,
  previewLayeredExpansion,
} from '../../api/masterData'
import { buildHierarchyTree, treeSelectProps } from '../../utils/hierarchyTree'

const machineTypes = ref([])
const machineTypeId = ref(null)
const stateNodes = ref([])
const activityNodes = ref([])
const running = ref(false)
const expansionResult = ref(null)
const healthResult = ref(null)
const form = ref({
  target_state_node_ids: [],
  activity_scope_node_ids: [],
  include_inactive: false,
})
const treeProps = treeSelectProps
const stateTreeOptions = computed(() =>
  buildHierarchyTree(stateNodes.value, { disabled: (node) => node.level < 2 }),
)
const activityTreeOptions = computed(() =>
  buildHierarchyTree(activityNodes.value, { disabled: (node) => node.level > 2 }),
)

const canRun = computed(() =>
  machineTypeId.value &&
  form.value.target_state_node_ids.length > 0 &&
  form.value.activity_scope_node_ids.length > 0
)

async function loadOptions() {
  expansionResult.value = null
  healthResult.value = null
  form.value.target_state_node_ids = []
  form.value.activity_scope_node_ids = []
  if (!machineTypeId.value) {
    stateNodes.value = []
    activityNodes.value = []
    return
  }
  try {
    const [states, activities] = await Promise.all([
      getStateNodes(machineTypeId.value),
      getActivityNodes(machineTypeId.value),
    ])
    stateNodes.value = states
    activityNodes.value = activities
  } catch {
    stateNodes.value = []
    activityNodes.value = []
  }
}

async function runValidation() {
  if (!canRun.value) return ElMessage.warning('请先选择目标状态和活动范围')
  running.value = true
  try {
    const payload = {
      target_state_node_ids: form.value.target_state_node_ids,
      activity_scope_node_ids: form.value.activity_scope_node_ids,
      include_inactive: form.value.include_inactive,
    }
    const [expansion, health] = await Promise.all([
      previewLayeredExpansion(machineTypeId.value, payload),
      checkLayeredHealth(machineTypeId.value, payload),
    ])
    expansionResult.value = JSON.stringify(expansion, null, 2)
    healthResult.value = JSON.stringify(health, null, 2)
  } finally {
    running.value = false
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

<style scoped>
.result-grid { margin-top: 16px; }
.json-view {
  max-height: 520px;
  overflow: auto;
  padding: 12px;
  margin: 0;
  background: #f7f8fa;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.5;
}
</style>
