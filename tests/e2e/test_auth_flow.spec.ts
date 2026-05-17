import { test, expect } from '@playwright/test';

/**
 * 7.2  Authenticated User Flow — Register → Edit → Persist across reload
 * 7.3  Logout → sandbox becomes ephemeral again
 *
 * WHY: Core regression test. Confirms that a logged-in user's files
 *      survive a page reload (simulating a container restart / reconnect).
 *
 * Prerequisites: docker compose up -d
 *
 * NOTE: Each run uses a unique username to avoid conflicts between test runs.
 */

// Helpers
const uniqueUser = () => `e2euser_${Date.now()}`;

async function registerAndLogin(page: any, username: string, password = 'testpass123') {
  await page.goto('/');

  // Open auth modal
  await page.click('button:has-text("Login")');
  await expect(page.locator('.auth-modal')).toBeVisible({ timeout: 5_000 });

  // Switch to Register tab
  await page.click('.auth-tabs button:has-text("Register")');
  await expect(page.getByText('Create Account')).toBeVisible();

  // Fill form
  await page.fill('input[placeholder="Enter your username"]', username);
  await page.fill('input[placeholder="Enter your password"]', password);

  // Submit
  await page.click('button:has-text("Create Account")');

  // Wait for the page to reload (auth success triggers window.location.reload())
  await page.waitForLoadState('networkidle', { timeout: 15_000 });
}


test.describe('Authenticated User Flow', () => {

  test('register → username appears in control panel', async ({ page }) => {
    const username = uniqueUser();
    await registerAndLogin(page, username);

    // After login, the user's name must appear in the header/control panel
    await expect(page.getByText(username)).toBeVisible({ timeout: 10_000 });
  });

  test('authenticated user code persists after page reload', async ({ page }) => {
    /**
     * WHY: This is THE core regression test.
     *      Write a unique marker → wait for auto-save → reload the
     *      page → confirm the marker is still in the editor.
     */
    const username = uniqueUser();
    await registerAndLogin(page, username);

    // Wait for the Monaco editor to be ready
    await page.waitForSelector('.monaco-editor', { timeout: 20_000 });

    // Click into the editor and type a unique marker
    const marker = `// E2E_PERSIST_MARKER_${Date.now()}`;
    await page.click('.monaco-editor');
    await page.keyboard.press('Control+A');  // Select all
    await page.keyboard.press('Delete');     // Clear
    // Type the marker
    await page.keyboard.type(marker);

    // Wait for auto-save to complete properly.
    // In EditorView.jsx, status goes: Auto-saved -> Saving... -> Saved -> Auto-saved
    await expect(page.locator('#save-status')).toHaveText(/Saving/i, { timeout: 5000 });
    await expect(page.locator('#save-status')).toHaveText(/Saved/i, { timeout: 10000 });

    // Simulate reconnect: reload the page
    await page.reload();
    await page.waitForSelector('.monaco-editor', { timeout: 20_000 });
    
    // Wait for initial load to finish (status returns to Auto-saved/Saved)
    await expect(page.locator('#save-status')).not.toHaveText(/Saving/i, { timeout: 10000 });

    // Confirm the marker is still there. 
    // instead of innerText(), use toHaveText on the view-lines which is more reliable for Monaco
    const displayMarker = marker.replace('// ', '');
    await expect(page.locator('.view-lines')).toContainText(displayMarker, { timeout: 10000 });
  });

  test('logout button is visible and functional', async ({ page }) => {
    const username = uniqueUser();
    await registerAndLogin(page, username);

    await expect(page.getByText('Logout')).toBeVisible({ timeout: 10_000 });

    await page.click('button:has-text("Logout")');
    await page.waitForLoadState('networkidle');

    // After logout, the Login button should be back
    await expect(page.locator('button:has-text("Login")')).toBeVisible({ timeout: 10_000 });
  });
});


test.describe('Logout Flow', () => {

  test('after logout, sandbox is ephemeral (login button reappears)', async ({ page }) => {
    /**
     * WHY: After logout, the user should be treated as a guest again.
     *      Their files should NOT be loaded into the editor on reconnect.
     */
    const username = uniqueUser();
    await registerAndLogin(page, username);

    // Wait for editor
    await page.waitForSelector('.monaco-editor', { timeout: 20_000 });

    // Log out
    await page.click('button:has-text("Logout")');
    await page.waitForLoadState('networkidle');

    // After logout, user is a guest → Login button is shown, NOT the username
    await expect(page.locator('button:has-text("Login")')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(username)).not.toBeVisible();
  });
});
