import { isRequestHostAllowedForDev } from "@/lib/dev-host";
import { normalizeCondition } from "@/lib/experiment";
import { activateStudyReel, completeStudyPost, completeStudyReel, createSession, ensureSession, latestStudySession, prepareStudySession, recordStudyParticipationStatus, submitStudyPostSurvey, submitStudyPreSurvey } from "@/lib/server-log-store";

function allowDurationOverride(request: Request) {
  const host = request.headers.get("host") ?? "";
  return isRequestHostAllowedForDev(host);
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const session_id = searchParams.get("session_id");
    const user_id = searchParams.get("user_id") ?? undefined;
    const condition = normalizeCondition(searchParams.get("condition"));
    const reelDuration = searchParams.get("reel_duration_seconds");
    if (searchParams.get("latest_study") === "1") {
      if (!user_id) {
        return Response.json({ error: "user_id is required" }, { status: 400 });
      }
      return Response.json(await latestStudySession(user_id));
    }
    if (!session_id) {
      return Response.json({ error: "session_id is required" }, { status: 400 });
    }
    const duration = allowDurationOverride(request) && reelDuration ? Number(reelDuration) : undefined;
    return Response.json(await ensureSession(session_id, condition, user_id, Number.isFinite(duration) ? duration : undefined));
  } catch (error) {
    const status = (error as Error & { status?: number }).status ?? 500;
    return Response.json({ error: error instanceof Error ? error.message : "session request failed" }, { status });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json().catch(() => ({}));
    const action = typeof body.action === "string" ? body.action : "create";
    const condition = normalizeCondition(body.condition);

    if (action === "study_participation_status") {
      const session_id = typeof body.session_id === "string" ? body.session_id : "";
      const user_id = typeof body.user_id === "string" ? body.user_id : "";
      if (!session_id || !user_id || !["accepted", "declined"].includes(body.consent_status)) {
        return Response.json({ error: "session_id, user_id, and valid consent_status are required" }, { status: 400 });
      }
      return Response.json(await recordStudyParticipationStatus({
        session_id, user_id, condition, consent_status: body.consent_status,
        screened_reason: typeof body.screened_reason === "string" ? body.screened_reason : undefined,
        norstat_pid: typeof body.norstat_pid === "string" ? body.norstat_pid : null,
      }));
    }

    if (action === "study_prepare") {
      const session_id = typeof body.session_id === "string" ? body.session_id : "";
      const user_id = typeof body.user_id === "string" ? body.user_id : "";
      if (!session_id || !user_id) {
        return Response.json({ error: "session_id and user_id are required" }, { status: 400 });
      }
      const requested = Number(body.reel_duration_seconds);
      const reelDuration = allowDurationOverride(request) && Number.isFinite(requested) && requested > 0 ? Math.floor(requested) : 240;
      return Response.json(await prepareStudySession(session_id, condition, user_id, reelDuration));
    }

    if (action === "study_pre_survey") {
      if (typeof body.session_id !== "string" || !body.session_id) {
        return Response.json({ error: "session_id is required" }, { status: 400 });
      }
      return Response.json(await submitStudyPreSurvey({
        session_id: body.session_id,
        user_id: typeof body.user_id === "string" ? body.user_id : "",
        condition,
        age_group: String(body.age_group ?? ""),
        gender: String(body.gender ?? ""),
        video_platform_use: String(body.video_platform_use ?? ""),
        political_orientation: Number(body.political_orientation),
        education_level: String(body.education_level ?? ""),
        typical_video_platforms: Array.isArray(body.typical_video_platforms) ? body.typical_video_platforms.map(String) : [],
        cohabitation_status: String(body.cohabitation_status ?? ""),
        employment_status: String(body.employment_status ?? ""),
        norstat_pid: typeof body.norstat_pid === "string" ? body.norstat_pid : null,
      }));
    }

    if (action === "study_post_survey") {
      if (typeof body.session_id !== "string" || !body.session_id) {
        return Response.json({ error: "session_id is required" }, { status: 400 });
      }
      return Response.json(await submitStudyPostSurvey({
        session_id: body.session_id,
        feminist_attitude: Number(body.feminist_attitude),
        feminism_taken_too_far: Number(body.feminism_taken_too_far),
        traditional_gender_attitude: Number(body.traditional_gender_attitude),
        harder_to_be_a_man_today: Number(body.harder_to_be_a_man_today),
        social_division: Number(body.social_division),
        gender_conflict_exaggeration: Number(body.gender_conflict_exaggeration),
        online_misinformation: Number(body.online_misinformation),
        perceived_content_type: String(body.perceived_content_type ?? ""),
      }));
    }

    if (action === "study_reel_activate") {
      if (typeof body.session_id !== "string" || !body.session_id) {
        return Response.json({ error: "session_id is required" }, { status: 400 });
      }
      return Response.json(await activateStudyReel(body.session_id));
    }

    if (action === "study_reel_complete") {
      if (typeof body.session_id !== "string" || !body.session_id) {
        return Response.json({ error: "session_id is required" }, { status: 400 });
      }
      return Response.json(await completeStudyReel(body.session_id));
    }

    if (action === "study_complete") {
      if (typeof body.session_id !== "string" || !body.session_id) {
        return Response.json({ error: "session_id is required" }, { status: 400 });
      }
      return Response.json(await completeStudyPost(body.session_id));
    }

    return Response.json(await createSession(condition, body.user_id));
  } catch (error) {
    const status = (error as Error & { status?: number }).status ?? 500;
    return Response.json({ error: error instanceof Error ? error.message : "session request failed" }, { status });
  }
}
