import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
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
      command: 'cd /mnt/e/Solver_demo_project && DATABASE_URL=sqlite+aiosqlite:///./frontend/e2e/test.db uvicorn app.main:app --port 8000',
      url: 'http://localhost:8000/health',
      timeout: 120 * 1000,
      reuseExistingServer: !process.env.CI,
      env: {
        DATABASE_URL: 'sqlite+aiosqlite:///./frontend/e2e/test.db',
      },
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      timeout: 120 * 1000,
      reuseExistingServer: !process.env.CI,
    },
  ],
})
