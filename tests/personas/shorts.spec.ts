import { test, expect } from '@playwright/test';
import { completeEntrySurvey } from '../helpers/survey';

test('shorts shelf flow', async ({ page }) => {
  await page.goto('/platform');
  await completeEntrySurvey(page);
  await expect(page.getByTestId('shorts-shelf')).toBeVisible();
  await expect(page.getByTestId('shorts-shelf-card').first()).toBeVisible();
  await page.getByTestId('shorts-shelf-card').first().getByRole('button').click();
  await expect(page.getByTestId('shorts-reel')).toBeVisible();
});
