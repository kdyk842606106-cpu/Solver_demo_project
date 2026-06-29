import { defineConfig, devices } from '@playwright/test'
import { readFileSync } from 'fs'
import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'

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

const frontendRoot = dirname(fileURLToPath(import.meta.url))
const projectRoot = resolve(frontendRoot, '..')
const windowsProjectRoot = process.env.SOLVER_PROJECT_ROOT || projectRoot
const windowsBackendScript = resolve(windowsProjectRoot, 'frontend', 'e2e', 'start-backend.bat')

function toWslPath(windowsPath: string): string {
  const normalized = windowsPath.replace(/\\/g, '/')
  const driveMatch = normalized.match(/^([A-Za-z]):\/(.*)$/)
  if (!driveMatch) return normalized
  return `/mnt/${driveMatch[1].toLowerCase()}/${driveMatch[2]}`
}

// Backend command depends on runtime:
// - WSL2: invoke the Windows batch file through cmd.exe
// - Windows native: invoke the same batch file directly
const backendCommand = isWSL
  ? `/mnt/c/Windows/System32/cmd.exe /c "${toWslPath(windowsBackendScript)}"`
  : `"${windowsBackendScript}"`
const backendHealthUrl = isWSL
  ? 'http://172.26.16.1:8000/health'
  : 'http://127.0.0.1:8000/health'

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
    video: 'off',
    viewport: { width: 1280, height: 900 },
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'], channel: 'msedge' } },
  ],
  webServer: process.env.PW_SKIP_WEBSERVER ? [] : [
    {
      command: backendCommand,
      url: backendHealthUrl,
      timeout: 120 * 1000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: process.platform === 'win32' ? 'npm.cmd run dev' : 'npm run dev',
      url: 'http://localhost:5173',
      timeout: 120 * 1000,
      reuseExistingServer: !process.env.CI,
    },
  ],
})
