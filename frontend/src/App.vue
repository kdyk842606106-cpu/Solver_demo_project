<template>
  <el-container class="layout">
    <el-header class="header">
      <div class="header-left">
        <span class="title">工艺规划与资源优化系统</span>
        <span class="subtitle">集成计划求解引擎 {{ buildVersion }}</span>
      </div>
      <div class="header-right">
        <el-tag :type="healthOk ? 'success' : 'danger'" effect="light">
          {{ healthOk ? `服务正常 · ${version}` : '服务不可用' }}
        </el-tag>
      </div>
    </el-header>

    <el-container direction="vertical" class="content-shell">
      <nav class="top-nav">
        <el-menu
          :default-active="currentView"
          mode="horizontal"
          :ellipsis="false"
          class="top-menu"
          @select="currentView = $event"
        >
          <el-menu-item index="data">
            <el-icon><Grid /></el-icon>
            <span>Planner 数据</span>
          </el-menu-item>
          <el-menu-item index="solve">
            <el-icon><Cpu /></el-icon>
            <span>多引擎求解</span>
          </el-menu-item>
        </el-menu>
      </nav>

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
import DataManagement from './views/PlannerData/index.vue'
import SolvePage from './views/PlannerSolve/index.vue'
import { getHealth } from './api/system'

const currentView = ref('data')
const healthOk = ref(false)
const version = ref('')
const buildVersion = `v${import.meta.env.VITE_APP_VERSION || 'dev'}`

async function checkHealth() {
  try {
    const res = await getHealth()
    healthOk.value = true
    version.value = `v${res.version ?? ''}`
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

.content-shell {
  min-width: 0;
  background: #f4f7fb;
}

.top-nav {
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
  overflow-x: auto;
}

.top-menu {
  min-width: max-content;
  padding: 0 24px;
  border-bottom: none;
}

.main {
  min-width: 0;
  background: #f4f7fb;
  padding: 24px;
}

@media (max-width: 760px) {
  .header {
    height: auto;
    min-height: 56px;
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
    padding: 12px 16px;
  }

  .header-left {
    flex-wrap: wrap;
  }

  .top-menu {
    padding: 0 12px;
  }

  .main {
    padding: 16px;
  }
}
</style>
