import { test, expect } from '@playwright/test';
import { completeEntrySurvey } from '../helpers/survey';

test('homepage embeds Shorts shelf without a separate visible Shorts nav destination', async ({ page }) => {
  await page.goto('/platform');
  await completeEntrySurvey(page);
  await expect(page.getByTestId('shorts-shelf')).toBeVisible();
  await expect(page.getByTestId('shorts-shelf-card').first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Shorts', exact: true })).toHaveCount(0);
  await expect(page.getByTestId('shorts-reel')).toHaveCount(0);
  await expect(page.getByText(/Use ArrowDown/i)).toHaveCount(0);

  await page.getByTestId('shorts-shelf-card').first().getByRole('button').click();
  await expect(page.getByTestId('shorts-reel')).toBeVisible();
  await expect(page.getByTestId('shorts-card')).toBeVisible();
  await expect(page.getByTestId('shorts-next')).toBeVisible();
  await expect(page.getByLabel('Comments')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Luk videofeed|Forlad sessionen/ })).toHaveCount(0);
  await expect(page.getByTestId('shorts-surface-toggle')).toHaveCount(0);
  await expect(page.getByLabel(/Slå lyd/)).toHaveCount(0);

  const reel = page.getByTestId('shorts-reel');
  const likeButton = reel.getByLabel('Like');
  const shareButton = reel.getByLabel('Del');
  await expect(likeButton).toHaveAttribute('data-active', 'false');
  await expect(shareButton).toHaveAttribute('data-active', 'false');
  await likeButton.click();
  await shareButton.click();
  await expect(likeButton).toHaveAttribute('data-active', 'true');
  await expect(shareButton).toHaveAttribute('data-active', 'true');

  const firstTitle = await page.getByTestId('shorts-card').locator('h2').textContent();
  await page.evaluate(() => {
    const surface = document.querySelector('[data-testid="shorts-card"] > div');
    if (!surface) throw new Error('shorts swipe surface not found');
    const startTouch = new Touch({ identifier: 1, target: surface, clientX: 180, clientY: 540 });
    const endTouch = new Touch({ identifier: 1, target: surface, clientX: 180, clientY: 300 });
    surface.dispatchEvent(new TouchEvent('touchstart', { bubbles: true, touches: [startTouch], changedTouches: [startTouch] }));
    surface.dispatchEvent(new TouchEvent('touchend', { bubbles: true, touches: [], changedTouches: [endTouch] }));
  });
  await expect.poll(async () => page.getByTestId('shorts-card').locator('h2').textContent()).not.toBe(firstTitle);

  await page.getByTestId('shorts-next').click();
  await expect(page.getByTestId('shorts-card')).toBeVisible();
  await expect(page.getByTestId('shorts-surface-toggle')).toHaveCount(0);
});
