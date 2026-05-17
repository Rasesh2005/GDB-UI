import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for GDB Sandbox E2E tests.
 *
 * Prerequisites before running:
 *   docker compose up -d     ← backend + sandbox-cpp image
 *   (frontend is served by the FastAPI backend at port 8000)
 *
 * Run:   npx playwright test
 * UI:    npx playwright test --ui
 * Debug: npx playwright test --debug
 */
export default defineConfig({
  testDir: '.',
  fullyParallel: false,          // sandbox tests are stateful — run serially
  retries: process.env.CI ? 1 : 0,
  reporter: [['html', { open: 'never' }], ['list']],

  use: {
    baseURL: 'http://localhost:8000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    // Give containers time to spin up
    actionTimeout: 30_000,
    navigationTimeout: 30_000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Optionally start the backend server before tests.
  // Comment out if you start docker compose manually.
  // webServer: {
  //   command: 'docker compose up',
  //   url: 'http://localhost:8000',
  //   reuseExistingServer: !process.env.CI,
  //   timeout: 60_000,
  // },
});
