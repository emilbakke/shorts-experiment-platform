import { test, expect } from '@playwright/test';
import { completeEntrySurvey } from '../helpers/survey';

test('entry survey blocks first interaction, stores demographics, and is not repeated', async ({ page }) => {
  await page.goto('/platform');
  await expect(page.getByTestId('entry-survey-modal')).toBeVisible();
  await expect(page.getByTestId('home-grid')).toHaveCount(0);
  await completeEntrySurvey(page);
  await expect(page.getByTestId('home-grid')).toBeVisible();

  await expect.poll(async () => {
    try {
      const logs = await (await page.request.get('/api/logs')).json();
      return logs.sessions.some((session: { survey_completed: boolean; gender?: string; age?: number; household_living_arrangement?: string; education?: string; region_dk?: string; left_right_orientation?: number }) =>
        session.survey_completed === true &&
        session.gender === 'woman' &&
        session.age === 24 &&
        session.household_living_arrangement === 'living_with_partner_or_roommate' &&
        !!session.education &&
        !!session.region_dk &&
        session.left_right_orientation === 5,
      );
    } catch {
      return false;
    }
  }).toBeTruthy();

  await page.reload();
  await expect(page.getByTestId('entry-survey-modal')).toHaveCount(0);
  await expect(page.getByTestId('home-grid')).toBeVisible();
});
