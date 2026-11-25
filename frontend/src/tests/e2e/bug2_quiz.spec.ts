import { test, expect } from '@playwright/test';

const ARTIFACT_DIR =
  '/Users/gopalamghanashyam/.gemini/antigravity/brain/d092e4af-366d-4274-aca6-397ca72feefc/audit_evidence';

test('Bug 2 E2E: 100% on right answers, exact key on wrong answer, reshuffle consistency', async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text());
  });

  await page.setViewportSize({ width: 1366, height: 900 });
  await page.goto('/analyze');
  await page.getByRole('button', { name: /Run Demo Audit/i }).first().click();
  await expect(page).toHaveURL(/\/workspace\//, { timeout: 10000 });
  await expect(page.getByText(/Grounded Explanation Steps/i)).toBeVisible({ timeout: 10000 });

  await page.getByRole('link', { name: /Practice Mode/i }).click();
  await expect(page).toHaveURL(/\/practice\//, { timeout: 10000 });
  await expect(page.getByText(/Blank-Label Practice Mode/i)).toBeVisible();

  // Fill all 5 verified blanks (including plural/hyphen variations) -> expect 100%
  await page.getByPlaceholder(/Type label for \[1\]/i).fill('cell-wall');
  await page.getByPlaceholder(/Type label for \[2\]/i).fill('chloroplasts');
  await page.getByPlaceholder(/Type label for \[3\]/i).fill('Mitochondrion');
  await page.getByPlaceholder(/Type label for \[4\]/i).fill('Central Vacuole');
  await page.getByPlaceholder(/Type label for \[5\]/i).fill('Nucleus');
  await page.getByRole('button', { name: /Check Answers/i }).click();
  await expect(page.getByText(/Result: 5\/5 \(100%\)/i)).toBeVisible({ timeout: 10000 });
  await page.screenshot({ path: `${ARTIFACT_DIR}/bug2-after-100pct.png`, fullPage: true });

  // Reshuffle & reload, type one wrong answer -> expect exact key for that blank only
  await page.getByRole('button', { name: /Reshuffle & Retake/i }).click();
  await page.getByPlaceholder(/Type label for \[1\]/i).fill('WrongGuess');
  await page.getByPlaceholder(/Type label for \[2\]/i).fill('Chloroplast');
  await page.getByRole('button', { name: /Check Answers/i }).click();
  await expect(page.getByText(/Correct answer: Cell Wall/i)).toBeVisible({ timeout: 10000 });
  await page.screenshot({ path: `${ARTIFACT_DIR}/bug2-after-wrong-key.png`, fullPage: true });

  expect(consoleErrors).toEqual([]);
});
