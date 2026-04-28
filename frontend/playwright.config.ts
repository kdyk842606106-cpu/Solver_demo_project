import { defineConfig, devices } from '@playwright/test'

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
      command: '/mnt/c/Windows/System32/cmd.exe /c "cd /d E:\\Solver_demo_project && set DATABASE_URL=sqlite+aiosqlite:///E:/Solver_demo_project/frontend/e2e/test.db && .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000 --host 127.0.0.1"',
      url: 'http://127.0.0.1:8000/health',
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
