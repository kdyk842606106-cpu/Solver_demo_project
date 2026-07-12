<template>
  <div class="activity-workspace">
    <div class="workspace-toolbar">
      <div>
        <h2>活动能力</h2>
        <p>一级包 / 二级包组织候选能力，原子活动维护一份可复用的执行定义。</p>
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
      </div>
    </div>

    <el-empty v-if="!machineTypeId" description="先选择一个设备类型" />

    <div v-else class="workspace-grid">
      <section class="panel">
        <div class="panel-header">
          <span>活动包树</span>
          <div class="header-actions">
            <el-button size="small" :icon="Plus" @click="openCreatePackage(1)">一级包</el-button>
            <el-button size="small" :icon="Plus" @click="openCreatePackage(2)">二级包</el-button>
          </div>
        </div>
        <el-tree
          v-loading="loading"
          :data="packageTree"
          node-key="id"
          default-expand-all
          highlight-current
          :expand-on-click-node="false"
          @node-click="selectPackage"
        >
          <template #default="{ data }">
            <div class="tree-row">
              <span>{{ data.name }}</span>
              <el-tag size="small" :type="data.level === 1 ? 'info' : 'success'">
                {{ data.level === 1 ? '一级包' : '二级包' }}
              </el-tag>
            </div>
          </template>
        </el-tree>
      </section>

      <section class="panel">
        <div class="panel-header">
          <span>{{ selectedPackage ? selectedPackage.name : '活动包内容' }}</span>
          <div class="header-actions">
            <el-button v-if="selectedPackage" size="small" @click="openEditPackage(selectedPackage)">编辑包</el-button>
            <el-button v-if="selectedPackage" size="small" type="danger" @click="removePackage(selectedPackage)">删除包</el-button>
          </div>
        </div>

        <el-empty v-if="!selectedPackage" description="从左侧选择活动包" />
        <template v-else-if="selectedPackage.level === 1">
          <el-table :data="childrenOf(selectedPackage.id)" size="small" border>
            <el-table-column prop="code" label="二级包编码" width="160" />
            <el-table-column prop="name" label="名称" />
            <el-table-column prop="sort_order" label="排序" width="80" />
            <el-table-column label="启用" width="80">
              <template #default="{ row }">{{ row.is_active ? '是' : '否' }}</template>
            </el-table-column>
          </el-table>
        </template>
        <template v-else>
          <div class="attach-row">
            <el-select v-model="atomicToAttach" filterable placeholder="选择原子活动" style="width: 100%">
              <el-option
                v-for="item in attachableAtomicActivities"
                :key="item.id"
                :label="`${item.name} (${item.code})`"
                :value="item.id"
              />
            </el-select>
            <el-button type="primary" :icon="Link" :disabled="!atomicToAttach" @click="attachAtomic">添加引用</el-button>
          </div>

          <el-alert
            title="移除引用只会从当前二级包移除该原子活动，不会删除原子活动定义。"
            type="info"
            :closable="false"
            class="hint-alert"
          />

          <el-table :data="selectedRefs" size="small" border>
            <el-table-column prop="atomic_activity_code" label="原子活动" width="150" />
            <el-table-column prop="atomic_activity_name" label="名称" />
            <el-table-column prop="activity_category" label="分类" width="90" />
            <el-table-column prop="sort_order" label="排序" width="80" />
            <el-table-column label="操作" width="110">
              <template #default="{ row }">
                <el-button size="small" type="danger" link @click="detachAtomic(row)">移除引用</el-button>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </section>

      <section class="panel">
        <div class="panel-header">
          <span>原子活动库</span>
          <el-button size="small" :icon="Plus" @click="openCreateAtomic">原子活动</el-button>
        </div>

        <el-table :data="atomicActivities" size="small" border highlight-current-row @row-click="openEditAtomic">
          <el-table-column prop="code" label="系统标识" width="140" />
          <el-table-column prop="name" label="名称" show-overflow-tooltip />
          <el-table-column label="执行定义" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="executionStatus(row.id).type">
                {{ executionStatus(row.id).label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="引用" width="70">
            <template #default="{ row }">{{ refCount(row.id) }}</template>
          </el-table-column>
        </el-table>
      </section>
    </div>

    <el-drawer v-model="packageDrawerVisible" :title="packageEditId ? '编辑活动包' : '新增活动包'" size="440px">
      <el-form :model="packageForm" label-width="96px" @submit.prevent>
        <el-form-item label="层级">
          <el-segmented
            v-model="packageForm.level"
            :options="[
              { label: '一级包', value: 1 },
              { label: '二级包', value: 2 },
            ]"
            :disabled="!!packageEditId"
          />
        </el-form-item>
        <el-form-item v-if="packageForm.level === 2" label="父一级包" required>
          <el-select v-model="packageForm.parent_id" style="width: 100%" filterable>
            <el-option
              v-for="item in rootPackages"
              :key="item.id"
              :label="`${item.name} (${item.code})`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="packageForm.name" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="packageForm.activity_category" style="width: 100%">
            <el-option value="normal" label="普通" />
            <el-option value="repair" label="维修" />
            <el-option value="maintenance" label="维护" />
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="packageForm.sort_order" style="width: 100%" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="packageForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="packageDrawerVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingPackage" @click="savePackage">保存</el-button>
      </template>
    </el-drawer>

    <el-drawer v-model="atomicDrawerVisible" :title="atomicEditId ? '编辑原子活动基础信息' : '新增原子活动基础信息'" size="620px">
      <div class="drawer-stack">
        <el-alert
          v-if="atomicEditId && atomicReferences.length > 1"
          title="此修改会影响所有引用该原子活动的活动包。"
          type="warning"
          :closable="false"
        />
        <el-alert
          v-if="hasMultipleRules"
          title="该原子活动存在多条历史执行定义，当前普通维护流不会自动合并或覆盖它们。"
          type="error"
          :closable="false"
        />
        <el-alert
          v-if="hasLegacyFacts"
          title="当前执行定义包含未匹配到原子状态的历史事实，保存时会保留这些事实。"
          type="warning"
          :closable="false"
        />

        <el-form :model="atomicForm" label-width="112px" @submit.prevent>
          <div class="form-section">
            <div class="section-title">基本信息</div>
            <el-form-item label="名称" required>
              <el-input v-model="atomicForm.name" />
            </el-form-item>
            <el-form-item label="分类">
              <el-select v-model="atomicForm.activity_category" style="width: 100%">
                <el-option value="normal" label="普通" />
                <el-option value="repair" label="维修" />
                <el-option value="maintenance" label="维护" />
              </el-select>
            </el-form-item>
            <el-form-item label="排序">
              <el-input-number v-model="atomicForm.sort_order" style="width: 100%" />
            </el-form-item>
            <el-form-item label="启用">
              <el-switch v-model="atomicForm.is_active" />
            </el-form-item>
          </div>

          <div class="form-section">
            <div class="section-title">执行信息</div>
            <el-form-item label="耗时(分钟)" required>
              <el-input-number
                v-model="atomicForm.duration_min"
                :min="1"
                style="width: 100%"
                :disabled="hasMultipleRules"
              />
            </el-form-item>
            <el-form-item label="维修活动">
              <el-switch v-model="atomicForm.is_repair" :disabled="hasMultipleRules" />
            </el-form-item>
            <el-form-item label="说明">
              <el-input
                v-model="atomicForm.description"
                type="textarea"
                :rows="3"
                :disabled="hasMultipleRules"
              />
            </el-form-item>
          </div>

          <div class="form-section">
            <div class="section-title">前置状态</div>
            <el-form-item label="必须满足">
              <el-select
                v-model="atomicForm.precondition_state_ids"
                multiple
                filterable
                clearable
                placeholder="选择已有原子状态"
                style="width: 100%"
                :disabled="hasMultipleRules"
              >
                <el-option
                  v-for="item in atomicStateNodes"
                  :key="item.id"
                  :label="stateFactLabel(item)"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
          </div>

          <div class="form-section">
            <div class="section-title">产出状态</div>
            <el-form-item label="完成后达到" required>
              <el-select
                v-model="atomicForm.effect_state_ids"
                multiple
                filterable
                clearable
                placeholder="选择已有原子状态"
                style="width: 100%"
                :disabled="hasMultipleRules"
              >
                <el-option
                  v-for="item in atomicStateNodes"
                  :key="item.id"
                  :label="stateFactLabel(item)"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
          </div>

          <div class="form-section">
            <div class="section-title">
              <span>资源需求</span>
              <el-button size="small" :icon="Plus" :disabled="hasMultipleRules" @click="addResourceReq">资源</el-button>
            </div>
            <div v-if="!atomicForm.resource_reqs.length" class="empty-line">未配置资源需求</div>
            <div v-for="(item, index) in atomicForm.resource_reqs" :key="index" class="resource-row">
              <el-input
                v-model="item.resource_type"
                placeholder="资源类型"
                :disabled="hasMultipleRules"
              />
              <el-input-number
                v-model="item.quantity"
                :min="1"
                controls-position="right"
                :disabled="hasMultipleRules"
              />
              <el-switch
                v-model="item.is_required"
                active-text="必需"
                inactive-text="可选"
                :disabled="hasMultipleRules"
              />
              <el-button
                type="danger"
                link
                :disabled="hasMultipleRules"
                @click="removeResourceReq(index)"
              >
                删除
              </el-button>
            </div>
          </div>

          <div v-if="atomicEditId" class="form-section">
            <div class="section-title">引用影响</div>
            <div v-if="!atomicReferences.length" class="empty-line">当前没有二级活动包引用它</div>
            <el-tag
              v-for="item in atomicReferences"
              :key="item.id"
              class="reference-tag"
              type="warning"
            >
              {{ packagePath(item.activity_node_id) }}
            </el-tag>
          </div>
        </el-form>
      </div>

      <template #footer>
        <el-button v-if="atomicEditId" type="danger" @click="removeAtomic">删除定义</el-button>
        <el-button @click="atomicDrawerVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingAtomic" @click="saveAtomic">保存</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Link, Plus, Refresh } from '@element-plus/icons-vue'
import {
  createActivityNode,
  createActivityPackageAtomicRef,
  createAtomicActivity,
  createOpRule,
  deleteActivityNode,
  deleteActivityPackageAtomicRef,
  deleteAtomicActivity,
  getActivityNodes,
  getActivityPackageAtomicRefs,
  getAtomicActivities,
  getMachineTypes,
  getOpRules,
  getStateNodes,
  updateActivityNode,
  updateAtomicActivity,
  updateOpRule,
} from '../../api/masterData'
import { buildHierarchyTree } from '../../utils/hierarchyTree'

const machineTypes = ref([])
const machineTypeId = ref(null)
const activityNodes = ref([])
const atomicActivities = ref([])
const stateNodes = ref([])
const refsByPackage = ref(new Map())
const opRules = ref([])
const selectedPackage = ref(null)
const atomicToAttach = ref(null)
const loading = ref(false)
const packageDrawerVisible = ref(false)
const atomicDrawerVisible = ref(false)
const packageEditId = ref(null)
const atomicEditId = ref(null)
const savingPackage = ref(false)
const savingAtomic = ref(false)
const packageForm = ref(defaultPackageForm())
const atomicForm = ref(defaultAtomicForm())

const packageNodes = computed(() => activityNodes.value.filter((item) => item.level <= 2))
const packageById = computed(() => new Map(packageNodes.value.map((item) => [item.id, item])))
const packageTree = computed(() => buildHierarchyTree(packageNodes.value))
const rootPackages = computed(() => packageNodes.value.filter((item) => item.level === 1))
const selectedRefs = computed(() => refsByPackage.value.get(selectedPackage.value?.id) || [])
const attachableAtomicActivities = computed(() => {
  const attachedIds = new Set(selectedRefs.value.map((item) => item.atomic_activity_id))
  return atomicActivities.value.filter((item) => !attachedIds.has(item.id))
})
const stateChildIds = computed(() => {
  const map = new Map()
  for (const item of stateNodes.value) {
    if (!map.has(item.parent_id)) map.set(item.parent_id, [])
    map.get(item.parent_id).push(item.id)
  }
  return map
})
const atomicStateNodes = computed(() =>
  stateNodes.value.filter((item) =>
    !(stateChildIds.value.get(item.id) || []).length &&
    item.feature_key &&
    item.target_value,
  ),
)
const stateNodeById = computed(() => new Map(atomicStateNodes.value.map((item) => [item.id, item])))
const atomicStateByFact = computed(() => {
  const map = new Map()
  for (const item of atomicStateNodes.value) {
    map.set(factKey(item.feature_key, item.target_value), item)
  }
  return map
})
const currentAtomicRules = computed(() =>
  atomicEditId.value ? opRules.value.filter((item) => item.atomic_activity_id === atomicEditId.value) : [],
)
const currentPrimaryRule = computed(() => (currentAtomicRules.value.length === 1 ? currentAtomicRules.value[0] : null))
const hasMultipleRules = computed(() => currentAtomicRules.value.length > 1)
const hasLegacyFacts = computed(() =>
  !!atomicForm.value.legacy_preconditions.length || !!atomicForm.value.legacy_effects.length,
)
const atomicReferences = computed(() => (atomicEditId.value ? refsForAtomic(atomicEditId.value) : []))

function defaultPackageForm(level = 1) {
  return {
    machine_type_id: machineTypeId.value,
    parent_id: null,
    level,
    code: '',
    name: '',
    activity_category: 'normal',
    sort_order: 0,
    is_active: true,
    metadata_json: null,
  }
}

function defaultAtomicForm() {
  return {
    machine_type_id: machineTypeId.value,
    code: '',
    name: '',
    activity_category: 'normal',
    sort_order: 0,
    is_active: true,
    metadata_json: null,
    duration_min: 30,
    description: '',
    is_repair: false,
    precondition_state_ids: [],
    effect_state_ids: [],
    resource_reqs: [],
    legacy_preconditions: [],
    legacy_effects: [],
  }
}

function childrenOf(parentId) {
  return packageNodes.value.filter((item) => item.parent_id === parentId)
}

function refsForAtomic(atomicId) {
  const refs = []
  for (const packageRefs of refsByPackage.value.values()) {
    refs.push(...packageRefs.filter((item) => item.atomic_activity_id === atomicId))
  }
  return refs
}

function refCount(atomicId) {
  return refsForAtomic(atomicId).length
}

function rulesForAtomic(atomicId) {
  return opRules.value.filter((item) => item.atomic_activity_id === atomicId)
}

function executionStatus(atomicId) {
  const count = rulesForAtomic(atomicId).length
  if (count === 0) return { label: '未配置', type: 'danger' }
  if (count === 1) return { label: '已配置', type: 'success' }
  return { label: '多条', type: 'warning' }
}

function factKey(featureKey, value) {
  return `${featureKey || ''}::${value || ''}`
}

function stateFactLabel(node) {
  const objectName = node.metadata_json?.state_object_name
  const baseName = objectName ? `${objectName} / ${node.name}` : node.name
  return `${baseName} = ${node.target_value}`
}

function packagePath(packageId) {
  const node = packageById.value.get(packageId)
  if (!node) return `活动包 ${packageId}`
  const parent = packageById.value.get(node.parent_id)
  return parent ? `${parent.name} / ${node.name}` : node.name
}

async function onTypeChange() {
  selectedPackage.value = null
  atomicToAttach.value = null
  await loadAll()
}

async function loadAll() {
  if (!machineTypeId.value) return
  loading.value = true
  try {
    const [nodes, atomics, rules, states] = await Promise.all([
      getActivityNodes(machineTypeId.value),
      getAtomicActivities(machineTypeId.value),
      getOpRules(machineTypeId.value),
      getStateNodes(machineTypeId.value),
    ])
    activityNodes.value = nodes
    atomicActivities.value = atomics
    opRules.value = rules
    stateNodes.value = states
    await loadRefs(nodes.filter((item) => item.level === 2))
    if (selectedPackage.value) {
      selectedPackage.value = packageNodes.value.find((item) => item.id === selectedPackage.value.id) || null
    }
  } finally {
    loading.value = false
  }
}

async function loadRefs(packages) {
  const entries = await Promise.all(
    packages.map(async (item) => [item.id, await getActivityPackageAtomicRefs(item.id)]),
  )
  refsByPackage.value = new Map(entries)
}

function selectPackage(item) {
  selectedPackage.value = item
  atomicToAttach.value = null
}

function openCreatePackage(level) {
  packageEditId.value = null
  packageForm.value = defaultPackageForm(level)
  if (level === 2 && rootPackages.value.length) {
    packageForm.value.parent_id = selectedPackage.value?.level === 1 ? selectedPackage.value.id : rootPackages.value[0].id
  }
  packageDrawerVisible.value = true
}

function openEditPackage(item) {
  packageEditId.value = item.id
  packageForm.value = { ...defaultPackageForm(item.level), ...item }
  packageDrawerVisible.value = true
}

async function savePackage() {
  if (!packageForm.value.name.trim()) {
    return ElMessage.warning('名称不能为空')
  }
  if (packageForm.value.level === 2 && !packageForm.value.parent_id) {
    return ElMessage.warning('二级包必须选择父一级包')
  }
  savingPackage.value = true
  try {
    const payload = {
      machine_type_id: machineTypeId.value,
      parent_id: packageForm.value.level === 1 ? null : packageForm.value.parent_id,
      level: packageForm.value.level,
      name: packageForm.value.name.trim(),
      activity_category: packageForm.value.activity_category,
      sort_order: packageForm.value.sort_order,
      is_active: packageForm.value.is_active,
      metadata_json: null,
    }
    if (packageEditId.value) await updateActivityNode(packageEditId.value, payload)
    else await createActivityNode(machineTypeId.value, payload)
    ElMessage.success('活动包已保存')
    packageDrawerVisible.value = false
    await loadAll()
  } finally {
    savingPackage.value = false
  }
}

async function removePackage(item) {
  await ElMessageBox.confirm('删除活动包会同时移除包内原子活动引用，原子活动定义会保留。确认删除？', '确认', { type: 'warning' })
  await deleteActivityNode(item.id)
  selectedPackage.value = null
  ElMessage.success('活动包已删除')
  await loadAll()
}

async function attachAtomic() {
  if (!selectedPackage.value || selectedPackage.value.level !== 2 || !atomicToAttach.value) return
  await createActivityPackageAtomicRef(selectedPackage.value.id, {
    atomic_activity_id: atomicToAttach.value,
    sort_order: selectedRefs.value.length + 10,
    is_active: true,
    metadata_json: null,
  })
  atomicToAttach.value = null
  await loadAll()
}

async function detachAtomic(row) {
  await deleteActivityPackageAtomicRef(row.id)
  await loadAll()
}

function openCreateAtomic() {
  atomicEditId.value = null
  atomicForm.value = defaultAtomicForm()
  atomicDrawerVisible.value = true
}

function openEditAtomic(item) {
  atomicEditId.value = item.id
  const rules = rulesForAtomic(item.id)
  const primaryRule = rules.length === 1 ? rules[0] : null
  atomicForm.value = {
    ...defaultAtomicForm(),
    ...item,
    duration_min: primaryRule?.duration_min || 30,
    description: primaryRule?.description || '',
    is_repair: !!primaryRule?.is_repair,
    precondition_state_ids: matchedPreconditionStateIds(primaryRule),
    effect_state_ids: matchedEffectStateIds(primaryRule),
    resource_reqs: (primaryRule?.resource_reqs || []).map((req) => ({
      resource_type: req.resource_type,
      quantity: req.quantity,
      is_required: req.is_required,
    })),
    legacy_preconditions: unmatchedPreconditions(primaryRule),
    legacy_effects: unmatchedEffects(primaryRule),
  }
  atomicDrawerVisible.value = true
}

function matchedPreconditionStateIds(rule) {
  if (!rule) return []
  return (rule.preconditions || [])
    .map((item) => atomicStateByFact.value.get(factKey(item.feature_key, item.feature_value))?.id)
    .filter(Boolean)
}

function matchedEffectStateIds(rule) {
  if (!rule) return []
  return (rule.effects || [])
    .map((item) => atomicStateByFact.value.get(factKey(item.feature_key, item.new_value))?.id)
    .filter(Boolean)
}

function unmatchedPreconditions(rule) {
  if (!rule) return []
  return (rule.preconditions || []).filter((item) =>
    !atomicStateByFact.value.has(factKey(item.feature_key, item.feature_value)),
  )
}

function unmatchedEffects(rule) {
  if (!rule) return []
  return (rule.effects || []).filter((item) =>
    !atomicStateByFact.value.has(factKey(item.feature_key, item.new_value)),
  )
}

function addResourceReq() {
  atomicForm.value.resource_reqs.push({
    resource_type: '',
    quantity: 1,
    is_required: true,
  })
}

function removeResourceReq(index) {
  atomicForm.value.resource_reqs.splice(index, 1)
}

function buildRulePayload(atomicActivityId) {
  const preconditions = [
    ...atomicForm.value.legacy_preconditions.map((item) => ({
      feature_key: item.feature_key,
      operator: item.operator || 'eq',
      feature_value: item.feature_value,
      value_list: item.value_list || null,
    })),
    ...atomicForm.value.precondition_state_ids.map((id) => {
      const node = stateNodeById.value.get(id)
      return {
        feature_key: node.feature_key,
        operator: 'eq',
        feature_value: node.target_value,
        value_list: null,
      }
    }),
  ]
  const effects = [
    ...atomicForm.value.legacy_effects.map((item) => ({
      feature_key: item.feature_key,
      new_value: item.new_value,
      effect_type: item.effect_type || 'set',
      delta_value: item.delta_value || null,
    })),
    ...atomicForm.value.effect_state_ids.map((id) => {
      const node = stateNodeById.value.get(id)
      return {
        feature_key: node.feature_key,
        new_value: node.target_value,
        effect_type: 'set',
        delta_value: null,
      }
    }),
  ]
  const resourceReqs = atomicForm.value.resource_reqs
    .map((item) => ({
      resource_type: String(item.resource_type || '').trim(),
      quantity: Number(item.quantity || 1),
      is_required: !!item.is_required,
    }))
    .filter((item) => item.resource_type)

  return {
    machine_type_id: machineTypeId.value,
    atomic_activity_id: atomicActivityId,
    name: atomicForm.value.name.trim(),
    duration_min: atomicForm.value.duration_min,
    description: atomicForm.value.description || null,
    is_active: atomicForm.value.is_active,
    is_repair: atomicForm.value.is_repair,
    preconditions,
    effects,
    resource_reqs: resourceReqs,
  }
}

async function saveAtomic() {
  if (!atomicForm.value.name.trim()) {
    return ElMessage.warning('名称不能为空')
  }
  if (!hasMultipleRules.value && !atomicForm.value.effect_state_ids.length && !atomicForm.value.legacy_effects.length) {
    return ElMessage.warning('原子活动至少需要一个产出状态')
  }
  savingAtomic.value = true
  try {
    const atomicPayload = {
      machine_type_id: machineTypeId.value,
      name: atomicForm.value.name.trim(),
      activity_category: atomicForm.value.activity_category,
      sort_order: atomicForm.value.sort_order,
      is_active: atomicForm.value.is_active,
      metadata_json: null,
    }
    let atomicId = atomicEditId.value
    if (atomicEditId.value) {
      await updateAtomicActivity(atomicEditId.value, atomicPayload)
    } else {
      const created = await createAtomicActivity(machineTypeId.value, atomicPayload)
      atomicId = created.id
    }

    if (!hasMultipleRules.value) {
      const rulePayload = buildRulePayload(atomicId)
      if (currentPrimaryRule.value) await updateOpRule(currentPrimaryRule.value.id, rulePayload)
      else await createOpRule(machineTypeId.value, rulePayload)
    }

    ElMessage.success(hasMultipleRules.value ? '原子活动已保存，历史多执行定义未修改' : '原子活动基础信息已保存')
    atomicDrawerVisible.value = false
    await loadAll()
  } finally {
    savingAtomic.value = false
  }
}

async function removeAtomic() {
  if (!atomicEditId.value) return
  await ElMessageBox.confirm('删除原子活动定义会同步移除包引用和未被历史计划使用的执行定义；如果已进入计划将无法删除。确认删除？', '确认', { type: 'warning' })
  await deleteAtomicActivity(atomicEditId.value)
  atomicDrawerVisible.value = false
  ElMessage.success('原子活动定义已删除')
  await loadAll()
}

onMounted(async () => {
  machineTypes.value = await getMachineTypes()
})
</script>

<style scoped>
.activity-workspace {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.workspace-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.workspace-toolbar h2 {
  margin: 0 0 6px;
  font-size: 20px;
}
.workspace-toolbar p {
  margin: 0;
  color: #606266;
}
.toolbar-controls {
  display: flex;
  gap: 8px;
  align-items: center;
}
.workspace-grid {
  display: grid;
  grid-template-columns: minmax(280px, 0.9fr) minmax(360px, 1.1fr) minmax(360px, 1fr);
  gap: 14px;
}
.panel {
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  padding: 12px;
  min-height: 520px;
  background: #fff;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
  font-weight: 600;
}
.header-actions {
  display: flex;
  gap: 6px;
}
.tree-row {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-right: 8px;
}
.attach-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  margin-bottom: 12px;
}
.hint-alert {
  margin-bottom: 12px;
}
.drawer-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.form-section {
  border-top: 1px solid #ebeef5;
  padding-top: 14px;
  margin-top: 14px;
}
.form-section:first-child {
  border-top: 0;
  padding-top: 0;
  margin-top: 0;
}
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
  font-weight: 600;
  color: #303133;
}
.resource-row {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) 120px 120px 56px;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.empty-line {
  color: #909399;
  font-size: 13px;
  line-height: 32px;
}
.reference-tag {
  margin: 0 8px 8px 0;
}
@media (max-width: 1200px) {
  .workspace-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 640px) {
  .resource-row {
    grid-template-columns: 1fr;
  }
}
</style>
