import { test, expect } from '@playwright/test';

/**
 * 7.1  Guest User Flow
 *
 * WHY: Validates the full guest path:
 *      load page → get sandbox → terminal connects → Run GDB button visible.
 *
 * Prerequisites: docker compose up (server + sandbox-cpp image must be running).
 */

test.describe('Guest User Flow', () => {

  test('page loads and terminal connects', async ({ page }) => {
    await page.goto('/');

    // The xterm terminal element must appear (indicates WS connected)
    await expect(page.locator('.xterm-rows')).toBeVisible({ timeout: 20_000 });
  });

  test('Run (GDB) button is visible to guests', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('button:has-text("Run (GDB)")')).toBeVisible({ timeout: 15_000 });
  });

  test('Login / Register button is visible to guest', async ({ page }) => {
    await page.goto('/');
    // The control panel must show a login option to unauthenticated users
    await expect(page.locator('button:has-text("Login")')).toBeVisible({ timeout: 10_000 });
  });

  test('guest can compile and run code', async ({ page }) => {
    /**
     * WHY: Full guest path regression test.
     *      If any step is broken (WS timeout, session ID missing), this catches it.
     */
    await page.goto('/');
    await page.waitForSelector('.xterm-rows', { timeout: 20_000 });

    // Click "Run (GDB)" to compile and run the default Hello World
    await page.click('button:has-text("Run (GDB)")');

    // Expect the sandbox output to appear in the terminal within 30 s
    await page.waitForFunction(
      () => document.body.innerText.includes('Hello from Sandbox'),
      { timeout: 30_000 }
    );
  });
});
