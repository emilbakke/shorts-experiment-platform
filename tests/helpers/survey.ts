import { expect, type Page } from '@playwright/test';

export async function completeEntrySurvey(page: Page) {
  const modal = page.getByTestId('entry-survey-modal');
  const visible = await modal.waitFor({ state: 'visible', timeout: 5000 }).then(() => true).catch(() => false);
  if (visible) {
    await page.getByTestId('entry-survey-submit').click();
    await expect(modal).toHaveCount(0);
  }
}
