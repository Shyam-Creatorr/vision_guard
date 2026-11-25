import { test, expect } from '@playwright/test';

const ARTIFACT_DIR =
  '/Users/gopalamghanashyam/.gemini/antigravity/brain/d092e4af-366d-4274-aca6-397ca72feefc/audit_evidence';
const FIXTURE_PATH =
  '/Users/gopalamghanashyam/.gemini/antigravity/scratch/visionguard-tutor-web/backend/tests/fixtures/degraded/01_plant_cell_gaussian_blur.png';

test('Bug 1 E2E: degraded upload shows preview, blocks blurred label with reason & suggestions, and gates quiz until confirmed', async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text());
  });
  page.on('pageerror', (e) => pageErrors.push(e.message));

  await page.setViewportSize({ width: 1366, height: 900 });

  // Sign up & onboard
  await page.goto('/signup');
  await page.getByLabel('Full Name').fill('Bug1 Verifier');
  await page.getByLabel('Email').fill(`bug1_after_${Date.now()}@science.edu`);
  await page.getByLabel('Password').fill('VerifyPass123');
  await page.getByRole('button', { name: /Create Account/i }).click();
  await expect(page).toHaveURL(/\/onboarding/, { timeout: 10000 });
  await page.getByRole('button', { name: /Save & Open Dashboard/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 10000 });

  // Upload degraded fixture & check instant preview + quality gate
  await page.goto('/analyze');
  await page.locator('input[type="file"]').first().setInputFiles(FIXTURE_PATH);

  await expect(page.getByAltText('Selected diagram preview')).toBeVisible();
  await expect(page.getByText('Replace')).toBeVisible();
  await expect(page.getByText('Remove')).toBeVisible();
  await expect(page.getByText('OpenCV Quality Report')).toBeVisible({ timeout: 10000 });
  await page.screenshot({ path: `${ARTIFACT_DIR}/bug1-after-upload-preview.png`, fullPage: true });

  await page.getByRole('button', { name: /Run Two-Stage Visual Audit/i }).click();
  await expect(page).toHaveURL(/\/workspace\//, { timeout: 10000 });

  // Wait for Limited Mode + blocked region card
  await expect(page.getByText(/Limited Mode/i).first()).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/region blocked|regions blocked/i)).toBeVisible();
  await expect(page.getByText(/Blocked Region ·/i)).toBeVisible();
  await expect(page.getByText(/Suggested \(unverified guess\)/i)).toBeVisible();
  await expect(page.getByText(/Show original/i)).toBeVisible();

  await page.waitForTimeout(700);
  await page.screenshot({ path: `${ARTIFACT_DIR}/bug1-after-blocked-workspace.png`, fullPage: true });

  // Toggle "Show original" to verify pixelation reveal works
  await page.getByRole('button', { name: /Show original/i }).click();
  await expect(page.getByText(/Hide original pixels/i)).toBeVisible();

  // Check Practice Mode BEFORE confirming blocked label -> blocked region must be excluded
  const workspaceUrl = page.url();
  await page.getByRole('link', { name: /Practice Mode/i }).click();
  await expect(page).toHaveURL(/\/practice\//, { timeout: 10000 });
  await expect(page.getByText(/UNVERIFIED Excluded/i)).toBeVisible();

  // Return to workspace and confirm "Golgi Apparatus"
  await page.goto(workspaceUrl);
  await expect(page.getByPlaceholder('Type my own label...')).toBeVisible({ timeout: 10000 });
  await page.getByPlaceholder('Type my own label...').fill('Golgi Apparatus');
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.getByText(/1 Confirmed by you/i)).toBeVisible({ timeout: 10000 });
  await page.screenshot({ path: `${ARTIFACT_DIR}/bug1-after-user-confirmed.png`, fullPage: true });

  // Verify Practice Mode now includes the user_confirmed label
  await page.getByRole('link', { name: /Practice Mode/i }).click();
  await expect(page).toHaveURL(/\/practice\//, { timeout: 10000 });
  await page.getByRole('button', { name: /Multiple Choice/i }).click();
  await expect(page.getByRole('button', { name: 'Golgi Apparatus' })).toBeVisible({ timeout: 10000 });

  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});
