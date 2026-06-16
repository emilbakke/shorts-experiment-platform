import { test, expect } from '@playwright/test';
import { completeEntrySurvey } from '../helpers/survey';

test('problematic content seeker flow', async ({ page }) => {
  await page.goto('/platform?condition=treatment_problematic_content');
  await completeEntrySurvey(page);

  await expect(page.getByTestId('home-condition')).toHaveAttribute('data-condition', 'treatment_problematic_content');
  const problematicCard = page.locator('[data-testid="video-card"][data-content-pool="problematic"]').first();
  await expect(problematicCard).toBeVisible();
  await problematicCard.getByRole('button').click();

  await expect(page.getByTestId('video-player')).toBeVisible();
  await expect(page.getByTestId('watch-condition')).toHaveAttribute('data-condition', 'treatment_problematic_content');
});
