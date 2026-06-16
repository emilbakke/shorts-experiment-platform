import { test, expect } from '@playwright/test';
import { completeEntrySurvey } from '../helpers/survey';

test('session API returns requested condition', async ({ request }) => {
  await expect.poll(async () => {
    try {
      const response = await request.post('/api/session', { data: { condition: 'treatment_problematic_content' } });
      if (!response.ok()) return false;
      const session = await response.json();
      return Boolean(session.session_id) && session.condition === 'treatment_problematic_content';
    } catch {
      return false;
    }
  }).toBeTruthy();
});

test('problematic condition exposes mixed content internally and strict logging fields', async ({ page }) => {
  await page.goto('/platform?condition=treatment_problematic_content');
  await completeEntrySurvey(page);
  await expect(page.getByTestId('home-condition')).toHaveAttribute('data-condition', 'treatment_problematic_content');
  await expect(page.getByText('problematic')).toHaveCount(0);

  const problematicCard = page.locator('[data-testid="video-card"][data-content-pool="problematic"]').first();
  await expect(problematicCard).toBeVisible();
  const title = await problematicCard.locator('h3').innerText();
  await problematicCard.getByRole('button').click();
  await expect(page).toHaveURL(/condition=treatment_problematic_content/);

  await expect.poll(async () => {
    try {
      const logs = await (await page.request.get('/api/logs')).json();
    return logs.events.some((row: { video_title: string; event_type: string; condition: string; content_pool: string; surface: string; click_from: string; user_id?: string }) =>
      row.video_title === title &&
      row.event_type === 'click' &&
      row.condition === 'treatment_problematic_content' &&
      row.content_pool === 'problematic' &&
      !!row.user_id &&
      row.surface === 'recommendation' &&
      row.click_from === 'recommendation',
    );
    } catch {
      return false;
    }
  }).toBeTruthy();
});
