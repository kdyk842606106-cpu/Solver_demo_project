<template>
  <div class="solve-workspace">
    <section class="solve-hero">
      <div><p class="eyebrow">IMMUTABLE SHARED INPUT</p><h1>多引擎求解</h1><p>旧引擎、Anytime A* 与 GA 使用同一场景快照，并由 Planner Validator 统一重放。</p></div>
      <el-tag :type="capabilities.planner_available ? 'success' : 'danger'">{{ capabilities.planner_available ? 'Planner 已连接' : 'Planner 未连接' }}</el-tag>
    </section>

    <section class="control-card">
      <el-form label-position="top" class="control-grid">
        <el-form-item label="场景"><el-select v-model="form.scenario_id" filterable style="width:100%"><el-option v-for="item in scenarios" :key="item.id" :value="item.id" :label="`${item.display_code} · ${item.name}`"/></el-select></el-form-item>
        <el-form-item label="运行方式"><el-select v-model="form.engine" style="width:100%"><el-option label="全部对比" value="ALL"/><el-option label="旧引擎" value="LEGACY"/><el-option label="Anytime A*" value="ASTAR"/><el-option label="遗传算法 GA" value="GA"/></el-select></el-form-item>
        <el-form-item label="时间预算（秒）"><el-input-number v-model="form.budget.time_limit_seconds" :min="0.1" :max="120" :step="0.5" style="width:100%"/></el-form-item>
        <el-form-item label="GA 随机种子"><el-input-number v-model="form.seed" style="width:100%"/></el-form-item>
      </el-form>
      <div class="run-actions">
        <div><span>资源模型</span><strong>容量汇总（不分配具体资源实例）</strong></div>
        <el-button type="primary" size="large" :disabled="!form.scenario_id || !capabilities.planner_available" :loading="running" @click="solve">开始求解</el-button>
      </div>
    </section>

    <el-empty v-if="!run" description="选择场景并启动求解" />
    <template v-else>
      <section class="run-summary">
        <div><span>运行状态</span><strong>{{ run.status }}</strong></div>
        <div><span>场景快照</span><code>{{ run.scenario_hash?.slice(0, 16) }}</code></div>
        <div><span>输入共享</span><strong>{{ run.result?.engines_share_mutable_state === false ? '隔离且一致' : '-' }}</strong></div>
      </section>
      <div class="engine-grid">
        <section v-for="(result, engine) in results" :key="engine" class="engine-card">
          <header><div><span class="engine-name">{{ engineLabel(engine) }}</span><el-tag size="small" :type="result.paths?.length ? 'success' : 'danger'">{{ result.status }}</el-tag></div><small>{{ result.elapsed_seconds ?? '-' }} 秒</small></header>
          <template v-if="result.paths?.length">
            <div class="metric-row"><div><span>合法方案</span><strong>{{ result.paths.length }}</strong></div><div><span>最短完工</span><strong>{{ result.paths[0].metrics.makespan }}</strong></div><div><span>活动数</span><strong>{{ result.paths[0].metrics.execution_count }}</strong></div></div>
            <el-table :data="result.paths[0].executions" size="small" max-height="300"><el-table-column prop="activity_name" label="活动"/><el-table-column prop="start_time" label="开始" width="70"/><el-table-column prop="end_time" label="结束" width="70"/></el-table>
            <div class="validator"><span>统一校验</span><el-tag size="small" type="success">{{ result.paths[0].validator_status }}</el-tag></div>
          </template>
          <el-alert v-else :title="result.error || result.diagnosis?.error_message || '未找到合法方案'" type="error" :closable="false" show-icon />
        </section>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createPlannerRun, getPlannerCapabilities, listPlannerScenarios } from '../../api/planner'

const scenarios = ref([]), capabilities = ref({ planner_available: false }), running = ref(false), run = ref(null)
const form = reactive({ scenario_id: '', engine: 'ALL', seed: 42, budget: { time_limit_seconds: 5, transition_limit: 20000, max_solutions: 10 } })
const results = computed(() => run.value?.result?.results || {})
onMounted(async () => { [scenarios.value, capabilities.value] = await Promise.all([listPlannerScenarios(), getPlannerCapabilities()]); if (scenarios.value.length) form.scenario_id = scenarios.value[0].id })
async function solve() { running.value = true; try { run.value = await createPlannerRun(form); if (run.value.status === 'OK') ElMessage.success('全部引擎完成并通过统一校验'); else ElMessage.warning('运行结束，请检查各引擎结果') } catch (error) { ElMessage.error(error?.response?.data?.error_message || error.message || '求解失败') } finally { running.value = false } }
function engineLabel(engine) { return { LEGACY: '旧引擎', ASTAR: 'Anytime A*', GA: '遗传算法 GA' }[engine] || engine }
</script>

<style scoped>
.solve-workspace{display:grid;gap:16px}.solve-hero{display:flex;align-items:center;justify-content:space-between;padding:26px 30px;border-radius:18px;color:#fff;background:linear-gradient(130deg,#172554,#1e3a8a 62%,#0f766e);box-shadow:0 18px 45px rgba(30,58,138,.18)}.solve-hero h1{margin:3px 0 7px;font-size:28px}.solve-hero p{margin:0;color:#bfdbfe}.eyebrow{font-size:11px;letter-spacing:.16em;color:#5eead4!important}.control-card{padding:20px 22px;background:#fff;border:1px solid #e2e8f0;border-radius:14px}.control-grid{display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:14px}.run-actions{display:flex;align-items:center;justify-content:space-between;border-top:1px solid #e2e8f0;padding-top:14px}.run-actions div{display:flex;gap:10px;align-items:center}.run-actions span{color:#64748b;font-size:12px}.run-summary{display:flex;gap:32px;padding:14px 20px;border-radius:12px;background:#eff6ff;border:1px solid #bfdbfe}.run-summary div{display:flex;gap:8px;align-items:center}.run-summary span{font-size:12px;color:#64748b}.engine-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.engine-card{padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:14px;box-shadow:0 8px 24px rgba(15,23,42,.05)}.engine-card header{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.engine-card header>div{display:flex;gap:8px;align-items:center}.engine-name{font-weight:700}.engine-card header small{color:#64748b}.metric-row{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px}.metric-row div{padding:9px;border-radius:8px;background:#f8fafc;text-align:center}.metric-row span{display:block;color:#64748b;font-size:11px}.metric-row strong{font-size:18px;color:#1e3a8a}.validator{display:flex;justify-content:space-between;align-items:center;margin-top:12px;font-size:12px;color:#64748b}@media(max-width:1050px){.control-grid,.engine-grid{grid-template-columns:1fr}.solve-hero{align-items:flex-start;flex-direction:column;gap:12px}}
</style>
