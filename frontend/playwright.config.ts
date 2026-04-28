import { defineConfig, devices } from '@playwright/test'
import { readFileSync } from 'fs'

// ============================================================
// Playwright WebServer Configuration
// ============================================================
// Detect runtime environment (WSL vs native Windows)
const isWSL = process.platform === 'linux' && (() => {
  try {
    readFileSync('/proc/sys/fs/binfmt_misc/WSLInterop')
    return true
  } catch {
    return false
  }
})()

// Backend command depends on runtime:
// - WSL2: use cmd.exe to run Windows batch file (env vars via set)
// - Windows native: same batch file
const backendCommand = isWSL
  ? '/mnt/c/Windows/System32/cmd.exe /c "E:\\Solver_demo_project\\frontend\\e2e\\start-backend.bat"'
  : 'E:\\Solver_demo_project\\frontend\\e2e\\start-backend.bat'

export default defineConfig({
  testDir: './e2e/tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: [
    {
      command: backendCommand,
      url: 'http://172.26.16.1:8000/health',
      timeout: 120 * 1000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      timeout: 120 * 1000,
      reuseExistingServer: !process.env.CI,
    },
  ],
})
