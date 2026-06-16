import { test, expect } from '@playwright/test';
import { completeEntrySurvey } from '../helpers/survey';

test('homepage loads videos', async ({ page }) => {
  await page.goto('/platform');
  await completeEntrySurvey(page);
  await expect(page.getByRole('banner')).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Primary' })).toHaveCount(0);
  await expect(page.getByText('☰')).toHaveCount(0);
  await expect(page.getByText('Create')).toHaveCount(0);
  await expect(page.getByTestId('home-grid')).toBeVisible();
  await expect(page.getByTestId('video-card').first()).toBeVisible();
});

test('category chips filter the recommendation grid through URL state', async ({ page }) => {
  await page.goto('/platform');
  await completeEntrySurvey(page);
  const firstCategory = page.getByTestId('category-filter-chips').getByRole('link').nth(1);
  const label = await firstCategory.innerText();
  await firstCategory.click();
  await expect(page).toHaveURL(/category=/);
  await expect(page.getByTestId('home-grid')).toBeVisible();
  await expect(page.getByTestId('category-filter-chips').getByRole('link', { name: label })).toHaveAttribute('aria-current', 'page');
  await expect(page.getByTestId('video-card').first()).toBeVisible();
});
