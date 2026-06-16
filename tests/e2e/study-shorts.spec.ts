import { expect, test, type Page } from "@playwright/test";

async function storedStudySessionId(page: Page) {
  return page.evaluate(() => JSON.parse(window.localStorage.getItem("exp-video-study-shorts-experiment") ?? "{}").session_id as string);
}

async function fillRequiredPreSurvey(page: Page, platformUse: "never" | "youtube" = "youtube") {
  await page.getByLabel("Aldersgruppe").selectOption("21-24");
  await page.getByLabel("Køn").selectOption("prefer_not_to_say");
  await page.getByLabel("Højeste gennemførte uddannelse").selectOption("gymnasium");
  await page.getByLabel("Boligsituation").selectOption("alene");
  await page.getByLabel("Hvad beskriver bedst din nuværende beskæftigelse?").selectOption("studerende");
  await page.getByTestId("study-video-platform-use").selectOption(platformUse === "never" ? "never" : "daily");
  if (platformUse === "youtube") {
    await page.getByRole("button", { name: "YouTube" }).click();
  }
}

async function fillRequiredPostSurvey(page: Page) {
  for (const name of [
    "post-feminist-attitude",
    "post-feminism-taken-too-far",
    "post-traditional-gender-attitude",
    "post-harder-to-be-a-man",
    "post-division",
    "post-gender-conflict-exaggeration",
    "post-online-misinformation",
  ]) {
    await page.getByTestId(`${name}-4`).click();
  }
  await page.getByTestId("post-content-type-ved_ikke_husker_ikke").click();
}

test("dedicated shorts study route exists and advances through the guarded flow", async ({ page }) => {
  await page.goto("/study/shorts-experiment?pid=TEST_E2E&duration_seconds=2");
  await expect(page).toHaveURL(/\/study\/shorts-experiment\?pid=TEST_E2E&duration_seconds=2$/);
  await expect(page.getByRole("heading", { name: "Undersøgelse om Shorts-videoer" })).toBeVisible();
  await expect(page.getByText("Samtykkeerklæring")).toBeVisible();
  await expect(page.getByText("Syddansk Universitet om korte videoer og holdninger")).toBeVisible();
  await expect(page.getByText("4 minutters videofeed")).toBeVisible();
  await expect(page.getByText("pseudonymiseres i analysen")).toBeVisible();
  await expect(page.getByText("resultater rapporteres kun samlet")).toBeVisible();
  await expect(page.getByText("Behandlingsgrundlaget er dit samtykke, jf. GDPR artikel 6, stk. 1, litra a")).toBeVisible();
  await expect(page.getByText("Data opbevares på SDU/UCloud-infrastruktur med adgang begrænset til autoriserede forskere")).toBeVisible();
  await expect(page.getByText("trække dit samtykke tilbage")).toBeVisible();
  await expect(page.getByText("Har du spørgsmål, kan du kontakte os på emilbj@sam.sdu.dk.")).toBeVisible();
  await expect(page.getByText("Jeg giver samtykke til at mine svar bruges til forskning i overensstemmelse med ovenstående information.")).toBeVisible();
  await page.getByTestId("study-entry-consent").check();
  await page.getByTestId("study-entry-start").click();

  await expect(page).toHaveURL(/\/study\/shorts-experiment\/pre\?pid=TEST_E2E&duration_seconds=2$/);
  await expect(page.getByRole("heading", { name: "Før videosessionen" })).toBeVisible();
  await expect(page.getByLabel("Aldersgruppe")).toHaveValue("");
  await expect(page.getByLabel("Boligsituation")).toContainText("Bor sammen med en eller flere");
  await expect(page.getByText("Valgt: 5")).toBeVisible();
  await expect(page.getByTestId("study-video-platform-use")).toContainText("Aldrig");
  await expect(page.getByRole("button", { name: "YouTube" })).toHaveAttribute("aria-pressed", "false");
  await fillRequiredPreSurvey(page);
  await page.getByTestId("study-pre-submit").click();

  await expect(page).toHaveURL(/\/study\/shorts-experiment\/instructions\?pid=TEST_E2E&duration_seconds=2$/);
  const preparedSessionId = await storedStudySessionId(page);
  const preparedSession = await (await page.request.get(`/api/session?session_id=${encodeURIComponent(preparedSessionId)}`)).json();
  expect(preparedSession.study_state).toBe("assigned");
  await expect(page.getByRole("heading", { name: "Sådan bruger du videofeedet" })).toBeVisible();
  await expect(page.getByTestId("study-instructions")).toBeVisible();
  await expect(page.getByText("Bliv i feedet, indtil tiden er gået (4 minutter) for at gennemføre studiet.")).toBeVisible();
  await expect(page.getByText("Skru op for lyden på din telefon, inden du starter.")).toBeVisible();
  await expect(page.getByText("det er ikke vigtigt du ser en video færdig")).toBeVisible();
  await expect(page.getByTestId("study-attention-elephant")).toBeVisible();
  await expect(page.getByTestId("study-instructions-start")).toBeDisabled();
  await page.getByTestId("study-attention-answer-elefant").click();
  await expect(page.getByTestId("study-attention-message")).toContainText("Skru op for lyden");
  await page.getByTestId("study-attention-answer-hund").click();
  await expect(page.getByTestId("study-attention-message")).toContainText("Korrekt");
  await page.getByTestId("study-instructions-start").click();

  await expect(page).toHaveURL(/\/study\/shorts-experiment\/reel\?pid=TEST_E2E&duration_seconds=2$/);
  await expect(page.getByTestId("study-timer")).toBeVisible();
  await expect(page.getByTestId("shorts-reel")).toBeVisible();
  await expect(page.getByText("Korte videoer")).toHaveCount(0);
  await expect(page.getByText(/visninger/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Luk videofeed|Forlad sessionen/ })).toHaveCount(0);
  await page.getByTestId("shorts-first-start").click();
  await page.getByTestId("shorts-reel").locator("video").dispatchEvent("playing");

  const studySessionId = await page.evaluate(() => {
    const raw = window.localStorage.getItem("exp-video-study-shorts-experiment");
    return raw ? JSON.parse(raw).session_id as string : "";
  });
  await expect.poll(async () => {
    const logs = await (await page.request.get(`/api/logs?ts=${Date.now()}`)).json();
    const matchingImpressions = logs.impressions.filter((row: { user_id?: string; session_id?: string; surface?: string }) =>
      row.user_id === "norstat-TEST_E2E" && row.session_id === studySessionId && row.surface === "shorts",
    );
    const matchingEvents = logs.events.filter((row: { user_id?: string; session_id?: string; surface?: string }) =>
      row.user_id === "norstat-TEST_E2E" && row.session_id === studySessionId && row.surface === "shorts",
    );
    return matchingImpressions.length > 0 && matchingEvents.length > 0;
  }).toBeTruthy();

  await expect(page).toHaveURL(/\/study\/shorts-experiment\/post\?pid=TEST_E2E&duration_seconds=2$/, { timeout: 8000 });
  await expect(page.getByRole("heading", { name: "Afsluttende spørgsmål" })).toBeVisible();
  await expect(page.getByTestId("study-post-form")).toBeVisible();
  await expect(page.getByText("Lagde du mærke til videoer om køn, mænds rettigheder, feminisme eller forhold mellem mænd og kvinder?")).toBeVisible();
  await expect(page.getByTestId("post-content-type-nej")).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByTestId("post-content-type-en_eller_faa")).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByTestId("post-content-type-flere")).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByTestId("post-content-type-mange")).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByTestId("post-content-type-ved_ikke_husker_ikke")).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByTestId("study-post-submit")).toHaveText("Videre");
  await page.getByTestId("study-post-submit").click();
  await expect(page.getByText("Vælg venligst et svar til alle spørgsmål.")).toBeVisible();
  await fillRequiredPostSurvey(page);
  await page.getByTestId("study-post-submit").click();

  await expect(page).toHaveURL(/\/study\/shorts-experiment\/complete\?pid=TEST_E2E&duration_seconds=2$/);
  await expect(page.getByRole("heading", { name: "Tak for din deltagelse" })).toBeVisible();
  await expect(page.getByText("De holdninger eller synspunkter, som måtte være blevet udtrykt i videoerne, afspejler ikke forskergruppens egne holdninger.")).toBeVisible();
  const completeRedirect = page.getByTestId("norstat-complete-redirect");
  await expect(completeRedirect).toHaveAttribute("href", "https://webs.norstatsurveys.com/z/Complete");
  const buttonBeforeDebrief = await completeRedirect.evaluate((button) => {
    const debriefText = Array.from(document.querySelectorAll("p")).find((paragraph) => paragraph.textContent?.startsWith("Denne undersøgelse handler overordnet"));
    return Boolean(debriefText && (button.compareDocumentPosition(debriefText) & Node.DOCUMENT_POSITION_FOLLOWING));
  });
  expect(buttonBeforeDebrief).toBeTruthy();
});

test("new Norstat pid in same browser does not inherit prior incomplete debrief state", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => {
    window.localStorage.setItem(
      "exp-video-study-shorts-experiment",
      JSON.stringify({
        study_id: "study-stale-oldpid",
        state: "debrief",
        assignment: "control",
        session_id: "study-stale-oldpid",
        norstat_pid: "OLD_PID_INCOMPLETE",
        started_at: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
        completed_at: null,
      }),
    );
    window.localStorage.setItem("exp-video-study-consent", JSON.stringify({ research_use_consent: true }));
    window.localStorage.setItem("exp-video-study-pre", JSON.stringify({ stale: true }));
    window.localStorage.setItem("exp-video-study-post", JSON.stringify({ stale: true }));
  });

  await page.goto("/study/shorts-experiment?pid=NEW_PID_FRESH_BROWSER");
  await expect(page).toHaveURL(/\/study\/shorts-experiment\?pid=NEW_PID_FRESH_BROWSER$/);
  await expect(page.getByRole("heading", { name: "Undersøgelse om Shorts-videoer" })).toBeVisible();
  await expect(page.getByText("Information om undersøgelsen")).toHaveCount(0);

  const localState = await page.evaluate(() => ({
    session: JSON.parse(window.localStorage.getItem("exp-video-study-shorts-experiment") ?? "{}"),
    preSurvey: window.localStorage.getItem("exp-video-study-pre"),
  }));
  expect(localState.session.state).toBe("entry");
  expect(localState.session.norstat_pid).toBe("NEW_PID_FRESH_BROWSER");
  expect(localState.preSurvey).toBeNull();
});

test("study reel timing survives refresh and logs inattentive focus events", async ({ page }) => {
  await page.goto("/study/shorts-experiment?duration_seconds=20");
  await page.getByTestId("study-entry-consent").check();
  await page.getByTestId("study-entry-start").click();
  await fillRequiredPreSurvey(page, "never");
  await expect(page.getByText("Hvilke videoplatforme anvender du typisk?")).toHaveCount(0);
  await page.getByTestId("study-pre-submit").click();
  await expect(page).toHaveURL(/\/study\/shorts-experiment\/instructions\?duration_seconds=20$/);
  await page.getByTestId("study-attention-answer-hund").click();
  await page.getByTestId("study-instructions-start").click();

  await expect(page).toHaveURL(/\/study\/shorts-experiment\/reel\?duration_seconds=20$/);
  await expect(page.getByTestId("study-timer")).toContainText("00:20");
  await page.getByTestId("shorts-first-start").click();
  const sessionId = await page.evaluate(() => {
    const raw = window.localStorage.getItem("exp-video-study-shorts-experiment");
    return raw ? JSON.parse(raw).session_id as string : "";
  });
  const beforeSession = await (await page.request.get(`/api/session?session_id=${encodeURIComponent(sessionId)}`)).json();

  await page.evaluate(() => {
    window.dispatchEvent(new Event("blur"));
    window.dispatchEvent(new Event("focus"));
  });

  await page.waitForTimeout(1700);
  await page.reload();

  const afterSession = await (await page.request.get(`/api/session?session_id=${encodeURIComponent(sessionId)}`)).json();
  expect(afterSession.reel_started_at).toBe(beforeSession.reel_started_at);
  expect(afterSession.reel_expires_at).toBe(beforeSession.reel_expires_at);

  await expect.poll(async () => {
    const logs = await (await page.request.get(`/api/logs?ts=${Date.now()}`)).json();
    const studyAttentionEvents = logs.events.filter((row: { event_type?: string; metadata?: { blurred_duration_ms?: number } | null; surface?: string }) =>
      row.surface === "shorts" && (row.event_type === "window_blur" || row.event_type === "window_focus"),
    );
    return studyAttentionEvents.length >= 2;
  }).toBeTruthy();
});


test("first study video requires one explicit start tap only", async ({ page }) => {
  await page.goto("/study/shorts-experiment/dev-60");
  await expect(page).toHaveURL(/\/study\/shorts-experiment\/reel\?duration_seconds=60$/, { timeout: 8000 });

  const startButton = page.getByTestId("shorts-first-start");
  const reelVideo = page.getByTestId("shorts-reel").locator("video");
  const timer = page.getByTestId("study-timer");
  const sessionId = await page.evaluate(() => JSON.parse(window.localStorage.getItem("exp-video-study-shorts-experiment") ?? "{}").session_id as string);
  await expect(startButton).toHaveText("Tryk her for at starte");
  await expect(timer).toContainText("01:00");
  await page.waitForTimeout(1700);
  await expect(timer).toContainText("01:00");
  const beforeStartLogs = await (await page.request.get(`/api/logs?ts=${Date.now()}`)).json();
  expect(beforeStartLogs.events.filter((row: { session_id?: string; event_type?: string }) =>
    row.session_id === sessionId && ["watch_start", "progress", "complete"].includes(row.event_type ?? ""),
  )).toHaveLength(0);
  const beforeStart = await (await page.request.get(`/api/session?session_id=${encodeURIComponent(sessionId)}`)).json();
  expect(beforeStart.reel_started_at).toBeNull();
  expect(beforeStart.reel_expires_at).toBeNull();
  await reelVideo.evaluate((video) => {
    const testVideo = video as HTMLVideoElement & { __firstStartPlayCalls?: number };
    testVideo.__firstStartPlayCalls = 0;
    testVideo.play = () => {
      testVideo.__firstStartPlayCalls = (testVideo.__firstStartPlayCalls ?? 0) + 1;
      return Promise.resolve();
    };
  });

  await startButton.click();
  await expect(startButton).toHaveCount(0);
  await expect.poll(async () => {
    const activated = await (await page.request.get(`/api/session?session_id=${encodeURIComponent(sessionId)}`)).json();
    return Boolean(activated.reel_started_at && activated.reel_expires_at);
  }).toBeTruthy();
  expect(await reelVideo.evaluate((video) => (video as HTMLVideoElement & { __firstStartPlayCalls?: number }).__firstStartPlayCalls ?? 0)).toBeGreaterThanOrEqual(1);

  await page.getByTestId("shorts-next").click();
  await expect(startButton).toHaveCount(0);
});

test("first reel navigation starts the exposure timer without requiring the start button", async ({ page }) => {
  await page.goto("/study/shorts-experiment/dev-60");
  await expect(page).toHaveURL(/\/study\/shorts-experiment\/reel\?duration_seconds=60$/, { timeout: 8000 });

  const sessionId = await page.evaluate(() => JSON.parse(window.localStorage.getItem("exp-video-study-shorts-experiment") ?? "{}").session_id as string);
  const startButton = page.getByTestId("shorts-first-start");
  await expect(startButton).toBeVisible();

  const reelBox = await page.getByTestId("shorts-reel").boundingBox();
  if (!reelBox) throw new Error("reel bounds unavailable");
  const client = await page.context().newCDPSession(page);
  const x = reelBox.x + reelBox.width / 2;
  await client.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y: reelBox.y + reelBox.height * 0.75 }] });
  await client.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x, y: reelBox.y + reelBox.height * 0.35 }] });
  await client.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });

  await expect(startButton).toHaveCount(0);
  await expect.poll(async () => {
    const activated = await (await page.request.get(`/api/session?session_id=${encodeURIComponent(sessionId)}`)).json();
    return Boolean(activated.reel_started_at && activated.reel_expires_at && activated.study_state === "reel_active");
  }).toBeTruthy();

  const activated = await (await page.request.get(`/api/session?session_id=${encodeURIComponent(sessionId)}`)).json();
  await page.getByTestId("shorts-next").click();
  const afterSecondNavigation = await (await page.request.get(`/api/session?session_id=${encodeURIComponent(sessionId)}`)).json();
  expect(afterSecondNavigation.reel_started_at).toBe(activated.reel_started_at);
  expect(afterSecondNavigation.reel_expires_at).toBe(activated.reel_expires_at);
});

test("study reel contains videos within narrow device width without cropping", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto("/study/shorts-experiment/dev-60");
  await expect(page).toHaveURL(/\/study\/shorts-experiment\/reel\?duration_seconds=60$/, { timeout: 8000 });

  const reelVideo = page.getByTestId("shorts-reel").locator("video");
  await expect(reelVideo).toHaveCount(1);
  expect(await reelVideo.evaluate((video) => getComputedStyle(video).objectFit)).toBe("contain");
  const dimensions = await page.evaluate(() => {
    const video = document.querySelector('[data-testid="shorts-reel"] video');
    const rect = video?.getBoundingClientRect();
    return {
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
      videoLeft: rect?.left ?? -1,
      videoRight: rect?.right ?? Number.POSITIVE_INFINITY,
    };
  });
  expect(dimensions.documentWidth).toBeLessThanOrEqual(dimensions.viewportWidth);
  expect(dimensions.videoLeft).toBeGreaterThanOrEqual(0);
  expect(dimensions.videoRight).toBeLessThanOrEqual(dimensions.viewportWidth);
});

test("localhost dev route resets study state and starts a 60-second reel test flow", async ({ page }) => {
  await page.goto("/study/shorts-experiment/dev-60");
  await expect(page).toHaveURL(/\/study\/shorts-experiment\/reel\?duration_seconds=60$/, { timeout: 8000 });
  await expect(page.getByTestId("shorts-reel")).toBeVisible();
  await expect(page.getByTestId("study-timer")).toContainText("01:00");

  const reelVideo = page.getByTestId("shorts-reel").locator("video");
  await expect(reelVideo).toHaveCount(1);
  await reelVideo.evaluate((video) => {
    const persistentVideo = video as HTMLVideoElement & { __sourceLoadCalls?: number; __sourcePlayCalls?: number };
    persistentVideo.dataset.persistentMarker = "single-player";
    persistentVideo.__sourceLoadCalls = 0;
    persistentVideo.__sourcePlayCalls = 0;
    persistentVideo.load = () => { persistentVideo.__sourceLoadCalls = (persistentVideo.__sourceLoadCalls ?? 0) + 1; };
    persistentVideo.play = () => {
      persistentVideo.__sourcePlayCalls = (persistentVideo.__sourcePlayCalls ?? 0) + 1;
      return Promise.resolve();
    };
  });
  await page.getByTestId("shorts-first-start").click();

  const firstTitle = await page.getByTestId("shorts-card").locator("h2").textContent();
  const sessionId = await page.evaluate(() => JSON.parse(window.localStorage.getItem("exp-video-study-shorts-experiment") ?? "{}").session_id as string);
  await reelVideo.dispatchEvent("playing");
  await page.waitForTimeout(150);
  await reelVideo.dispatchEvent("waiting");
  await page.getByTestId("shorts-next").click();
  await expect.poll(async () => {
    const logs = await (await page.request.get(`/api/logs?ts=${Date.now()}`)).json();
    const click = logs.events.findLast((row: { session_id?: string; video_title?: string; event_type?: string; metadata?: Record<string, unknown>; exposure_id?: string; client_log_id?: string; client_event_at?: string; client_sequence_number?: number }) =>
      row.session_id === sessionId && row.video_title === firstTitle && row.event_type === "click",
    );
    const waiting = logs.events.findLast((row: { session_id?: string; video_title?: string; event_type?: string; exposure_id?: string }) =>
      row.session_id === sessionId && row.video_title === firstTitle && row.event_type === "playback_waiting",
    );
    const impression = logs.impressions.findLast((row: { session_id?: string; video_title?: string; exposure_id?: string }) =>
      row.session_id === sessionId && row.video_title === firstTitle,
    );
    return click?.metadata?.playback_started === true
      && typeof click.metadata.surface_dwell_ms === "number"
      && typeof click.metadata.playback_dwell_ms === "number"
      && click.metadata.surface_dwell_ms >= click.metadata.playback_dwell_ms
      && click.metadata.playback_dwell_ms >= 100
      && typeof click.metadata.actual_playing_ms === "number"
      && click.metadata.actual_playing_ms >= 100
      && typeof click.metadata.startup_delay_ms === "number"
      && Boolean(click.exposure_id && click.client_log_id && click.client_event_at && click.client_sequence_number)
      && waiting?.exposure_id === click.exposure_id
      && impression?.exposure_id === click.exposure_id;
  }).toBeTruthy();

  let failExposureEnd = true;
  await page.route("**/api/events", async (route) => {
    const body = route.request().postDataJSON() as { event_type?: string };
    if (failExposureEnd && body.event_type === "exposure_end") {
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: "temporary" }) });
      return;
    }
    await route.continue();
  });
  await reelVideo.dispatchEvent("playing");
  await page.waitForTimeout(120);
  await page.evaluate(() => window.dispatchEvent(new Event("pagehide")));
  await expect.poll(async () => page.evaluate(() => JSON.parse(window.localStorage.getItem("exp-video-log-outbox-v1") ?? "[]").some((item: { body?: { event_type?: string } }) => item.body?.event_type === "exposure_end"))).toBeTruthy();
  failExposureEnd = false;
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect.poll(async () => {
    const logs = await (await page.request.get(`/api/logs?ts=${Date.now()}`)).json();
    const finalExposure = logs.events.findLast((row: { session_id?: string; event_type?: string; metadata?: Record<string, unknown> }) =>
      row.session_id === sessionId && row.event_type === "exposure_end",
    );
    return finalExposure?.metadata?.reason === "pagehide"
      && typeof finalExposure.metadata.surface_dwell_ms === "number"
      && typeof finalExposure.metadata.actual_playing_ms === "number"
      && finalExposure.metadata.actual_playing_ms >= 100;
  }).toBeTruthy();

  for (let index = 0; index < 11; index += 1) {
    await page.getByTestId("shorts-next").click();
  }
  await expect(reelVideo).toHaveCount(1);
  await expect(reelVideo).toHaveAttribute("data-persistent-marker", "single-player");
  const sourceSwitchCalls = await reelVideo.evaluate((video) => {
    const persistentVideo = video as HTMLVideoElement & { __sourceLoadCalls?: number; __sourcePlayCalls?: number };
    return { load: persistentVideo.__sourceLoadCalls ?? 0, play: persistentVideo.__sourcePlayCalls ?? 0 };
  });
  expect(sourceSwitchCalls.load).toBeGreaterThanOrEqual(12);
  expect(sourceSwitchCalls.play).toBeGreaterThanOrEqual(12);
});


test("failed behavior logs remain queued and retry exactly once", async ({ page }) => {
  let failImpressions = true;
  await page.route("**/api/impressions", async (route) => {
    if (failImpressions) {
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: "temporary" }) });
      return;
    }
    await route.continue();
  });

  await page.goto("/study/shorts-experiment/dev-60");
  await expect(page).toHaveURL(/\/study\/shorts-experiment\/reel\?duration_seconds=60$/, { timeout: 8000 });
  const queued = await expect.poll(async () => page.evaluate(() => JSON.parse(window.localStorage.getItem("exp-video-log-outbox-v1") ?? "[]"))).toHaveLength(1);
  void queued;
  const queuedClientLogId = await page.evaluate(() => JSON.parse(window.localStorage.getItem("exp-video-log-outbox-v1") ?? "[]")[0]?.body?.client_log_id as string);
  expect(queuedClientLogId).toBeTruthy();

  failImpressions = false;
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect.poll(async () => page.evaluate(() => JSON.parse(window.localStorage.getItem("exp-video-log-outbox-v1") ?? "[]").length)).toBe(0);

  const logs = await (await page.request.get(`/api/logs?ts=${Date.now()}`)).json();
  expect(logs.impressions.filter((row: { client_log_id?: string }) => row.client_log_id === queuedClientLogId)).toHaveLength(1);
});

test("localhost full-flow dev route keeps landing, pre, reel, and post in a 60-second test", async ({ page }) => {
  await page.goto("/study/shorts-experiment/dev-flow-60");
  await expect(page).toHaveURL(/\/study\/shorts-experiment\?duration_seconds=60$/, { timeout: 8000 });
  await expect(page.getByRole("heading", { name: "Undersøgelse om Shorts-videoer" })).toBeVisible();
  await page.getByTestId("study-entry-consent").check();
  await page.getByTestId("study-entry-start").click();

  await expect(page).toHaveURL(/\/study\/shorts-experiment\/pre\?duration_seconds=60$/);
  await fillRequiredPreSurvey(page);
  await page.getByTestId("study-pre-submit").click();

  await expect(page).toHaveURL(/\/study\/shorts-experiment\/instructions\?duration_seconds=60$/);
  await expect(page.getByRole("heading", { name: "Sådan bruger du videofeedet" })).toBeVisible();
  await page.getByTestId("study-attention-answer-hund").click();
  await page.locator('video[aria-hidden="true"]').evaluate((video) => {
    const testWindow = window as typeof window & { __unlockPlayCalls?: number; __unlockPauseCalls?: number };
    testWindow.__unlockPlayCalls = 0;
    testWindow.__unlockPauseCalls = 0;
    video.play = () => {
      testWindow.__unlockPlayCalls = (testWindow.__unlockPlayCalls ?? 0) + 1;
      return new Promise((resolve) => window.setTimeout(resolve, 250));
    };
    video.pause = () => { testWindow.__unlockPauseCalls = (testWindow.__unlockPauseCalls ?? 0) + 1; };
  });
  await page.getByTestId("study-instructions-start").click();
  await page.waitForTimeout(100);
  await expect(page).toHaveURL(/\/study\/shorts-experiment\/instructions\?duration_seconds=60$/);

  await expect(page).toHaveURL(/\/study\/shorts-experiment\/reel\?duration_seconds=60$/);
  expect(await page.evaluate(() => {
    const testWindow = window as typeof window & { __unlockPlayCalls?: number; __unlockPauseCalls?: number };
    return { play: testWindow.__unlockPlayCalls ?? 0, pause: testWindow.__unlockPauseCalls ?? 0 };
  })).toEqual({ play: 1, pause: 0 });
  await expect(page.getByTestId("study-timer")).toContainText("01:00");
  await page.getByTestId("shorts-first-start").click();
  await expect(page.getByTestId("study-timer")).toContainText(/00:5|00:4/);

  await page.goto("/study/shorts-experiment/post?duration_seconds=60");
  await expect(page.getByRole("heading", { name: "Afsluttende spørgsmål" })).toBeVisible();
});
