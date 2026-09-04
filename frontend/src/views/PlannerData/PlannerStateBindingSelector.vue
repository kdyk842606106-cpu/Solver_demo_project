<template>
  <div class="planner-binding-selector" :class="{ compact }" data-testid="activity-state-bindings">
    <div class="binding-toolbar">
      <el-segmented v-model="viewMode" :options="[{ label: '按状态包', value: 'package' }, { label: '全部原子状态', value: 'atomic' }]" />
      <el-input v-model="keyword" clearable placeholder="搜索状态包或原子状态" />
    </div>

    <div class="binding-columns">
      <section class="binding-source">
        <header>选择前置状态</header>
        <el-tree v-if="viewMode === 'package'" :data="filteredPackageTree" node-key="key" default-expand-all :expand-on-click-node="false" empty-text="没有匹配的状态包">
          <template #default="{ data }">
            <div class="binding-tree-row">
              <div><span>{{ data.label }}</span><el-tag size="small" :type="data.kind === 'package' ? 'primary' : 'info'">{{ data.kind === 'package' ? `状态包 · ${data.memberIds.length}` : '成员' }}</el-tag></div>
              <el-button link type="primary" :disabled="disabled || selectionDisabled(data)" @click.stop="addSelection(data)">{{ selectionText(data) }}</el-button>
            </div>
          </template>
        </el-tree>
        <div v-else class="atomic-source-list">
          <div v-for="state in filteredStates" :key="state.id" class="atomic-source-row">
            <div><span>{{ state.name }}</span><small v-if="excludedReason(state.id)">{{ excludedReason(state.id) }}</small></div>
            <el-tooltip :disabled="!coveredByPackage(state.id)" :content="`已由 ${coveredByPackage(state.id)} 覆盖`">
              <el-button size="small" :disabled="disabled || atomicDisabled(state.id)" @click="addAtomic(state.id)">{{ atomicButtonText(state.id) }}</el-button>
            </el-tooltip>
          </div>
          <el-empty v-if="!filteredStates.length" description="没有匹配的原子状态" :image-size="44" />
        </div>
      </section>

      <section class="binding-selected">
        <header>已绑定前置状态 <span>{{ modelValue.length }}</span></header>
        <el-empty v-if="!selectedTree.length" description="尚未绑定前置状态" :image-size="44" />
        <el-tree v-else :data="selectedTree" node-key="key" :expand-on-click-node="true" class="selected-binding-tree">
          <template #default="{ data }">
            <div class="selected-tree-row state-binding-row" :class="[`is-${data.kind}`, { 'has-conflict': data.conflict }]">
              <template v-if="data.kind === 'package'">
                <div class="selected-node-main"><strong>{{ data.label }}</strong><small>覆盖 {{ data.binding.covered_state_ids.length }}/{{ data.currentCount }} 个原子状态</small></div>
                <el-tag v-if="data.conflict" size="small" type="danger">与状态转移冲突</el-tag>
                <el-tag size="small" :type="statusTag(data.status)">{{ statusText(data.status) }}</el-tag>
                <el-button v-if="data.status === 'stale'" link type="warning" :disabled="disabled" @click.stop="refreshPackage(data.binding)">更新成员</el-button>
                <el-button v-if="data.status === 'stale'" link :disabled="disabled" @click.stop="keepPackageSnapshot(data.binding)">保留快照</el-button>
                <el-button link type="danger" :disabled="disabled" @click.stop="removeBinding(data.binding)">移除</el-button>
              </template>
              <template v-else-if="data.kind === 'package_member'">
                <el-checkbox :model-value="data.included" :disabled="disabled" @click.stop @update:model-value="(checked) => updateMember(data.binding, data.state.id, checked)">{{ data.state.name }}</el-checkbox>
                <small v-if="data.moved">已移出状态包</small><small v-if="data.excluded">{{ excludedReason(data.state.id) }}</small>
              </template>
              <template v-else>
                <div class="selected-node-main"><strong>{{ data.label }}</strong><small>执行前必须存在，执行后保留</small></div>
                <el-tag v-if="data.conflict" size="small" type="danger">与状态转移冲突</el-tag>
                <el-button link type="danger" :disabled="disabled" aria-label="移除状态绑定" @click.stop="removeBinding(data.binding)">移除</el-button>
              </template>
            </div>
          </template>
        </el-tree>
      </section>
    </div>
    <span class="state-binding-help">这里只维护执行后保留的前置条件；状态包按成员快照绑定。</span>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({ modelValue: { type: Array, default: () => [] }, statePackages: { type: Array, default: () => [] }, statePackageMemberships: { type: Array, default: () => [] }, states: { type: Array, default: () => [] }, excludedStateIds: { type: Array, default: () => [] }, disabled: { type: Boolean, default: false }, compact: { type: Boolean, default: false } })
const emit = defineEmits(['update:modelValue'])
const viewMode = ref('package'), keyword = ref('')
const stateById = computed(() => new Map(props.states.map((item) => [item.id, item])))
const packageById = computed(() => new Map(props.statePackages.map((item) => [item.id, item])))
const packageBindings = computed(() => props.modelValue.filter((item) => item.binding_type === 'state_package'))
const atomicBindings = computed(() => props.modelValue.filter((item) => item.binding_type === 'atomic_state'))
const excludedIds = computed(() => new Set(props.excludedStateIds.filter(Boolean)))
const selectedPackageIds = computed(() => new Set(packageBindings.value.map((item) => item.state_package_id)))
const selectedAtomicIds = computed(() => new Set(atomicBindings.value.map((item) => item.state_id)))
const packageChildren = computed(() => groupBy(props.statePackages, (item) => item.parent_id || null))
const directMembers = computed(() => groupBy(props.statePackageMemberships, (item) => item.state_package_id))
const packageCoverage = computed(() => { const result = new Map(); for (const binding of packageBindings.value) for (const stateId of binding.covered_state_ids || []) if (!result.has(stateId)) result.set(stateId, packagePath(binding.state_package_id)); return result })
const packageTree = computed(() => (packageChildren.value.get(null) || []).map(buildPackageNode))
const filteredPackageTree = computed(() => filterTree(packageTree.value, keyword.value.trim().toLowerCase()))
const filteredStates = computed(() => { const search = keyword.value.trim().toLowerCase(); return props.states.filter((item) => !search || `${item.name} ${item.id}`.toLowerCase().includes(search)) })
const selectedTree = computed(() => props.modelValue.map((binding) => {
  if (binding.binding_type === 'state_package') {
    const current = packageMemberIds(binding.state_package_id), currentSet = new Set(current), coveredSet = new Set(binding.covered_state_ids || [])
    return { key: `selected-package:${binding.state_package_id}`, kind: 'package', label: packagePath(binding.state_package_id), binding, currentCount: current.length, status: bindingStatus(binding), conflict: (binding.covered_state_ids || []).some((id) => excludedIds.value.has(id)), children: coverageStates(binding).map((state) => ({ key: `selected-member:${binding.state_package_id}:${state.id}`, kind: 'package_member', state, binding, included: coveredSet.has(state.id), moved: !currentSet.has(state.id), excluded: excludedIds.value.has(state.id) })) }
  }
  return { key: `selected-atomic:${binding.state_id}`, kind: 'atomic', label: stateById.value.get(binding.state_id)?.name || binding.state_id, binding, conflict: excludedIds.value.has(binding.state_id), children: [] }
}))

function groupBy(items, keyFn) { const result = new Map(); for (const item of items) { const key = keyFn(item); if (!result.has(key)) result.set(key, []); result.get(key).push(item) } return result }
function packageMemberIds(packageId, seen = new Set()) { if (seen.has(packageId)) return []; const nextSeen = new Set(seen).add(packageId); const result = (directMembers.value.get(packageId) || []).map((item) => item.state_id); for (const child of packageChildren.value.get(packageId) || []) result.push(...packageMemberIds(child.id, nextSeen)); return [...new Set(result)].filter((id) => stateById.value.has(id)) }
function buildPackageNode(item) { const packageNodes = (packageChildren.value.get(item.id) || []).map(buildPackageNode); const memberNodes = (directMembers.value.get(item.id) || []).map((membership) => ({ key: `member:${item.id}:${membership.state_id}`, kind: 'atomic', id: membership.state_id, label: stateById.value.get(membership.state_id)?.name || membership.state_id, searchText: `${stateById.value.get(membership.state_id)?.name || ''} ${membership.state_id}`.toLowerCase(), children: [] })); return { key: `package:${item.id}`, kind: 'package', id: item.id, label: item.name, memberIds: packageMemberIds(item.id), searchText: `${item.name} ${item.id}`.toLowerCase(), children: [...packageNodes, ...memberNodes] } }
function filterTree(nodes, search) { if (!search) return nodes; return nodes.map((node) => { const children = filterTree(node.children || [], search); return node.searchText.includes(search) || children.length ? { ...node, children } : null }).filter(Boolean) }
function emitValue(next) { emit('update:modelValue', next.map((item) => ({ ...item, relation_role: 'required', covered_state_ids: [...(item.covered_state_ids || [])] }))) }
function addSelection(item) { if (item.kind === 'package') addPackage(item.id); else addAtomic(item.id) }
function addPackage(packageId) { if (selectedPackageIds.value.has(packageId)) return; const allMembers = packageMemberIds(packageId), memberIds = allMembers.filter((id) => !excludedIds.value.has(id)), covered = new Set(memberIds); emitValue([...props.modelValue.filter((item) => item.binding_type !== 'atomic_state' || !covered.has(item.state_id)), { binding_type: 'state_package', state_package_id: packageId, covered_state_ids: memberIds, relation_role: 'required', coverage_status: memberIds.length === allMembers.length ? 'complete' : 'partial' }]) }
function addAtomic(stateId) { if (!atomicDisabled(stateId)) emitValue([...props.modelValue, { binding_type: 'atomic_state', state_id: stateId, covered_state_ids: [stateId], relation_role: 'required', coverage_status: 'complete' }]) }
function removeBinding(binding) { emitValue(props.modelValue.filter((item) => item !== binding)) }
function updateMember(binding, stateId, checked) { const next = new Set(binding.covered_state_ids || []); if (checked) next.add(stateId); else next.delete(stateId); updateCoverage(binding, [...next]) }
function updateCoverage(binding, stateIds) { const normalized = [...new Set(stateIds)], covered = new Set(normalized); emitValue(props.modelValue.filter((item) => item.binding_type !== 'atomic_state' || !covered.has(item.state_id)).map((item) => item === binding ? { ...item, covered_state_ids: normalized, coverage_status: computedStatus(binding.state_package_id, normalized), snapshot_kept: false } : item)) }
function refreshPackage(binding) { updateCoverage(binding, packageMemberIds(binding.state_package_id).filter((id) => !excludedIds.value.has(id))) }
function keepPackageSnapshot(binding) { emitValue(props.modelValue.map((item) => item === binding ? { ...item, snapshot_kept: true } : item)) }
function computedStatus(packageId, coveredIds) { const current = packageMemberIds(packageId), currentSet = new Set(current); if (!coveredIds.length || coveredIds.some((id) => !currentSet.has(id))) return 'stale'; return coveredIds.length === current.length ? 'complete' : 'partial' }
function bindingStatus(binding) { const computed = computedStatus(binding.state_package_id, binding.covered_state_ids || []); if (binding.coverage_status === 'complete' && computed === 'partial') return 'stale'; return computed }
function coverageStates(binding) { return [...new Set([...packageMemberIds(binding.state_package_id), ...(binding.covered_state_ids || [])])].map((id) => stateById.value.get(id) || { id, name: `状态 ${id}` }) }
function packagePath(packageId) { const parts = []; let current = packageById.value.get(packageId); const seen = new Set(); while (current && !seen.has(current.id)) { seen.add(current.id); parts.unshift(current.name); current = packageById.value.get(current.parent_id) } return parts.join(' / ') || packageId }
function coveredByPackage(stateId) { return packageCoverage.value.get(stateId) || '' }
function excludedReason(stateId) { return excludedIds.value.has(stateId) ? '已用于当前活动状态转移' : '' }
function atomicDisabled(stateId) { return excludedIds.value.has(stateId) || selectedAtomicIds.value.has(stateId) || !!coveredByPackage(stateId) }
function atomicButtonText(stateId) { return excludedIds.value.has(stateId) ? '转移已占用' : selectedAtomicIds.value.has(stateId) ? '已选择' : coveredByPackage(stateId) ? '包内已覆盖' : '添加' }
function selectionDisabled(item) { if (item.kind === 'package') return selectedPackageIds.value.has(item.id) || !item.memberIds.some((id) => !excludedIds.value.has(id)); return atomicDisabled(item.id) }
function selectionText(item) { return item.kind === 'package' ? (!item.memberIds.length ? '空状态包' : selectedPackageIds.value.has(item.id) ? '已选择' : '绑定整包') : atomicButtonText(item.id) }
function statusText(status) { return ({ complete: '完整覆盖', partial: '部分覆盖', stale: '覆盖已过期' })[status] || status }
function statusTag(status) { return ({ complete: 'success', partial: 'warning', stale: 'danger' })[status] || 'info' }
</script>

<style scoped>
.planner-binding-selector{width:100%;display:grid;gap:12px}.binding-toolbar{display:grid;grid-template-columns:auto minmax(220px,1fr);gap:12px}.binding-columns{display:grid;grid-template-columns:minmax(280px,.9fr) minmax(360px,1.1fr);gap:12px}.binding-source,.binding-selected{border:1px solid #e2e8f0;border-radius:9px;padding:12px;min-height:300px;max-height:500px;overflow:auto;background:#fff}.binding-source>header,.binding-selected>header{display:flex;justify-content:space-between;font-weight:700;color:#0f172a;margin-bottom:12px}.binding-tree-row,.atomic-source-row,.selected-tree-row{display:flex;align-items:center;justify-content:space-between;gap:9px;width:100%}.binding-tree-row>div{display:flex;align-items:center;gap:6px}.atomic-source-list{display:grid;gap:8px}.atomic-source-row{padding:9px 10px;border:1px solid #e2e8f0;border-radius:7px}.atomic-source-row>div{display:grid}.atomic-source-row small{color:#dc2626}.selected-binding-tree :deep(.el-tree-node__content){height:auto;min-height:44px;padding:4px 0}.selected-tree-row{padding:6px 8px;border:1px solid #e2e8f0;border-radius:7px}.selected-tree-row.is-package{background:#f8fafc}.selected-tree-row.is-package_member{border:0;border-bottom:1px dashed #e2e8f0;border-radius:0}.selected-tree-row.has-conflict{border-color:#fca5a5;background:#fff1f2}.selected-node-main{display:grid;min-width:0;margin-right:auto}.selected-node-main strong{overflow:hidden;text-overflow:ellipsis}.selected-node-main small,.is-package_member small{color:#64748b}.state-binding-help{font-size:12px;color:#64748b}.compact .binding-columns,.compact .binding-toolbar{grid-template-columns:1fr}.compact .binding-source,.compact .binding-selected{min-height:220px;max-height:360px}@media(max-width:900px){.binding-columns,.binding-toolbar{grid-template-columns:1fr}}
</style>
