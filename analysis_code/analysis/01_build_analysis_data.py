#!/usr/bin/env python3
"""Build participant- and impression-level analysis datasets from raw exports."""
from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from common import (
    ANTI_FEMINIST_ITEMS,
    BROADER_ITEMS,
    DERIVED_DIR,
    LIKERT_KEYS,
    LOG_DIR,
    POST_SURVEY_KEYS,
    RAW_DIR,
    ensure_output_dirs,
    is_likely_test_id,
    normalize_condition,
    normalize_gender,
    parse_timestamp_columns,
    read_csv_if_exists,
    safe_json_loads,
    treatment_indicator,
    write_text,
)


def load_raw() -> dict[str, pd.DataFrame]:
    return {
        name: parse_timestamp_columns(read_csv_if_exists(RAW_DIR / f"{name}.csv"))
        for name in ["users", "sessions", "impressions", "events", "search_queries", "videos", "content_pools"]
    }


def extract_metadata_survey(events: pd.DataFrame) -> pd.DataFrame:
    """Extract post-survey item metadata if the app logs survey answers as event metadata.

    The current app version may only store post-survey answers in browser localStorage.
    If no metadata with POST_SURVEY_KEYS is present, this returns an empty frame and the audit warns loudly.
    """
    if events.empty or "metadata_json" not in events.columns:
        return pd.DataFrame(columns=["session_id", *POST_SURVEY_KEYS])
    rows: list[dict[str, Any]] = []
    for _, row in events.iterrows():
        metadata = safe_json_loads(row.get("metadata_json"))
        if not any(key in metadata for key in POST_SURVEY_KEYS):
            continue
        out = {"session_id": row.get("session_id"), "event_id": row.get("id"), "event_type": row.get("event_type"), "timestamp": row.get("timestamp")}
        for key in POST_SURVEY_KEYS:
            out[key] = metadata.get(key)
        rows.append(out)
    if not rows:
        return pd.DataFrame(columns=["session_id", *POST_SURVEY_KEYS])
    survey = pd.DataFrame(rows).sort_values(["session_id", "timestamp"])
    return survey.groupby("session_id", as_index=False).tail(1).reset_index(drop=True)




def extract_actual_playback_ms(metadata: Any) -> float:
    data = safe_json_loads(metadata)
    value = data.get("actual_playing_ms")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def first_nonempty(series: pd.Series) -> Any:
    nonempty = series.dropna()
    nonempty = nonempty[nonempty.astype(str).str.strip() != ""]
    return nonempty.iloc[0] if not nonempty.empty else np.nan


def build_actual_playback_exposures(raw: dict[str, pd.DataFrame], participant: pd.DataFrame) -> pd.DataFrame:
    events = raw["events"].copy()
    if events.empty or participant.empty or not {"session_id", "exposure_id", "event_type"}.issubset(events.columns):
        return pd.DataFrame()

    pcols = [c for c in ["id", "participant_id", "condition_clean", "gender_clean", "analysis_behavioral", "likely_test"] if c in participant.columns]
    sessions = participant[pcols].rename(columns={"id": "session_id"})
    events = events.merge(sessions, on="session_id", how="inner", suffixes=("", "_session"))
    events = events.loc[events["exposure_id"].notna() & (events["exposure_id"].astype(str).str.strip() != "")].copy()
    if events.empty:
        return pd.DataFrame()

    if "content_pool" not in events.columns:
        events["content_pool"] = ""
    events["manosphere_video"] = events["content_pool"].astype(str).str.contains("manosphere|problematic", case=False, regex=True, na=False).astype(int)
    if "gender_clean" not in events.columns:
        events["gender_clean"] = events.get("gender", pd.Series(index=events.index, dtype="object")).map(normalize_gender)
    else:
        event_gender = events.get("gender", pd.Series(index=events.index, dtype="object")).map(normalize_gender)
        events["gender_clean"] = np.where(events["gender_clean"].isin(["unknown", "nan", ""]), event_gender, events["gender_clean"])

    if "metadata_json" in events.columns:
        events["actual_playing_ms"] = events["metadata_json"].map(extract_actual_playback_ms)
    else:
        events["actual_playing_ms"] = np.nan

    if "video_id" not in events.columns:
        events["video_id"] = np.nan
    if "video_title" not in events.columns:
        events["video_title"] = np.nan
    if "timestamp" not in events.columns:
        events["timestamp"] = pd.NaT

    group_cols = ["session_id", "participant_id", "exposure_id"]
    rows = []
    for keys, group in events.groupby(group_cols, dropna=False):
        actual_ms = pd.to_numeric(group["actual_playing_ms"], errors="coerce")
        row = {
            "session_id": keys[0],
            "participant_id": keys[1],
            "exposure_id": keys[2],
            "condition_clean": first_nonempty(group.get("condition_clean", pd.Series(dtype="object"))),
            "gender_clean": first_nonempty(group.get("gender_clean", pd.Series(dtype="object"))),
            "video_id": first_nonempty(group["video_id"]),
            "video_title": first_nonempty(group["video_title"]),
            "content_pool": first_nonempty(group["content_pool"]),
            "manosphere_video": int(group["manosphere_video"].max()),
            "timestamp": group["timestamp"].min(),
            "actual_playing_ms": actual_ms.max(skipna=True),
            "completed_video": int(group["event_type"].astype(str).eq("complete").any()),
            "watch_started": int(group["event_type"].astype(str).eq("watch_start").any()),
            "event_rows": len(group),
            "analysis_behavioral": bool(group.get("analysis_behavioral", pd.Series([True])).fillna(False).astype(bool).any()),
            "likely_test": bool(group.get("likely_test", pd.Series([False])).fillna(False).astype(bool).any()),
        }
        rows.append(row)
    exposures = pd.DataFrame(rows)
    exposures["actual_playing_seconds"] = pd.to_numeric(exposures["actual_playing_ms"], errors="coerce") / 1000
    exposures = exposures.loc[exposures["actual_playing_seconds"].notna() & (exposures["actual_playing_seconds"] >= 0)].copy()
    exposures = exposures.sort_values(["participant_id", "timestamp", "exposure_id"]).reset_index(drop=True)
    exposures["exposure_index"] = exposures.groupby("participant_id").cumcount() + 1
    exposures["actual_playing_seconds_cap60"] = exposures["actual_playing_seconds"].clip(upper=60)
    exposures["actual_playing_seconds_cap30"] = exposures["actual_playing_seconds"].clip(upper=30)
    exposures["actual_playing_seconds_cap20"] = exposures["actual_playing_seconds"].clip(upper=20)
    exposures["actual_playing_seconds_cap15"] = exposures["actual_playing_seconds"].clip(upper=15)
    exposures["actual_playing_log"] = np.log1p(exposures["actual_playing_seconds"])
    exposures["actual_playing_log_30"] = np.log1p(exposures["actual_playing_seconds_cap30"])
    exposures["analysis_behavioral"] = exposures["analysis_behavioral"] & ~exposures["likely_test"]
    return exposures


def build_participant(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    sessions = raw["sessions"].copy()
    impressions = raw["impressions"].copy()
    events = raw["events"].copy()
    if sessions.empty:
        return pd.DataFrame()

    sessions["condition_clean"] = sessions.get("condition", pd.Series(index=sessions.index, dtype="object")).map(normalize_condition)
    sessions["treatment"] = sessions["condition_clean"].map(treatment_indicator)
    sessions["participant_id"] = sessions.get("user_id", sessions.get("id"))
    sessions["gender_clean"] = sessions.get("gender", pd.Series(index=sessions.index, dtype="object")).map(normalize_gender)

    education_scale = {
        "folkeskole": 1,
        "gymnasium": 2,
        "erhvervsuddannelse": 2,
        "kort_videregaende": 3,
        "mellem_videregaende": 4,
        "lang_videregaende": 5,
        "phd": 6,
    }
    platform_use_scale = {
        "never": 0,
        "rarely": 1,
        "monthly": 2,
        "weekly": 3,
        "daily": 4,
    }
    sessions["education_scale"] = sessions.get("education_level", pd.Series(index=sessions.index, dtype="object")).astype(str).str.strip().map(education_scale)
    sessions["video_platform_use_scale"] = sessions.get("video_platform_use", pd.Series(index=sessions.index, dtype="object")).astype(str).str.strip().map(platform_use_scale)

    # Recover gender from impression/event logs if sessions.gender was not populated.
    gender_sources = []
    for df in [impressions, events]:
        if not df.empty and {"session_id", "gender"}.issubset(df.columns):
            tmp = df.loc[df["gender"].notna() & (df["gender"].astype(str) != "unspecified"), ["session_id", "gender"]].copy()
            if not tmp.empty:
                gender_sources.append(tmp)
    if gender_sources:
        genders = pd.concat(gender_sources, ignore_index=True)
        genders["gender_from_logs"] = genders["gender"].map(normalize_gender)
        genders = genders.groupby("session_id", as_index=False)["gender_from_logs"].agg(lambda x: x.mode().iloc[0] if not x.mode().empty else x.iloc[0])
        sessions = sessions.merge(genders, left_on="id", right_on="session_id", how="left", suffixes=("", "_gsrc"))
        sessions["gender_clean"] = np.where(sessions["gender_clean"].isin(["unknown", "nan", ""]), sessions["gender_from_logs"], sessions["gender_clean"])
        sessions = sessions.drop(columns=[c for c in ["session_id_gsrc", "gender_from_logs"] if c in sessions.columns])

    survey = extract_metadata_survey(events)
    if not survey.empty:
        sessions = sessions.merge(survey.drop(columns=[c for c in ["event_id", "event_type", "timestamp"] if c in survey.columns]), left_on="id", right_on="session_id", how="left", suffixes=("", "_survey"))
        if "session_id_survey" in sessions.columns:
            sessions = sessions.drop(columns=["session_id_survey"])
    else:
        for key in POST_SURVEY_KEYS:
            if key not in sessions.columns:
                sessions[key] = np.nan

    for key in LIKERT_KEYS:
        sessions[key] = pd.to_numeric(sessions[key], errors="coerce")
    sessions["feminist_attitude_rev"] = 8 - sessions["feminist_attitude"]
    sessions["anti_feminist_index"] = sessions[ANTI_FEMINIST_ITEMS].mean(axis=1, skipna=False)
    sessions["broader_perception_index"] = sessions[BROADER_ITEMS].mean(axis=1, skipna=False)

    sessions["is_complete"] = sessions.get("study_state", "").astype(str).eq("complete") | sessions.get("post_survey_completed_at", pd.Series(index=sessions.index)).notna()
    sessions["has_reel_started"] = sessions.get("reel_started_at", pd.Series(index=sessions.index)).notna()
    sessions["has_reel_completed"] = sessions.get("reel_completed_at", pd.Series(index=sessions.index)).notna()
    sessions["has_post_survey_items"] = sessions[LIKERT_KEYS].notna().all(axis=1)
    sessions["likely_test"] = sessions["participant_id"].map(is_likely_test_id) | sessions["id"].map(is_likely_test_id)
    consent = sessions.get("consent_status", pd.Series(index=sessions.index, dtype="object")).astype(str).str.strip().eq("accepted")
    not_screened = sessions.get("screened_reason", pd.Series(index=sessions.index, dtype="object")).isna() | sessions.get("screened_reason", pd.Series(index=sessions.index, dtype="object")).astype(str).str.strip().eq("")
    sessions["eligible_completed"] = sessions["is_complete"] & consent & not_screened
    sessions["analysis_binary_gender"] = sessions["gender_clean"].isin(["man", "woman"])
    sessions["analysis_post_survey"] = sessions["eligible_completed"] & sessions["has_post_survey_items"] & sessions["analysis_binary_gender"] & ~sessions["likely_test"]
    sessions["analysis_behavioral"] = sessions["eligible_completed"] & sessions["has_reel_started"] & sessions["analysis_binary_gender"] & ~sessions["likely_test"]

    keep_first = [
        "participant_id", "id", "condition", "condition_clean", "treatment", "gender_clean", "study_state",
        "created_at", "started_at", "reel_started_at", "reel_expires_at", "reel_completed_at", "post_survey_completed_at",
        "is_complete", "has_reel_started", "has_reel_completed", "has_post_survey_items", "likely_test",
        "eligible_completed", "analysis_binary_gender", "analysis_post_survey", "analysis_behavioral",
    ]
    return sessions[[c for c in keep_first if c in sessions.columns] + [c for c in sessions.columns if c not in keep_first]]


def video_manosphere_map(videos: pd.DataFrame) -> pd.DataFrame:
    if videos.empty:
        return pd.DataFrame(columns=["video_id", "video_title_content", "creator_slug", "content_pool_video", "manosphere_video"])
    out = videos.copy()
    out["video_id"] = out.get("id")
    content_text = out[[c for c in ["content_pool", "review_group", "topic", "creator_slug", "title"] if c in out.columns]].astype(str).agg(" ".join, axis=1).str.lower()
    out["manosphere_video"] = content_text.str.contains("manosphere|problematic", regex=True, na=False).astype(int)
    return out.rename(columns={"title": "video_title_content", "content_pool": "content_pool_video"})[[c for c in ["video_id", "video_title_content", "channel", "creator_slug", "review_group", "content_pool_video", "manosphere_video"] if c in out.columns or c in ["video_id", "manosphere_video"]]]


def build_impressions(raw: dict[str, pd.DataFrame], participant: pd.DataFrame) -> pd.DataFrame:
    impressions = raw["impressions"].copy()
    events = raw["events"].copy()
    if impressions.empty:
        return pd.DataFrame()

    impressions = impressions.sort_values(["session_id", "timestamp", "rank", "video_id"]).reset_index(drop=True)
    impressions["impression_index"] = impressions.groupby("session_id").cumcount() + 1
    impressions["condition_clean"] = impressions.get("condition", pd.Series(index=impressions.index, dtype="object")).map(normalize_condition)
    impressions["treatment"] = impressions["condition_clean"].map(treatment_indicator)
    impressions["gender_clean"] = impressions.get("gender", pd.Series(index=impressions.index, dtype="object")).map(normalize_gender)
    impressions["manosphere_video"] = impressions.get("content_pool", pd.Series(index=impressions.index, dtype="object")).astype(str).str.contains("manosphere|problematic", case=False, regex=True, na=False).astype(int)

    videos_map = video_manosphere_map(raw["videos"])
    if not videos_map.empty:
        impressions = impressions.merge(videos_map, on="video_id", how="left", suffixes=("", "_video"))
        if "manosphere_video_video" in impressions.columns:
            impressions["manosphere_video"] = np.where(
                impressions["manosphere_video"].eq(1) | impressions["manosphere_video_video"].fillna(0).astype(int).eq(1),
                1,
                0,
            )
            impressions = impressions.drop(columns=["manosphere_video_video"])

    if not participant.empty:
        pcols = [c for c in ["id", "participant_id", "gender_clean", "analysis_behavioral", "likely_test", "reel_expires_at", "post_survey_completed_at"] if c in participant.columns]
        impressions = impressions.merge(participant[pcols], left_on="session_id", right_on="id", how="left", suffixes=("", "_session"))
        impressions["gender_clean"] = np.where(impressions["gender_clean"].isin(["unknown", "nan", ""]), impressions.get("gender_clean_session"), impressions["gender_clean"])

    # End of exposure = next impression in same session by default; if absent, use next click event or session end.
    impressions["next_impression_timestamp"] = impressions.groupby("session_id")["timestamp"].shift(-1)
    click_events = pd.DataFrame()
    if not events.empty and {"session_id", "timestamp", "event_type"}.issubset(events.columns):
        ev = events.loc[events["event_type"].astype(str).eq("click")].copy()
        if not ev.empty:
            click_events = ev[["session_id", "timestamp"]].rename(columns={"timestamp": "click_timestamp"})
    end_times = []
    for _, row in impressions.iterrows():
        candidates = []
        for col in ["next_impression_timestamp", "reel_expires_at", "post_survey_completed_at"]:
            val = row.get(col)
            if pd.notna(val):
                candidates.append(val)
        if not click_events.empty:
            clicks = click_events.loc[(click_events["session_id"] == row.get("session_id")) & (click_events["click_timestamp"] > row.get("timestamp")), "click_timestamp"]
            if not clicks.empty:
                candidates.append(clicks.min())
        end_times.append(min(candidates) if candidates else pd.NaT)
    impressions["impression_end_timestamp"] = end_times
    impressions["watch_time_seconds_raw"] = (impressions["impression_end_timestamp"] - impressions["timestamp"]).dt.total_seconds()
    impressions["watch_time_seconds_clean"] = impressions["watch_time_seconds_raw"]
    impressions.loc[impressions["watch_time_seconds_clean"] < 0, "watch_time_seconds_clean"] = np.nan
    impressions.loc[impressions["watch_time_seconds_clean"] > 300, "watch_time_seconds_clean"] = np.nan
    impressions["watch_time_log"] = np.log1p(impressions["watch_time_seconds_clean"])
    impressions["analysis_behavioral"] = impressions.get("analysis_behavioral", True).fillna(True) & impressions["watch_time_seconds_clean"].notna()
    return impressions


def write_audit(raw: dict[str, pd.DataFrame], participant: pd.DataFrame, impressions: pd.DataFrame, actual_playback: pd.DataFrame) -> None:
    lines: list[str] = []
    lines.append("DATA BUILD AUDIT")
    for name, df in raw.items():
        if not df.empty:
            lines.append(f"raw.{name}: rows={len(df)} cols={len(df.columns)}")
    if participant.empty:
        lines.append("participant: EMPTY")
    else:
        lines.append(f"participant rows={len(participant)}")
        lines.append(f"post-survey item rows={int(participant['has_post_survey_items'].sum()) if 'has_post_survey_items' in participant else 0}")
        lines.append(f"eligible_completed rows={int(participant['eligible_completed'].sum()) if 'eligible_completed' in participant else 0}")
        lines.append(f"binary-gender eligible rows={int((participant['eligible_completed'] & participant['analysis_binary_gender']).sum()) if {'eligible_completed', 'analysis_binary_gender'}.issubset(participant.columns) else 0}")
        lines.append(f"analysis_post_survey rows={int(participant['analysis_post_survey'].sum()) if 'analysis_post_survey' in participant else 0}")
        lines.append("condition counts:\n" + participant.get("condition_clean", pd.Series(dtype='object')).value_counts(dropna=False).to_string())
        lines.append("study_state counts:\n" + participant.get("study_state", pd.Series(dtype='object')).value_counts(dropna=False).to_string())
        if int(participant.get("has_post_survey_items", pd.Series(dtype=bool)).sum()) == 0:
            lines.append("WARNING: No post-survey item responses were found in PostgreSQL exports/events metadata. H3/H4 models will be skipped until survey answers are persisted to the behavior DB.")
    if impressions.empty:
        lines.append("impressions_derived: EMPTY")
    else:
        lines.append(f"impressions_derived rows={len(impressions)} valid_watch_rows={int(impressions['analysis_behavioral'].sum())}")
    if actual_playback.empty:
        lines.append("actual_playback_exposures: EMPTY")
    else:
        lines.append(f"actual_playback_exposures rows={len(actual_playback)} valid_actual_playback_rows={int(actual_playback['analysis_behavioral'].sum())}")
    write_text(LOG_DIR / "data_build_audit.txt", "\n".join(lines) + "\n")
    print("\n".join(lines))


def main() -> None:
    ensure_output_dirs()
    raw = load_raw()
    participant = build_participant(raw)
    impressions = build_impressions(raw, participant)
    actual_playback = build_actual_playback_exposures(raw, participant)
    participant.to_csv(DERIVED_DIR / "participants.csv", index=False)
    impressions.to_csv(DERIVED_DIR / "impressions_analysis.csv", index=False)
    actual_playback.to_csv(DERIVED_DIR / "actual_playback_exposures.csv", index=False)
    write_audit(raw, participant, impressions, actual_playback)


if __name__ == "__main__":
    main()
