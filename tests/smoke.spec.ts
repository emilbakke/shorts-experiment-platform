import { expect, test } from '@playwright/test';
import { completeEntrySurvey } from './helpers/survey';

test('homepage follows YouTube layout, embeds Shorts, and logs impression before click', async ({ page }) => {
  await page.goto('/platform');
  await completeEntrySurvey(page);

  await expect(page.getByRole('banner')).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Primary' })).toHaveCount(0);
  await expect(page.getByText('☰')).toHaveCount(0);
  await expect(page.getByText('Create')).toHaveCount(0);
  await expect(page.getByTestId('shorts-shelf')).toBeVisible();
  await expect(page.getByTestId('shorts-shelf-card').first()).toBeVisible();
  await expect(page.getByTestId('home-grid')).toBeVisible();
  await expect(page.getByTestId('video-card').first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Shorts', exact: true })).toHaveCount(0);
  await expect(page.getByText('problematic')).toHaveCount(0);

  const firstCard = page.getByTestId('video-card').first();
  const title = await firstCard.locator('h3').innerText();
  await expect.poll(async () => {
    try {
      const logsResponse = await page.request.get(`/api/logs?ts=${Date.now()}`);
      if (!logsResponse.ok()) return false;
      const logs = await logsResponse.json();
      return logs.impressions.some((row: { video_title: string; surface: string; user_id?: string }) => row.video_title === title && row.surface === 'recommendation' && !!row.user_id);
    } catch {
      return false;
    }
  }, { timeout: 30_000 }).toBeTruthy();
  await firstCard.getByRole('button').click();
  await expect(page).toHaveURL(/\/watch\/v/);
  await expect(page.getByTestId('video-player')).toBeVisible();

  await expect.poll(async () => {
    try {
      const logsResponse = await page.request.get('/api/logs');
      if (!logsResponse.ok()) return false;
      const logs = await logsResponse.json();
      const impressionIndex = logs.impressions.findIndex((row: { video_title: string; surface: string; user_id?: string }) => row.video_title === title && row.surface === 'recommendation' && !!row.user_id);
      const clickIndex = logs.events.findIndex((row: { video_title: string; event_type: string; click_from: string; user_id?: string }) => row.video_title === title && row.event_type === 'click' && row.click_from === 'recommendation' && !!row.user_id);
      return impressionIndex >= 0 && clickIndex >= 0;
    } catch {
      return false;
    }
  }).toBeTruthy();
});

test('search results use the search surface', async ({ page }) => {
  await page.goto('/search?q=technology');
  await completeEntrySurvey(page);
  await expect(page.getByRole('heading', { name: /Søgeresultater for “technology”/ })).toBeVisible();
  await expect(page.getByTestId('video-card').first()).toBeVisible();
  await page.getByTestId('video-card').first().getByRole('button').click();
  await expect(page).toHaveURL(/from=search/);
});

test('watch page shows 70/30 player and related list hierarchy', async ({ page }) => {
  await page.goto('/watch/v2?from=recommendation');
  await completeEntrySurvey(page);
  await expect(page.getByTestId('video-player')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Relaterede videoer' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'How Recommendation Systems Rank Videos' })).toBeVisible();
});

test('shorts shelf logs shorts clicks distinctly', async ({ page }) => {
  await page.goto('/platform');
  await completeEntrySurvey(page);
  await expect(page.getByTestId('shorts-shelf-card').first()).toBeVisible();
  const firstShort = page.getByTestId('shorts-shelf-card').first();
  const beforeLogs = await (await page.request.get(`/api/logs?ts=${Date.now()}`)).json();
  const priorEventIds = new Set(
    beforeLogs.events.map((row: { id: string }) => row.id),
  );
  await firstShort.getByRole('button').click();
  await expect(page.getByTestId('shorts-reel')).toBeVisible();
  await expect(page.getByTestId('shorts-next')).toBeVisible();

  await expect.poll(async () => {
    try {
      const logs = await (await page.request.get(`/api/logs?ts=${Date.now()}`)).json();
      const shortClicks = logs.events.filter((row: { id: string; event_type: string; surface: string; click_from: string; condition: string; user_id?: string }) =>
        row.event_type === 'click' &&
        row.condition === 'treatment_problematic_content' &&
        row.surface === 'shorts' &&
        row.click_from === 'shorts' &&
        !!row.user_id &&
        !priorEventIds.has(row.id),
      );
      return shortClicks.length > 0;
    } catch {
      return false;
    }
  }).toBeTruthy();
});

test('logging API rejects clicks before impressions and stores required fields', async ({ request }) => {
  const recommendations = await request.get('/api/recommendations?condition=control_recommendation&content_pool=safe');
  expect(recommendations.ok()).toBeTruthy();
  const firstVideo = (await recommendations.json())[0] as {
    id: string;
    title: string;
    contentPool?: 'safe' | 'problematic';
    content_pool?: 'safe' | 'problematic';
    rank?: number;
  };
  const contentPool = firstVideo.content_pool ?? firstVideo.contentPool ?? 'safe';
  const rank = firstVideo.rank ?? 1;
  const contractPayload = {
    user_id: 'contract-user',
    video_id: firstVideo.id,
    video_title: firstVideo.title,
    surface: 'recommendation',
    click_from: 'recommendation',
    rank,
    session_id: `contract-session-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    condition: 'control_recommendation',
    content_pool: contentPool,
    gender: 'woman',
  } as const;

  const missingClickFrom = await request.post('/api/impressions', {
    data: (({ click_from: _clickFrom, ...rest }) => rest)(contractPayload),
  });
  expect(missingClickFrom.status()).toBe(400);

  const rejected = await request.post('/api/events', {
    data: { ...contractPayload, event_type: 'click', session_id: 'no-impression-session' },
  });
  expect(rejected.status()).toBe(400);

  const impression = await request.post('/api/impressions', { data: contractPayload });
  expect(impression.ok()).toBeTruthy();
  const click = await request.post('/api/events', { data: { ...contractPayload, event_type: 'click' } });
  expect(click.ok()).toBeTruthy();
  const row = await click.json();
  expect(row).toMatchObject({
    user_id: 'contract-user',
    video_id: contractPayload.video_id,
    video_title: contractPayload.video_title,
    surface: 'recommendation',
    click_from: 'recommendation',
    rank,
    event_type: 'click',
    condition: 'control_recommendation',
    content_pool: contentPool,
    gender: 'woman',
  });
  expect(row.timestamp).toBeTruthy();
});
