import { test, expect } from '@playwright/test';
import { completeEntrySurvey } from '../helpers/survey';

test('recommendation explorer flow', async ({ page }) => {
  await page.goto('/platform');
  await completeEntrySurvey(page);
  await page.waitForLoadState('networkidle');

  const cards = page.getByTestId('video-card');
  await expect(cards.first()).toBeVisible();
  await cards.first().getByRole('button').click();

  await expect(page.getByTestId('video-player')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Relaterede videoer' })).toBeVisible();
});
