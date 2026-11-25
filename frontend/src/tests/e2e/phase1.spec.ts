import { test, expect } from '@playwright/test';

const ARTIFACT_DIR =
  '/Users/gopalamghanashyam/.gemini/antigravity/brain/d092e4af-366d-4274-aca6-397ca72feefc';

test('Landing theme toggle, 360 diagram switcher, and 404 route', async ({ page }) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];

  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => {
    pageErrors.push(err.message);
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  await expect(page.getByText(/Explain science diagrams/i)).toBeVisible();

  // Switch 360° Inspector diagram
  await page.getByRole('button', { name: /Human Heart/i }).click();
  await page.getByRole('button', { name: /Water Cycle/i }).click();

  // Toggle Dark Mode
  await page.getByRole('button', { name: /Switch to dark theme/i }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.waitForTimeout(500);
  await page.screenshot({
    path: `${ARTIFACT_DIR}/final-landing-dark.png`,
    fullPage: false,
  });

  // Verify 404 route
  await page.goto('/nonexistent-route-check');
  await expect(page.getByText(/Unmapped Diagram Coordinate/i)).toBeVisible();

  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});
