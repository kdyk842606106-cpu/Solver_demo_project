<!-- 4-2: RulePage — adds gt/gte/lt/lte operators, effect_type, delta_value, is_repair -->
<template>
  <div>
    <h2>活动规则</h2>
    <el-row :gutter="16">
      <!-- Form -->
      <el-col :span="14">
        <el-card>
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item label="设备类型" required>
                <el-select
                  v-model="form.machine_type_id"
                  placeholder="请选择"
                  style="width:100%"
                  @change="onTypeChange"
                >
                  <el-option
                    v-for="mt in machineTypes"
                    :key="mt.id"
                    :label="`${mt.name} (${mt.code})`"
                    :value="mt.id"
                  />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="是否修复规则">
                <el-checkbox v-model="form.is_repair">修复规则 (is_repair)</el-checkbox>
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="12">
            <el-col :span="8">
              <el-form-item label="活动编码" required>
                <el-input v-model="form.code" placeholder="例如 OP_WARMUP" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="活动名称" required>
                <el-input v-model="form.name" placeholder="例如 预热" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="时长(min)" required>
                <el-input-number v-model="form.duration_min" :min="1" style="width:100%" />
              </el-form-item>
            </el-col>
          </el-row>

          <el-form-item label="描述">
            <el-input v-model="form.description" type="textarea" :rows="2" />
          </el-form-item>

          <!-- Preconditions -->
          <el-divider content-position="left">
            前置条件
            <el-button size="small" style="margin-left:8px" @click="addPre">+ 新增</el-button>
          </el-divider>
          <div v-for="(pre, i) in form.preconditions" :key="i" class="dynamic-row">
            <el-row :gutter="8" align="middle">
              <el-col :span="7">
                <el-select v-model="pre.feature_key" placeholder="特征键" size="small" style="width:100%">
                  <el-option
                    v-for="fd in featureDefs"
                    :key="fd.feature_key"
                    :label="fd.feature_name || fd.feature_key"
                    :value="fd.feature_key"
                  />
                </el-select>
              </el-col>
              <el-col :span="6">
                <el-select v-model="pre.operator" size="small" style="width:100%">
                  <el-option value="eq" label="= 等于" />
                  <el-option value="neq" label="≠ 不等于" />
                  <el-option value="gt" label="> 大于" />
                  <el-option value="gte" label="≥ 大于等于" />
                  <el-option value="lt" label="< 小于" />
                  <el-option value="lte" label="≤ 小于等于" />
                  <el-option value="in" label="∈ 属于" />
                </el-select>
              </el-col>
              <el-col :span="9">
                <el-input
                  v-model="pre.feature_value"
                  size="small"
                  :placeholder="pre.operator === 'in' ? '逗号分隔，如 a,b,c' : '值'"
                />
              </el-col>
              <el-col :span="2">
                <el-button size="small" type="danger" circle @click="form.preconditions.splice(i, 1)">
                  ×
                </el-button>
              </el-col>
            </el-row>
          </div>

          <!-- Effects -->
          <el-divider content-position="left">
            执行效果
            <el-button size="small" style="margin-left:8px" @click="addEff">+ 新增</el-button>
          </el-divider>
          <div v-for="(eff, i) in form.effects" :key="i" class="dynamic-row">
            <el-row :gutter="8" align="middle">
              <el-col :span="7">
                <el-select v-model="eff.feature_key" placeholder="特征键" size="small" style="width:100%">
                  <el-option
                    v-for="fd in featureDefs"
                    :key="fd.feature_key"
                    :label="fd.feature_name || fd.feature_key"
                    :value="fd.feature_key"
                  />
                </el-select>
              </el-col>
              <el-col :span="6">
                <el-select v-model="eff.effect_type" size="small" style="width:100%">
                  <el-option value="set" label="set 设置" />
                  <el-option value="increment" label="+ 增加" />
                  <el-option value="decrement" label="- 减少" />
                </el-select>
              </el-col>
              <el-col :span="9">
                <!-- set: new_value string -->
                <el-input
                  v-if="eff.effect_type === 'set'"
                  v-model="eff.new_value"
                  size="small"
                  placeholder="执行后值"
                />
                <!-- increment/decrement: delta_value number -->
                <el-input-number
                  v-else
                  v-model="eff.delta_value"
                  size="small"
                  :min="0"
                  style="width:100%"
                  placeholder="变化量"
                />
              </el-col>
              <el-col :span="2">
                <el-button size="small" type="danger" circle @click="form.effects.splice(i, 1)">
                  ×
                </el-button>
              </el-col>
            </el-row>
          </div>

          <!-- Resource Requirements -->
          <el-divider content-position="left">
            资源需求
            <el-button size="small" style="margin-left:8px" @click="addReq">+ 新增</el-button>
          </el-divider>
          <div v-for="(req, i) in form.resource_reqs" :key="i" class="dynamic-row">
            <el-row :gutter="8" align="middle">
              <el-col :span="9">
                <el-input v-model="req.resource_type" size="small" placeholder="资源类型" />
              </el-col>
              <el-col :span="5">
                <el-input-number v-model="req.quantity" :min="1" size="small" style="width:100%" />
              </el-col>
              <el-col :span="8">
                <el-select v-model="req.is_required" size="small" style="width:100%">
                  <el-option :value="true" label="必需" />
                  <el-option :value="false" label="可选" />
                </el-select>
              </el-col>
              <el-col :span="2">
                <el-button size="small" type="danger" circle @click="form.resource_reqs.splice(i, 1)">
                  ×
                </el-button>
              </el-col>
            </el-row>
          </div>

          <div style="margin-top:16px">
            <el-button type="primary" :loading="saving" @click="save">保存</el-button>
            <el-button @click="reset">清空</el-button>
          </div>
        </el-card>
      </el-col>

      <!-- Rule List -->
      <el-col :span="10">
        <el-card v-loading="loading">
          <div style="margin-bottom:12px">
            <el-select
              v-model="listTypeId"
              placeholder="选择设备类型查看规则"
              style="width:100%"
              @change="loadRules"
            >
              <el-option
                v-for="mt in machineTypes"
                :key="mt.id"
                :label="`${mt.name} (${mt.code})`"
                :value="mt.id"
              />
            </el-select>
          </div>
          <el-table :data="ruleList" size="small" border stripe>
            <el-table-column prop="code" label="编码" width="130" show-overflow-tooltip />
            <el-table-column prop="name" label="名称" show-overflow-tooltip />
            <el-table-column label="时长" width="60">
              <template #default="{ row }">{{ row.duration_min }}m</template>
            </el-table-column>
            <el-table-column label="标记" width="60">
              <template #default="{ row }">
                <el-tag v-if="row.is_repair" size="small" type="danger">修复</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="editRule(row)">编辑</el-button>
                <el-button size="small" type="danger" @click="removeRule(row.id)">删除</el-button>
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
  getFeatureDefs,
  getOpRules,
  createOpRule,
  updateOpRule,
  deleteOpRule,
} from '../../api/masterData'

const machineTypes = ref([])
const featureDefs = ref([])
const ruleList = ref([])
const loading = ref(false)
const saving = ref(false)
const editId = ref(null)
const listTypeId = ref(null)

const newPre = () => ({ feature_key: '', operator: 'eq', feature_value: '' })
const newEff = () => ({ feature_key: '', effect_type: 'set', new_value: '', delta_value: 0 })
const newReq = () => ({ resource_type: '', quantity: 1, is_required: true })

const form = ref({
  machine_type_id: null,
  code: '',
  name: '',
  duration_min: 30,
  description: '',
  is_repair: false,
  preconditions: [newPre()],
  effects: [newEff()],
  resource_reqs: [],
})

function addPre() { form.value.preconditions.push(newPre()) }
function addEff() { form.value.effects.push(newEff()) }
function addReq() { form.value.resource_reqs.push(newReq()) }

async function onTypeChange() {
  featureDefs.value = form.value.machine_type_id
    ? await getFeatureDefs(form.value.machine_type_id)
    : []
}

async function loadRules() {
  if (!listTypeId.value) { ruleList.value = []; return }
  loading.value = true
  try { ruleList.value = await getOpRules(listTypeId.value) }
  finally { loading.value = false }
}

async function save() {
  if (!form.value.machine_type_id || !form.value.code || !form.value.name) {
    return ElMessage.warning('设备类型、编码、名称不能为空')
  }
  const validEffects = form.value.effects.filter((e) => e.feature_key)
  if (!validEffects.length) return ElMessage.warning('至少需要一个执行效果')

  saving.value = true
  try {
    const effects = validEffects.map((e) => {
      if (e.effect_type === 'set') {
        return { feature_key: e.feature_key, effect_type: 'set', new_value: e.new_value || 'none' }
      }
      return {
        feature_key: e.feature_key,
        effect_type: e.effect_type,
        new_value: String(e.delta_value ?? 0),
        delta_value: e.delta_value ?? 0,
      }
    })
    const preconditions = form.value.preconditions
      .filter((p) => p.feature_key && p.feature_value)
      .map((p) => {
        const payload = { feature_key: p.feature_key, operator: p.operator, feature_value: p.feature_value }
        if (p.operator === 'in') {
          payload.value_list = p.feature_value.split(',').map((v) => v.trim()).filter(Boolean)
        }
        return payload
      })

    const payload = {
      machine_type_id: form.value.machine_type_id,
      code: form.value.code.trim(),
      name: form.value.name.trim(),
      duration_min: form.value.duration_min,
      description: form.value.description.trim() || null,
      is_active: true,
      is_repair: form.value.is_repair,
      preconditions,
      effects,
      resource_reqs: form.value.resource_reqs.filter((r) => r.resource_type),
    }

    if (editId.value) {
      await updateOpRule(editId.value, payload)
    } else {
      await createOpRule(form.value.machine_type_id, payload)
    }
    ElMessage.success('活动规则已保存')
    const mtId = form.value.machine_type_id
    reset()
    form.value.machine_type_id = mtId
    listTypeId.value = mtId
    await Promise.all([onTypeChange(), loadRules()])
  } finally { saving.value = false }
}

function editRule(row) {
  editId.value = row.id
  form.value.machine_type_id = row.machine_type_id
  form.value.code = row.code
  form.value.name = row.name
  form.value.duration_min = row.duration_min
  form.value.description = row.description ?? ''
  form.value.is_repair = row.is_repair ?? false
  form.value.preconditions = row.preconditions.length
    ? row.preconditions.map((p) => ({ ...p, feature_value: p.feature_value ?? '' }))
    : [newPre()]
  form.value.effects = row.effects.length
    ? row.effects.map((e) => ({
        feature_key: e.feature_key,
        effect_type: e.effect_type ?? 'set',
        new_value: e.effect_type === 'set' || !e.effect_type ? (e.new_value ?? '') : '',
        delta_value: e.delta_value ?? 0,
      }))
    : [newEff()]
  form.value.resource_reqs = row.resource_reqs.length ? row.resource_reqs : []
  onTypeChange()
}

async function removeRule(id) {
  await ElMessageBox.confirm('确定删除这个活动规则吗？', '确认', { type: 'warning' })
  await deleteOpRule(id)
  ElMessage.success('已删除')
  await loadRules()
}

function reset() {
  editId.value = null
  form.value = {
    machine_type_id: form.value.machine_type_id,
    code: '',
    name: '',
    duration_min: 30,
    description: '',
    is_repair: false,
    preconditions: [newPre()],
    effects: [newEff()],
    resource_reqs: [],
  }
}

onMounted(async () => {
  machineTypes.value = await getMachineTypes()
})
</script>

<style scoped>
.dynamic-row { margin-bottom: 8px; }
</style>
