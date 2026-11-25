import { test, expect } from '@playwright/test';

const ARTIFACT_DIR =
  '/Users/gopalamghanashyam/.gemini/antigravity/brain/d092e4af-366d-4274-aca6-397ca72feefc';

test('Full E2E: Landing 360 -> Signup -> Onboarding -> Demo Workspace 2D & 3D -> Practice Mode', async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];

  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => {
    pageErrors.push(err.message);
  });

  await page.setViewportSize({ width: 1440, height: 900 });

  // 1. Landing Page with 3D Hero & 360 Diagram Inspector
  await page.goto('/');
  await expect(page.getByText(/Explain science diagrams/i)).toBeVisible();
  await expect(page.getByText(/360° Interactive Diagram Inspector/i)).toBeVisible();
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${ARTIFACT_DIR}/final-landing-360.png`, fullPage: false });

  // 2. Sign Up & Onboarding
  const uniqueEmail = `e2e_${Date.now()}@science.edu`;
  await page.goto('/signup');
  await expect(page.getByText(/Create your VisionGuard account/i)).toBeVisible();
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${ARTIFACT_DIR}/final-auth-split.png` });

  await page.getByLabel('Full Name').fill('Rosalind Franklin');
  await page.getByLabel('Email').fill(uniqueEmail);
  await page.getByLabel('Password').fill('ScienceDNA51');
  await page.getByRole('button', { name: /Create Account/i }).click();

  await expect(page).toHaveURL(/\/onboarding/, { timeout: 10000 });
  await page.getByRole('button', { name: /Save & Open Dashboard/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 10000 });
  await expect(page.getByText(/Welcome back, Rosalind Franklin/i)).toBeVisible();
  await page.screenshot({ path: `${ARTIFACT_DIR}/final-dashboard.png` });

  // 3. Demo Mode Analysis -> Workspace 2D + 360 3D View
  await page.goto('/analyze');
  await expect(page.getByText(/Instant Demo Mode/i)).toBeVisible();
  await page.getByRole('button', { name: /Run Demo Audit/i }).first().click();

  await expect(page).toHaveURL(/\/workspace\//, { timeout: 10000 });
  await expect(page.getByText(/Blocked Regions \(1\)/i)).toBeVisible({ timeout: 10000 });
  await expect(page.getByText(/Reference Rubric Comparison/i)).toBeVisible();
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${ARTIFACT_DIR}/final-workspace-2d.png`, fullPage: true });

  // Toggle 360° 3D View
  await page.getByRole('button', { name: /360° 3D View/i }).click();
  await expect(page.getByText(/360° Interactive 3D Audit/i)).toBeVisible();
  await page.waitForTimeout(900);
  await page.screenshot({ path: `${ARTIFACT_DIR}/final-workspace-360-3d.png` });

  // 4. Blank-Label Practice Mode
  await page.getByRole('link', { name: /Practice Mode/i }).click();
  await expect(page).toHaveURL(/\/practice\//, { timeout: 10000 });
  await expect(page.getByText(/Blank-Label Practice Mode/i)).toBeVisible();
  await expect(page.getByText(/1 UNVERIFIED Excluded/i)).toBeVisible();

  await page.getByPlaceholder(/Type label for \[1\]/i).fill('Cell Wall');
  await page.getByPlaceholder(/Type label for \[2\]/i).fill('Chloroplast');
  await page.getByRole('button', { name: /Check Answers/i }).click();
  await expect(page.getByText(/Result:/i)).toBeVisible({ timeout: 10000 });
  await page.screenshot({ path: `${ARTIFACT_DIR}/final-practice-mode.png`, fullPage: true });

  // 5. Verify Tutorial, Library, Progress, Settings, Teacher & Mobile responsive check
  await page.goto('/tutorial');
  await expect(page.getByText(/Learn How VisionGuard Works/i)).toBeVisible();
  await page.goto('/library');
  await expect(page.getByText(/Saved Diagram Library/i)).toBeVisible();
  await page.goto('/progress');
  await expect(page.getByText(/Achievement Badges/i)).toBeVisible();
  await page.goto('/settings');
  await expect(page.getByText(/Profile & Settings/i)).toBeVisible();
  await page.goto('/teacher');
  await expect(page.getByText(/Teacher/i).first()).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByText(/Explain science diagrams/i)).toBeVisible();

  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});
