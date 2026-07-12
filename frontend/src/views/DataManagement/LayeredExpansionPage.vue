<template>
  <div>
    <h2>展开预览</h2>
    <el-row :gutter="16">
      <el-col :span="8">
        <el-card>
          <el-form label-width="108px" @submit.prevent>
            <el-form-item label="设备类型" required>
              <el-select v-model="machineTypeId" style="width:100%" @change="onTypeChange">
                <el-option
                  v-for="mt in machineTypes"
                  :key="mt.id"
                  :label="`${mt.name} (${mt.code})`"
                  :value="mt.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="目标状态">
              <el-tree-select
                v-model="targetStateNodeIds"
                :data="stateTreeOptions"
                :props="treeProps"
                node-key="id"
                multiple
                show-checkbox
                check-strictly
                filterable
                collapse-tags
                collapse-tags-tooltip
                style="width:100%"
              />
            </el-form-item>
            <el-form-item label="活动范围">
              <el-tree-select
                v-model="activityScopeNodeIds"
                :data="activityTreeOptions"
                :props="treeProps"
                node-key="id"
                multiple
                show-checkbox
                check-strictly
                filterable
                collapse-tags
                collapse-tags-tooltip
                style="width:100%"
              />
            </el-form-item>
            <el-form-item label="包含停用">
              <el-switch v-model="includeInactive" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="loading" @click="runPreview">生成预览</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card v-loading="loading">
          <el-empty v-if="!preview" description="请选择目标状态和活动范围后生成预览" />
          <template v-else>
            <el-alert
              v-if="preview.diagnostics.length"
              type="warning"
              :closable="false"
              class="section"
              :title="`发现 ${preview.diagnostics.length} 条诊断`"
            />
            <el-table
              v-if="preview.diagnostics.length"
              :data="preview.diagnostics"
              size="small"
              border
              class="section"
            >
              <el-table-column prop="code" label="诊断码" width="190" />
              <el-table-column prop="message" label="说明" show-overflow-tooltip />
            </el-table>

            <h3>目标事实</h3>
            <el-table :data="preview.goal_facts" size="small" border class="section">
              <el-table-column prop="state_node_code" label="状态" width="150" />
              <el-table-column prop="feature_key" label="状态维度（feature_key）" width="170" />
              <el-table-column label="目标" width="150">
                <template #default="{ row }">{{ row.operator }} {{ row.target_value }}</template>
              </el-table-column>
              <el-table-column label="路径" show-overflow-tooltip>
                <template #default="{ row }">{{ formatPath(row.source_path) }}</template>
              </el-table-column>
            </el-table>

            <h3>候选活动</h3>
            <el-table :data="preview.candidate_activities" size="small" border class="section">
              <el-table-column prop="activity_node_code" label="活动" width="150" />
              <el-table-column prop="activity_category" label="分类" width="90" />
              <el-table-column label="规则" width="120">
                <template #default="{ row }">{{ row.op_rule_ids.length }}</template>
              </el-table-column>
              <el-table-column label="路径" show-overflow-tooltip>
                <template #default="{ row }">{{ formatPath(row.source_path) }}</template>
              </el-table-column>
            </el-table>

            <h3>Effective Rules</h3>
            <el-table :data="preview.effective_rules" size="small" border>
              <el-table-column prop="op_rule_code" label="规则" width="150" />
              <el-table-column prop="activity_node_code" label="三级活动" width="150" />
              <el-table-column label="前置来源" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row.preconditions.map(formatPrecondition).join('；') || '-' }}
                </template>
              </el-table-column>
              <el-table-column label="效果" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row.effects.map((item) => `${item.effect_type}:${item.feature_key}->${item.new_value}`).join('；') }}
                </template>
              </el-table-column>
            </el-table>
          </template>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getActivityNodes,
  getMachineTypes,
  getStateNodes,
  previewLayeredExpansion,
} from '../../api/masterData'
import { buildHierarchyTree, treeSelectProps } from '../../utils/hierarchyTree'

const machineTypes = ref([])
const activityNodes = ref([])
const stateNodes = ref([])
const machineTypeId = ref(null)
const targetStateNodeIds = ref([])
const activityScopeNodeIds = ref([])
const includeInactive = ref(false)
const preview = ref(null)
const loading = ref(false)
const treeProps = treeSelectProps
const stateTreeOptions = computed(() =>
  buildHierarchyTree(stateNodes.value, { disabled: (node) => node.level < 2 }),
)
const activityTreeOptions = computed(() =>
  buildHierarchyTree(activityNodes.value, { disabled: (node) => node.level > 2 }),
)

function formatPath(path) {
  return path?.map((item) => item.code).join(' / ') || '-'
}

function formatPrecondition(item) {
  const source = item.source_type === 'self_activity_rule' ? '自有' : item.scope_guard_name
  const target = item.feature_key || item.state_node_code || '-'
  const value = item.feature_value ? `${item.operator} ${item.feature_value}` : item.operator
  return `${source}:${target} ${value}`
}

async function onTypeChange() {
  preview.value = null
  targetStateNodeIds.value = []
  activityScopeNodeIds.value = []
  if (!machineTypeId.value) {
    activityNodes.value = []
    stateNodes.value = []
    return
  }
  const [activities, states] = await Promise.all([
    getActivityNodes(machineTypeId.value),
    getStateNodes(machineTypeId.value),
  ])
  activityNodes.value = activities
  stateNodes.value = states
}

async function runPreview() {
  if (!machineTypeId.value) return ElMessage.warning('请先选择设备类型')
  if (!targetStateNodeIds.value.length && !activityScopeNodeIds.value.length) {
    return ElMessage.warning('请选择目标状态或活动范围')
  }
  loading.value = true
  try {
    preview.value = await previewLayeredExpansion(machineTypeId.value, {
      target_state_node_ids: targetStateNodeIds.value,
      activity_scope_node_ids: activityScopeNodeIds.value,
      include_inactive: includeInactive.value,
    })
  } finally {
    loading.value = false
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
.section {
  margin-bottom: 16px;
}

h3 {
  margin: 18px 0 8px;
  font-size: 15px;
}
</style>
