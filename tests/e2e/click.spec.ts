import { expect, test } from '@playwright/test';
import { completeEntrySurvey } from '../helpers/survey';

test('recommendation click logs after impression and opens watch page', async ({ page }) => {
  await page.goto('/platform');
  await completeEntrySurvey(page);

  const firstCard = page.getByTestId('video-card').first();
  const title = await firstCard.locator('h3').innerText();
  const contentPool = await firstCard.getAttribute('data-content-pool');
  await firstCard.getByRole('button').click();

  await expect(page).toHaveURL(/\/watch\/v/);
  await expect(page.getByTestId('video-player')).toBeVisible();

  await expect.poll(async () => {
    try {
      const response = await page.request.get('/api/logs');
      const logs = await response.json();
      return logs.events.some((row: { video_title: string; event_type: string; surface: string; click_from: string; user_id?: string }) =>
        row.video_title === title &&
        row.event_type === 'click' &&
        row.condition === 'treatment_problematic_content' &&
        row.content_pool === contentPool &&
        !!row.user_id &&
        row.surface === 'recommendation' &&
        row.click_from === 'recommendation',
      );
    } catch {
      return false;
    }
  }).toBeTruthy();
});
