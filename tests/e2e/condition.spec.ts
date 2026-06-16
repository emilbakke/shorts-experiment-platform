import { test, expect } from '@playwright/test';
import { completeEntrySurvey } from '../helpers/survey';

test('condition stays internal while the YouTube-like homepage remains available', async ({ page }) => {
  await page.goto('/platform?condition=treatment_search');
  await completeEntrySurvey(page);
  await expect(page.getByTestId('home-condition')).toHaveAttribute('data-condition', 'treatment_search');
  await expect(page.getByTestId('shorts-shelf')).toBeVisible();
  await expect(page.getByTestId('home-grid')).toBeVisible();
  await expect(page.getByText('treatment_search')).toHaveCount(0);
  await expect(page.getByText(/condition:/i)).toHaveCount(0);
});
