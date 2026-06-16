import { test, expect } from '@playwright/test';
import { completeEntrySurvey } from '../helpers/survey';

test('search goal oriented flow', async ({ page }) => {
  await page.goto('/platform?condition=treatment_search');
  await completeEntrySurvey(page);
  const input = page.locator('input[placeholder="Søg"]');
  await expect(input).toBeVisible();
  await input.fill('technology');
  await input.press('Enter');
  await expect(page.getByRole('heading', { name: /Søgeresultater for “technology”/ })).toBeVisible();
  await expect(page.getByTestId('video-card').first()).toBeVisible();
  await page.getByTestId('video-card').first().getByRole('button').click();
  await expect(page).toHaveURL(/from=search/);
});
