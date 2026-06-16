import { test, expect } from '@playwright/test';
import { completeEntrySurvey } from '../helpers/survey';

test('search flow keeps search clicks distinct from recommendations', async ({ page }) => {
  await page.goto('/search?q=technology');
  await completeEntrySurvey(page);

  await expect(page.getByRole('heading', { name: /Søgeresultater for “technology”/ })).toBeVisible();
  await expect(page.getByTestId('video-card').first()).toBeVisible();

  const firstCard = page.getByTestId('video-card').first();
  const resultTitle = await firstCard.locator('h3').innerText();
  const contentPool = await firstCard.getAttribute('data-content-pool');
  await firstCard.getByRole('button').click();
  await expect(page).toHaveURL(/from=search/);

  await expect.poll(async () => {
    try {
      const response = await page.request.get('/api/logs');
      const logs = await response.json();
      return logs.events.some((row: { video_title: string; event_type: string; surface: string; click_from: string; user_id?: string }) =>
        row.video_title === resultTitle &&
        row.event_type === 'click' &&
        row.condition === 'treatment_problematic_content' &&
        row.content_pool === contentPool &&
        !!row.user_id &&
        row.surface === 'search' &&
        row.click_from === 'search',
      );
    } catch {
      return false;
    }
  }).toBeTruthy();
});
