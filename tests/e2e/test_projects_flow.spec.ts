import { test, expect } from '@playwright/test';

// Helpers
const uniqueUser = () => `e2euser_proj_${Date.now()}`;

async function registerAndLogin(page: any, username: string, password = 'testpass123') {
  await page.goto('/');
  await page.click('button:has-text("Login")');
  await expect(page.locator('.auth-modal')).toBeVisible({ timeout: 5_000 });
  await page.click('.auth-tabs button:has-text("Register")');
  await page.fill('input[placeholder="Enter your username"]', username);
  await page.fill('input[placeholder="Enter your password"]', password);
  await page.click('button:has-text("Create Account")');
  await page.waitForLoadState('networkidle', { timeout: 15_000 });
}

test.describe('Authenticated Project Management', () => {

  test('full project CRUD workflow', async ({ page, context }) => {
    const username = uniqueUser();
    await registerAndLogin(page, username);

    // 1. Navigate to Projects Profile
    await page.click('a:has-text("Projects")');
    await expect(page).toHaveURL(/\/profile/);
    await expect(page.getByText('My Workspace')).toBeVisible();

    // 2. Create a new project
    const projectName = `Proj_${Date.now()}`;
    await page.fill('input[placeholder="Project Name..."]', projectName);
    await page.click('button:has-text("Create Project")');
    
    // Verify project card appears
    const projectCard = page.locator('.project-card.existing-project', { hasText: projectName });
    await expect(projectCard).toBeVisible({ timeout: 10_000 });

    // 3. Edit project name
    await projectCard.hover();
    await projectCard.locator('.edit-btn').click();
    
    const updatedName = `${projectName}_Updated`;
    await page.fill('.edit-input', updatedName);
    await page.click('.save-btn');
    
    // Verify name updated
    await expect(page.getByText(updatedName)).toBeVisible();

    // 4. Open in Editor (New Tab)
    const [newPage] = await Promise.all([
      context.waitForEvent('page'),
      projectCard.hover().then(() => projectCard.click()) // Click the card to open
    ]);
    
    await newPage.waitForLoadState();
    // Verify project name appears in the toolbar
    await expect(newPage.locator('.project-name')).toHaveText(updatedName, { timeout: 15_000 });

    // 5. Delete project
    // Back to profile page
    await page.bringToFront();
    const updatedCard = page.locator('.project-card.existing-project', { hasText: updatedName });
    await updatedCard.hover();
    
    // Handle dialog confirmation for delete
    page.on('dialog', dialog => dialog.accept());
    await updatedCard.locator('.delete-btn').click();
    
    // Verify project card is gone
    await expect(updatedCard).not.toBeVisible({ timeout: 10_000 });
  });

});
