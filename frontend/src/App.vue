<template>
  <el-container class="layout">
    <el-header class="header">
      <div class="header-left">
        <span class="title">工艺规划与资源优化系统</span>
        <span class="subtitle">集成计划求解引擎 V0.2</span>
      </div>
      <div class="header-right">
        <el-tag :type="healthOk ? 'success' : 'danger'" effect="light">
          {{ healthOk ? `服务正常 · ${version}` : '服务不可用' }}
        </el-tag>
      </div>
    </el-header>

    <el-container>
      <el-aside width="160px" class="aside">
        <el-menu
          :default-active="currentView"
          @select="currentView = $event"
        >
          <el-menu-item index="data">
            <el-icon><Grid /></el-icon>
            <span>数据管理</span>
          </el-menu-item>
          <el-menu-item index="solve">
            <el-icon><Cpu /></el-icon>
            <span>求解</span>
          </el-menu-item>
        </el-menu>
      </el-aside>

      <el-main class="main">
        <DataManagement v-if="currentView === 'data'" />
        <SolvePage v-else />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Grid, Cpu } from '@element-plus/icons-vue'
import axios from 'axios'
import DataManagement from './views/DataManagement/index.vue'
import SolvePage from './views/SolvePage/index.vue'

const currentView = ref('data')
const healthOk = ref(false)
const version = ref('')

async function checkHealth() {
  try {
    const res = await axios.get('/health')
    healthOk.value = true
    version.value = `v${res.data.version ?? ''}`
  } catch {
    healthOk.value = false
  }
}

onMounted(() => {
  checkHealth()
  setInterval(checkHealth, 30000)
})
</script>

<style>
* { box-sizing: border-box; }
body { margin: 0; font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; }

.layout { min-height: 100vh; }

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #0f172a;
  color: #fff;
  padding: 0 24px;
  height: 56px;
}
.header-left { display: flex; align-items: baseline; gap: 12px; }
.title { font-size: 18px; font-weight: 700; }
.subtitle { font-size: 12px; color: #94a3b8; }

.aside {
  background: #fff;
  border-right: 1px solid #e2e8f0;
}
.aside .el-menu { border-right: none; }

.main { background: #f4f7fb; padding: 24px; }
</style>
