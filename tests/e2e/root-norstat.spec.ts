import { expect, test, type Page } from "@playwright/test";

async function storedStudySessionId(page: Page) {
  return page.evaluate(() => {
    const session = JSON.parse(window.localStorage.getItem("exp-video-study-shorts-experiment") ?? "{}");
    return (session.session_id ?? session.study_id) as string;
  });
}

test("root route opens the Shorts experiment and preserves Norstat pid", async ({ page }) => {
  await page.goto("/?pid=1001&duration_seconds=2");
  await expect(page).toHaveURL(/\/\?pid=1001&duration_seconds=2$/);
  await expect(page.getByRole("heading", { name: "Undersøgelse om Shorts-videoer" })).toBeVisible();
  await page.getByTestId("study-entry-consent").check();
  await expect(page.getByTestId("study-entry-decline")).toBeDisabled();
  await page.getByTestId("study-entry-start").click();
  await expect(page).toHaveURL(/\/study\/shorts-experiment\/pre\?pid=1001&duration_seconds=2$/);
  const storedPid = await page.evaluate(() => {
    const raw = window.localStorage.getItem("exp-video-study-shorts-experiment");
    return raw ? JSON.parse(raw).norstat_pid as string | null : null;
  });
  expect(storedPid).toBe("1001");
  const session = await (await page.request.get(`/api/session?session_id=${encodeURIComponent(await storedStudySessionId(page))}`)).json();
  expect(session.consent_status).toBe("accepted");
  expect(session.consented_at).toBeTruthy();
});

test("declining consent redirects the participant to Norstat Screened", async ({ page }) => {
  await page.route("https://webs.norstatsurveys.com/z/Screened**", (route) => route.fulfill({ status: 200, body: "screened" }));
  await page.goto("/?pid=DECLINE_1001");
  await expect.poll(async () => page.evaluate(() => JSON.parse(window.localStorage.getItem("exp-video-study-shorts-experiment") ?? "{}").norstat_pid)).toBe("DECLINE_1001");
  const sessionId = await storedStudySessionId(page);

  const screenedRequest = page.waitForRequest((request) => request.url().startsWith("https://webs.norstatsurveys.com/z/Screened"));
  await page.getByTestId("study-entry-decline").click({ noWaitAfter: true });

  expect((await screenedRequest).url()).toBe("https://webs.norstatsurveys.com/z/Screened");
  await expect.poll(async () => {
    const session = await (await page.request.get(`/api/session?session_id=${encodeURIComponent(sessionId)}`)).json();
    return { consent_status: session.consent_status, screened_reason: session.screened_reason, screened_at: Boolean(session.screened_at) };
  }).toEqual({ consent_status: "declined", screened_reason: "declined_participation", screened_at: true });
});

test("selecting age 65+ redirects the participant to Norstat Screened", async ({ page }) => {
  await page.route("https://webs.norstatsurveys.com/z/Screened**", (route) => route.fulfill({ status: 200, body: "screened" }));
  await page.goto("/?pid=AGE_65_PLUS");
  await page.getByTestId("study-entry-consent").check();
  await page.getByTestId("study-entry-start").click();
  await expect(page).toHaveURL(/\/study\/shorts-experiment\/pre\?pid=AGE_65_PLUS$/);
  const sessionId = await storedStudySessionId(page);

  const screenedRequest = page.waitForRequest((request) => request.url().startsWith("https://webs.norstatsurveys.com/z/Screened"));
  await page.getByLabel("Aldersgruppe").selectOption("65+");

  expect((await screenedRequest).url()).toBe("https://webs.norstatsurveys.com/z/Screened");
  const session = await (await page.request.get(`/api/session?session_id=${encodeURIComponent(sessionId)}`)).json();
  expect(session.consent_status).toBe("accepted");
  expect(session.screened_reason).toBe("age_65_plus");
  expect(session.screened_at).toBeTruthy();
});
