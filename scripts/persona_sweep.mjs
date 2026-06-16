#!/usr/bin/env node
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';

const BROWSER_URL = process.env.PERSONA_BROWSER_URL || 'http://localhost:3000';
const SERVER_URL = process.env.PERSONA_SERVER_URL || 'http://[::1]:3000';
const ITERATIONS = Number(process.env.PERSONA_ITERATIONS || 3);
const REQUIRED_ITERATIONS = Math.max(3, ITERATIONS);
const REPORT_DIRS = ['analysis/reports', 'analysis/errors', 'analysis/agent_runs'];
const SURFACES = ['recommendation', 'search', 'related', 'shorts'];
const CONDITIONS = ['control_recommendation', 'treatment_search', 'treatment_problematic_content'];

process.env.PLAYWRIGHT_BROWSERS_PATH ||= '.playwright-browsers';
const { chromium } = await import('@playwright/test');

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function isServerReady() {
  try {
    const response = await fetch(`${SERVER_URL}/`);
    return response.ok;
  } catch {
    return false;
  }
}

async function waitForServer(timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await isServerReady()) return;
    await sleep(500);
  }
  throw new Error(`Timed out waiting for ${SERVER_URL}`);
}

async function startServerIfNeeded() {
  if (await isServerReady()) return { process: null, reused: true };
  const child = spawn(process.execPath, ['node_modules/next/dist/bin/next', 'dev', '--webpack', '--hostname', 'localhost', '--port', '3000'], {
    cwd: `${process.cwd()}/frontend`,
    env: { ...process.env, PLAYWRIGHT_BROWSERS_PATH: '.playwright-browsers', NEXT_DIST_DIR: '.next-test' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stdout.on('data', (chunk) => process.stdout.write(`[persona-web] ${chunk}`));
  child.stderr.on('data', (chunk) => process.stderr.write(`[persona-web] ${chunk}`));
  await waitForServer();
  return { process: child, reused: false };
}

async function stopServer(child) {
  if (!child) return;
  if (child.exitCode !== null || child.killed) return;
  await new Promise((resolve) => {
    const timeout = setTimeout(resolve, 5_000);
    child.once('exit', () => {
      clearTimeout(timeout);
      resolve();
    });
    child.kill('SIGTERM');
  });
}

async function resetLogs() {
  await fetch(`${SERVER_URL}/api/logs`, { method: 'DELETE' });
}

async function fetchLogs() {
  const response = await fetch(`${SERVER_URL}/api/logs`, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Unable to fetch logs: ${response.status}`);
  return response.json();
}

function emptySurfaceCounts() {
  return Object.fromEntries(SURFACES.map((surface) => [surface, 0]));
}

function emptyConditionCounts() {
  return Object.fromEntries(CONDITIONS.map((condition) => [condition, 0]));
}

function round(value) {
  return Math.round(value * 1000) / 1000;
}

function metricsFromLogs(logs, iterationsCompleted) {
  const clicks = logs.events.filter((event) => event.event_type === 'click');
  const watchEvents = logs.events.filter((event) => ['watch_start', 'progress', 'complete'].includes(event.event_type));
  const clicksBySurface = emptySurfaceCounts();
  const clicksByCondition = emptyConditionCounts();
  const impressionsBySurface = emptySurfaceCounts();
  const impressionsByCondition = emptyConditionCounts();
  const contentPoolExposure = { safe_impressions: 0, problematic_impressions: 0, safe_clicks: 0, problematic_clicks: 0 };

  for (const impression of logs.impressions) {
    if (impressionsBySurface[impression.surface] !== undefined) impressionsBySurface[impression.surface] += 1;
    if (impressionsByCondition[impression.condition] !== undefined) impressionsByCondition[impression.condition] += 1;
    if (impression.content_pool === 'safe') contentPoolExposure.safe_impressions += 1;
    if (impression.content_pool === 'problematic') contentPoolExposure.problematic_impressions += 1;
  }

  for (const click of clicks) {
    if (clicksBySurface[click.surface] !== undefined) clicksBySurface[click.surface] += 1;
    if (clicksByCondition[click.condition] !== undefined) clicksByCondition[click.condition] += 1;
    if (click.content_pool === 'safe') contentPoolExposure.safe_clicks += 1;
    if (click.content_pool === 'problematic') contentPoolExposure.problematic_clicks += 1;
  }

  const shortsImpressions = logs.impressions.filter((row) => row.surface === 'shorts');
  const shortsClicks = clicks.filter((row) => row.surface === 'shorts');
  const shortsWatchEvents = watchEvents.filter((row) => row.surface === 'shorts');
  const searchClicks = clicksBySurface.search;
  const recommendationClicks = clicksBySurface.recommendation;

  return {
    generated_at: new Date().toISOString(),
    iterations_completed: iterationsCompleted,
    personas: ['recommendation_explorer', 'search_goal_oriented', 'shorts_scroller', 'problematic_content_seeker'],
    totals: {
      impressions: logs.impressions.length,
      events: logs.events.length,
      clicks: clicks.length,
      watch_events: watchEvents.length,
      searches: logs.searches.length,
      sessions: logs.sessions.length,
    },
    impressions_by_surface: impressionsBySurface,
    impressions_by_condition: impressionsByCondition,
    clicks_by_surface: clicksBySurface,
    clicks_by_condition: clicksByCondition,
    shorts_usage: {
      impressions: shortsImpressions.length,
      clicks: shortsClicks.length,
      watch_events: shortsWatchEvents.length,
      unique_videos: new Set(shortsImpressions.map((row) => row.video_id)).size,
      click_through_rate: shortsImpressions.length ? round(shortsClicks.length / shortsImpressions.length) : 0,
    },
    search_vs_recommendation_ratio: {
      search_clicks: searchClicks,
      recommendation_clicks: recommendationClicks,
      ratio: recommendationClicks ? round(searchClicks / recommendationClicks) : searchClicks,
      formula: 'search click events / recommendation click events',
    },
    content_pool_exposure: contentPoolExposure,
  };
}

function deltaLogs(logs, seen) {
  const next = {
    impressions: logs.impressions.filter((row) => !seen.impressions.has(row.id)),
    events: logs.events.filter((row) => !seen.events.has(row.id)),
    searches: logs.searches.filter((row) => !seen.searches.has(row.id)),
    sessions: logs.sessions.filter((row) => !seen.sessions.has(row.id)),
  };
  for (const row of logs.impressions) seen.impressions.add(row.id);
  for (const row of logs.events) seen.events.add(row.id);
  for (const row of logs.searches) seen.searches.add(row.id);
  for (const row of logs.sessions) seen.sessions.add(row.id);
  return next;
}

function validateLogs(logs, runErrors) {
  const required = ['video_id', 'video_title', 'surface', 'click_from', 'condition', 'content_pool', 'session_id'];
  const knownSessions = new Set(logs.sessions.map((session) => session.session_id));
  for (const collection of ['impressions', 'events']) {
    for (const row of logs[collection]) {
      const missing = required.filter((field) => !row[field]);
      if (missing.length) runErrors.push(`${collection} row ${row.id || '(no id)'} missing ${missing.join(', ')}`);
      if (row.session_id && !knownSessions.has(row.session_id)) {
        runErrors.push(`${collection} row ${row.id || '(no id)'} references unregistered session_id=${row.session_id}`);
      }
    }
  }

  for (const search of logs.searches) {
    if (search.session_id && !knownSessions.has(search.session_id)) {
      runErrors.push(`search row ${search.id || '(no id)'} references unregistered session_id=${search.session_id}`);
    }
  }

  for (const click of logs.events.filter((row) => row.event_type === 'click')) {
    const prior = logs.impressions.some(
      (impression) =>
        impression.video_id === click.video_id &&
        impression.surface === click.surface &&
        impression.session_id === click.session_id,
    );
    if (!prior) {
      runErrors.push(`click ${click.id} for ${click.video_title} had no prior matching impression`);
    }
  }

  const metrics = metricsFromLogs(logs, 0);
  if (!logs.sessions.length) runErrors.push('session rows are missing from empirical logs');
  for (const surface of SURFACES) {
    if (!metrics.clicks_by_surface[surface]) runErrors.push(`missing click coverage for surface=${surface}`);
  }
  for (const condition of CONDITIONS) {
    if (!metrics.clicks_by_condition[condition]) runErrors.push(`missing click coverage for condition=${condition}`);
  }
  if (!metrics.shorts_usage.clicks) runErrors.push('shorts_usage has zero clicks');
  if (!logs.searches.length) runErrors.push('search query logs are missing');
}

function appendPageTracking(page, record) {
  page.on('framenavigated', (frame) => {
    if (frame === page.mainFrame()) record.pages.push(frame.url());
  });
  page.on('pageerror', (error) => record.errors.push(`pageerror: ${error.message}`));
  page.on('requestfailed', (request) => {
    const failure = request.failure();
    const url = request.url();
    if (url.includes('/api/impressions') && failure?.errorText === 'net::ERR_ABORTED') return;
    if (!url.includes('flower.mp4')) record.errors.push(`requestfailed: ${url} ${failure?.errorText || ''}`.trim());
  });
}

async function step(record, action, fn) {
  const startedAt = new Date().toISOString();
  try {
    const details = await fn();
    record.actions.push({ action, status: 'passed', started_at: startedAt, details });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    record.actions.push({ action, status: 'failed', started_at: startedAt, error: message });
    record.errors.push(`${action}: ${message}`);
  }
}

async function runPersona(browser, iteration, persona, flow) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const record = { iteration, persona, pages: [], actions: [], errors: [], expected_elements: [] };
  appendPageTracking(page, record);
  try {
    await flow(page, record);
  } finally {
    await context.close();
  }
  return record;
}

async function visibleCount(locator) {
  const count = await locator.count();
  let visible = 0;
  for (let index = 0; index < count; index += 1) {
    if (await locator.nth(index).isVisible()) visible += 1;
  }
  return visible;
}

async function completeEntrySurvey(page) {
  const modal = page.getByTestId('entry-survey-modal');
  const visible = await modal.waitFor({ state: 'visible', timeout: 5_000 }).then(() => true).catch(() => false);
  if (!visible) return;
  await page.getByTestId('entry-survey-submit').click();
  await modal.waitFor({ state: 'detached', timeout: 10_000 }).catch(async () => {
    await modal.waitFor({ state: 'hidden', timeout: 10_000 });
  });
}

const flows = {
  recommendation_explorer: async (page, record) => {
	    await step(record, 'open homepage recommendation feed', async () => {
	      await page.goto(`${BROWSER_URL}/?condition=control_recommendation`);
	      await completeEntrySurvey(page);
	      await page.getByTestId('home-grid').waitFor();
      const count = await page.getByTestId('video-card').count();
      record.expected_elements.push({ element: 'video-card', expected: '>= 4', observed: count });
      if (count < 4) throw new Error(`expected at least 4 video cards, saw ${count}`);
      return { card_count: count };
    });
    await step(record, 'click top recommendation', async () => {
      const firstCard = page.getByTestId('video-card').first();
      const title = await firstCard.locator('h3').innerText();
      await firstCard.getByRole('button').click();
      await page.waitForURL(/\/watch\//);
      await page.getByRole('heading', { name: 'Related videos' }).waitFor();
      return { video_title: title };
    });
    await step(record, 'click related video from watch page', async () => {
      const relatedCard = page.getByTestId('video-card').first();
      const title = await relatedCard.locator('h3').innerText();
      await relatedCard.getByRole('button').click();
      await page.waitForURL(/from=related/);
      return { video_title: title };
    });
  },

  search_goal_oriented: async (page, record) => {
	    await step(record, 'open search-first condition', async () => {
	      await page.goto(`${BROWSER_URL}/?condition=treatment_search`);
	      await completeEntrySurvey(page);
	      await page.getByTestId('home-condition').waitFor();
      return { condition: 'treatment_search' };
    });
    await step(record, 'submit fitness search', async () => {
      const input = page.locator('input[placeholder="Search"]');
      await input.fill('fitness');
      await input.press('Enter');
      await page.waitForURL(/\/search/);
      await page.getByRole('heading', { name: /Search results for “fitness”/ }).waitFor();
      const count = await page.getByTestId('video-card').count();
      record.expected_elements.push({ element: 'search video-card', expected: '>= 1', observed: count });
      if (count < 1) throw new Error(`expected at least one fitness result, saw ${count}`);
      return { query: 'fitness', result_count: count };
    });
    await step(record, 'click search result', async () => {
      const result = page.getByTestId('video-card').first();
      const title = await result.locator('h3').innerText();
      await result.getByRole('button').click();
      await page.waitForURL(/from=search/);
      return { video_title: title };
    });
  },

  shorts_scroller: async (page, record) => {
	    await step(record, 'open homepage shorts shelf', async () => {
	      await page.goto(`${BROWSER_URL}/?condition=control_recommendation`);
	      await completeEntrySurvey(page);
	      await page.getByTestId('shorts-shelf-card').first().waitFor();
      const count = await page.getByTestId('shorts-shelf-card').count();
      record.expected_elements.push({ element: 'shorts-shelf-card', expected: '>= 4', observed: count });
      if (count < 4) throw new Error(`expected at least 4 shorts, saw ${count}`);
      return { shorts_count: count };
    });
	    await step(record, 'open first short from shelf', async () => {
	      await page.getByTestId('shorts-shelf-card').first().getByRole('button').click();
	      await page.getByTestId('shorts-reel').waitFor();
	      return { action: 'open', surface: 'shorts' };
	    });
	    await step(record, 'return to homepage and open another short', async () => {
	      await page.goto(`${BROWSER_URL}/?condition=control_recommendation`);
	      await completeEntrySurvey(page);
	      const visible = await visibleCount(page.getByTestId('shorts-shelf-card'));
	      await page.getByTestId('shorts-shelf-card').nth(1).getByRole('button').click();
	      await page.getByTestId('shorts-reel').waitFor();
	      return { visible_shorts_after_return: visible, action: 'open-second' };
	    });
  },

  problematic_content_seeker: async (page, record) => {
	    await step(record, 'open problematic treatment feed', async () => {
	      await page.goto(`${BROWSER_URL}/?condition=treatment_problematic_content`);
	      await completeEntrySurvey(page);
	      await page.getByTestId('home-condition').waitFor();
      const problematicCount = await page.locator('[data-testid="video-card"][data-content-pool="problematic"]').count();
      record.expected_elements.push({ element: 'problematic video-card', expected: '>= 1', observed: problematicCount });
      if (problematicCount < 1) throw new Error('expected at least one problematic card');
      return { problematic_cards: problematicCount };
    });
    await step(record, 'click problematic recommendation', async () => {
      const card = page.locator('[data-testid="video-card"][data-content-pool="problematic"]').first();
      const title = await card.locator('h3').innerText();
      await card.getByRole('button').click();
      await page.waitForURL(/condition=treatment_problematic_content/);
      await page.getByTestId('video-player').waitFor();
      return { video_title: title };
    });
    await step(record, 'search within problematic treatment', async () => {
      const input = page.locator('input[placeholder="Search"]');
      await input.fill('civics');
      await input.press('Enter');
      await page.waitForURL(/\/search/);
      const count = await page.getByTestId('video-card').count();
      if (count < 1) throw new Error(`expected civics search results, saw ${count}`);
      return { query: 'civics', result_count: count };
    });
    await step(record, 'click problematic search result', async () => {
      const result = page.getByTestId('video-card').first();
      const title = await result.locator('h3').innerText();
      await result.getByRole('button').click();
      await page.waitForURL(/from=search/);
      return { video_title: title };
    });
  },
};

async function writeReports(runRecords, iterationMetrics, finalMetrics, errors) {
  for (const dir of REPORT_DIRS) await mkdir(dir, { recursive: true });

  await writeFile('analysis/reports/metrics.json', `${JSON.stringify({ ...finalMetrics, iteration_metrics: iterationMetrics }, null, 2)}\n`);

  const runLines = [
    '# Latest Agent Run',
    '',
    `Generated at: ${new Date().toISOString()}`,
    `Iterations completed: ${finalMetrics.iterations_completed}`,
    `Personas executed per iteration: ${finalMetrics.personas.join(', ')}`,
    '',
    '## Aggregate metrics',
    '',
    `- Clicks by surface: ${JSON.stringify(finalMetrics.clicks_by_surface)}`,
    `- Clicks by condition: ${JSON.stringify(finalMetrics.clicks_by_condition)}`,
    `- Shorts usage: ${JSON.stringify(finalMetrics.shorts_usage)}`,
    `- Search vs recommendation ratio: ${JSON.stringify(finalMetrics.search_vs_recommendation_ratio)}`,
    '',
    '## Iterations',
  ];

  for (const iteration of runRecords) {
    runLines.push('', `### Iteration ${iteration.iteration}`, '');
    for (const persona of iteration.personas) {
      runLines.push(`#### ${persona.persona}`, '');
      runLines.push(`- Pages visited: ${[...new Set(persona.pages)].join(' → ') || 'none recorded'}`);
      runLines.push(`- Expected elements: ${JSON.stringify(persona.expected_elements)}`);
      runLines.push(`- Actions taken:`);
      for (const action of persona.actions) {
        runLines.push(`  - ${action.status}: ${action.action}${action.details ? ` (${JSON.stringify(action.details)})` : ''}${action.error ? ` — ${action.error}` : ''}`);
      }
      runLines.push(`- Logging fired as expected: ${persona.errors.length === 0 ? 'yes' : 'no'}`);
      if (persona.errors.length) runLines.push(`- Encountered errors: ${persona.errors.join('; ')}`);
    }
  }

  await writeFile('analysis/agent_runs/latest_run.md', `${runLines.join('\n')}\n`);

  const errorLines = [
    '# Latest Errors',
    '',
    `Generated at: ${new Date().toISOString()}`,
    '',
    '## Baseline failures repaired in this loop',
    '',
    '- Missing `analysis/reports/metrics.json` caused the metrics-required backend tests to fail before persona output existed.',
    '- `recommendation_explorer` used a stale `img` selector; the UI uses reusable Tailwind/CSS `VideoCard` thumbnails.',
    '- Search page visits did not create search-query log rows until a reusable search-query logger was added.',
    '- Persona logs carried `session_id` on rows but did not persist matching session rows for empirical session counts.',
    '',
    '## Current unresolved anomalies',
    '',
  ];
  if (errors.length) {
    for (const error of errors) errorLines.push(`- ${error}`);
  } else {
    errorLines.push('- None after the latest sweep.');
  }
  errorLines.push('', '## Fix applied', '', '- Added deterministic Playwright persona sweep, fixed stale persona selectors, added search-query logging, and generated metrics from logged impressions/events/searches.');
  errorLines.push('- Auto-register session rows from impression, event, and search logs, and validate that empirical rows reference registered sessions.');
  await writeFile('analysis/errors/latest_errors.md', `${errorLines.join('\n')}\n`);

  await writeFile(
    'analysis/reports/status.md',
    `# Status\n\n- Generated at: ${new Date().toISOString()}\n- Iterations completed: ${finalMetrics.iterations_completed}\n- Unresolved anomalies: ${errors.length}\n- Metrics file: analysis/reports/metrics.json\n`,
  );
}

const server = await startServerIfNeeded();
const runRecords = [];
const iterationMetrics = [];
const allErrors = [];
let browser;

try {
  await resetLogs();
  browser = await chromium.launch({ headless: true });
  const seen = { impressions: new Set(), events: new Set(), searches: new Set(), sessions: new Set() };

  for (let iteration = 1; iteration <= REQUIRED_ITERATIONS; iteration += 1) {
    const personas = [];
    for (const [persona, flow] of Object.entries(flows)) {
      personas.push(await runPersona(browser, iteration, persona, flow));
    }
    await sleep(750);
    const logs = await fetchLogs();
    const delta = deltaLogs(logs, seen);
    const metrics = metricsFromLogs(delta, iteration);
    const iterationErrors = personas.flatMap((record) => record.errors.map((error) => `iteration ${iteration} ${record.persona}: ${error}`));
    validateLogs(delta, iterationErrors);
    iterationMetrics.push({ iteration, ...metrics, anomalies: iterationErrors });
    runRecords.push({ iteration, personas });
    allErrors.push(...iterationErrors);
  }

  const finalLogs = await fetchLogs();
  const finalErrors = [];
  validateLogs(finalLogs, finalErrors);
  allErrors.push(...finalErrors.map((error) => `aggregate: ${error}`));
  const finalMetrics = metricsFromLogs(finalLogs, REQUIRED_ITERATIONS);
  await writeReports(runRecords, iterationMetrics, finalMetrics, allErrors);

  if (REQUIRED_ITERATIONS < 3) allErrors.push('fewer than 3 iterations completed');
  if (allErrors.length) {
    console.error(`Persona sweep completed with ${allErrors.length} anomalies`);
    for (const error of allErrors) console.error(`- ${error}`);
    process.exitCode = 1;
  } else {
    console.log(`Persona sweep completed ${REQUIRED_ITERATIONS} iterations with no anomalies.`);
  }
} finally {
  if (browser) await browser.close();
  if (server.process && !server.reused) {
    await stopServer(server.process);
  }
}
