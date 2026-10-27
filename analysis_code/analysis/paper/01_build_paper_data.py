"""Build watch-time data: time before swipe per served video.

The raw impressions table logs about three impression rows per served video
(same exposure_id and rank, fired during one viewing episode). Each row's dwell
is therefore only a fragment of the time before swipe. The primary DV1 (watch
time before swipe per served video) is computed from device (client) timestamps;
the server-timed version (row dwell summed within exposure_id) is kept as a
robustness check. The script also writes descriptive checks reported in the paper.

Inputs: analysis/outputs/derived/{participants,impressions_analysis,actual_playback_exposures}.csv
Outputs: analysis/outputs/paper/ (git-ignored; contains participant-level rows)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DERIVED_DIR, OUTPUT_DIR, RAW_DIR  # noqa: E402

PAPER_DIR = OUTPUT_DIR / "paper"
PAPER_DERIVED = PAPER_DIR / "derived"
PAPER_TABLES = PAPER_DIR / "tables"

AGE_BAND = {"18-20": "18-29", "21-24": "18-29", "25-29": "18-29", "30-34": "30-34",
            "35-44": "35-44", "45-54": "45-54", "55-64": "55-64"}
AGE_ORDER = ["18-29", "30-34", "35-44", "45-54", "55-64"]
MEASURES = {"client": "client_dwell_seconds", "server": "dwell_seconds"}  # client is primary
OUTCOMES = ["feminist_attitude_rev", "feminism_taken_too_far", "traditional_gender_attitude",
            "harder_to_be_a_man_today", "social_division", "gender_conflict_exaggeration", "online_misinformation"]


def is_true(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(["true", "1"])


def paper_participants(participants: pd.DataFrame) -> pd.DataFrame:
    """Analysis samples for the paper.

    The preregistration excludes sessions without valid consent. Seventeen participants first
    clicked "decline" and then accepted consent seconds later and completed the study; the earlier
    descriptive pipeline excluded them because the decline flag was never cleared. Here a
    decline counts only if consent was not accepted afterwards.
    """
    p = participants.copy()
    screened_at = pd.to_datetime(p["screened_at"], utc=True, format="mixed", errors="coerce")
    consented_at = pd.to_datetime(p["consented_at"], utc=True, format="mixed", errors="coerce")
    consent = p["consent_status"].astype(str).str.strip().eq("accepted")
    reason = p["screened_reason"].fillna("").astype(str).str.strip()
    decline_overridden = reason.eq("declined_participation") & consent & (consented_at > screened_at)
    not_screened = reason.eq("") | decline_overridden
    eligible_any_gender = is_true(p["is_complete"]) & consent & not_screened & ~is_true(p["likely_test"])
    eligible = eligible_any_gender & p["gender_clean"].isin(["man", "woman"])
    p["decline_overridden"] = decline_overridden
    p["paper_post"] = eligible & is_true(p["has_post_survey_items"])
    # H4 does not involve gender and the registered exclusion rules do not mention gender,
    # so the H4 sample keeps post-survey completers of any gender.
    p["paper_post_all"] = eligible_any_gender & is_true(p["has_post_survey_items"])
    p["paper_behavioral"] = eligible & is_true(p["has_reel_started"])
    return p


BEHAVIORAL_IDS: set = set()  # filled in main() from paper_participants()


def behavioral(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["participant_id"].isin(BEHAVIORAL_IDS) & ~is_true(df["likely_test"])
              & df["gender_clean"].isin(["man", "woman"])].copy()


def build_exposures(impressions: pd.DataFrame, playback: pd.DataFrame) -> pd.DataFrame:
    imp = behavioral(impressions)
    imp = imp[imp["watch_time_seconds_clean"].notna()]
    rows_per_exposure = imp.groupby("exposure_id").size()
    exp = (imp.sort_values("impression_index")
           .groupby("exposure_id")
           .agg(participant_id=("participant_id", "first"), condition_clean=("condition_clean", "first"),
                gender_clean=("gender_clean", "first"), video_id=("video_id", "first"),
                manosphere_video=("manosphere_video", "first"), rank=("rank", "first"),
                first_impression_index=("impression_index", "min"),
                dwell_seconds=("watch_time_seconds_clean", lambda v: v.sum(min_count=1)))
           .reset_index())
    exp["impression_rows"] = exp["exposure_id"].map(rows_per_exposure)
    exp["exposure_index"] = exp.groupby("participant_id")["first_impression_index"].rank(method="first")
    pb = behavioral(playback)[["exposure_id", "actual_playing_seconds"]]
    exp = exp.merge(pb, on="exposure_id", how="left")
    exp = exp.merge(client_time_before_swipe(), on="exposure_id", how="left")
    return exp.dropna(subset=["dwell_seconds"])


def client_time_before_swipe() -> pd.DataFrame:
    """Time before swipe from device (client) timestamps.

    Server timestamps record when a log batch reached the server, which can lag the
    device event by seconds. Here each served video starts at its first client-side
    impression timestamp and ends when the next served video starts. The last video
    in a session has no successor: it was ended by the exposure timer, not a swipe,
    so it gets no time before swipe.
    """
    raw = pd.read_csv(RAW_DIR / "impressions.csv", usecols=["session_id", "exposure_id", "client_event_at"], low_memory=False)
    raw["client_ts"] = pd.to_datetime(raw["client_event_at"], utc=True, format="mixed", errors="coerce")
    starts = (raw.dropna(subset=["client_ts", "exposure_id"])
              .groupby(["session_id", "exposure_id"])["client_ts"].min()
              .reset_index()
              .sort_values(["session_id", "client_ts"]))
    starts["next_start"] = starts.groupby("session_id")["client_ts"].shift(-1)
    starts["client_dwell_seconds"] = (starts["next_start"] - starts["client_ts"]).dt.total_seconds()
    # Same validity rule as the server-timed measure: drop negative and > 300 s values.
    starts.loc[(starts["client_dwell_seconds"] < 0) | (starts["client_dwell_seconds"] > 300), "client_dwell_seconds"] = np.nan
    return starts[["exposure_id", "client_dwell_seconds"]]


def write_sample_and_manipulation_tables(participants: pd.DataFrame, exp: pd.DataFrame, impressions: pd.DataFrame) -> None:
    real = participants[~is_true(participants["likely_test"])]
    stages = [
        ("Assigned a condition", pd.Series(True, index=real.index)),
        ("Accepted consent", real["consent_status"].astype(str).eq("accepted")),
        ("Started the feed", is_true(real["has_reel_started"])),
        ("Completed the feed", is_true(real["has_reel_completed"])),
        ("Completed the post-survey", is_true(real["has_post_survey_items"])),
        ("Analysis sample (binary gender, valid consent)", real["paper_post"]),
    ]
    flow = [{"stage": name, **{c: int(mask[real["condition_clean"] == c].sum()) for c in ["control", "treatment"]}}
            for name, mask in stages]
    flow.append({"stage": "Decline overridden by later consent (included)",
                 **{c: int((real["decline_overridden"] & real["paper_post"])[real["condition_clean"] == c].sum()) for c in ["control", "treatment"]}})
    pd.DataFrame(flow).to_csv(PAPER_TABLES / "paper_sample_flow.csv", index=False)

    post = participants[participants["paper_post"]]
    cells = post.groupby(["condition_clean", "gender_clean"]).size().rename("n").reset_index()
    cells.to_csv(PAPER_TABLES / "paper_analysis_cells.csv", index=False)

    # Manipulation check: "noticed" = one/few, several, or many; "don't know" and "no" count as not noticed.
    noticed = post["perceived_content_type"].isin(["en_eller_faa", "flere", "mange"])
    manip = post.assign(noticed=noticed).groupby("condition_clean")["noticed"].agg(["sum", "size", "mean"]).reset_index()
    manip.to_csv(PAPER_TABLES / "paper_manipulation_check.csv", index=False)
    dist = (post.groupby("condition_clean")["perceived_content_type"].value_counts(normalize=True)
            .rename("share").reset_index())
    dist.to_csv(PAPER_TABLES / "paper_perceived_distribution.csv", index=False)

    # Served = any logged impression at the insertion's feed position (independent of dwell validity).
    imp = impressions[impressions["participant_id"].isin(post.loc[post["condition_clean"] == "treatment", "participant_id"])
                      & ~is_true(impressions["likely_test"])]
    n_treat = imp["participant_id"].nunique()
    reach = pd.DataFrame([{"insertion": k, "rank": 4 * k,
                           "participants_served": int(imp.loc[imp["rank"] == 4 * k, "participant_id"].nunique()),
                           "participants_beyond": int(imp.loc[imp["rank"] >= 4 * k, "participant_id"].nunique()),
                           "treated_with_logs": n_treat} for k in range(1, 21)])
    reach["pct_served"] = 100 * reach["participants_served"] / reach["treated_with_logs"]
    # Positions passed without a logged impression indicate logging gaps.
    reach["pct_passed_without_impression"] = 100 * (reach["participants_beyond"] - reach["participants_served"]) / reach["treated_with_logs"]
    reach.to_csv(PAPER_TABLES / "paper_slot_reach.csv", index=False)
    videos = exp[exp["participant_id"].isin(post["participant_id"])].groupby("participant_id").size()
    pd.DataFrame([{"statistic": "served videos per participant", "median": videos.median(),
                   "q25": videos.quantile(0.25), "q75": videos.quantile(0.75)}]).to_csv(PAPER_TABLES / "paper_videos_served.csv", index=False)


def participant_gaps(exp: pd.DataFrame, value: str, participants: pd.DataFrame) -> pd.DataFrame:
    means = exp.groupby(["participant_id", "manosphere_video"])[value].mean().unstack().dropna()
    means.columns = ["non_manosphere", "manosphere"]
    means["gap"] = means["manosphere"] - means["non_manosphere"]
    return means.reset_index().merge(participants[["participant_id", "age_band", "gender_clean"]], on="participant_id", how="left")


def main() -> None:
    for path in [PAPER_DERIVED, PAPER_TABLES]:
        path.mkdir(parents=True, exist_ok=True)
    participants = paper_participants(pd.read_csv(DERIVED_DIR / "participants.csv", low_memory=False))
    participants["age_band"] = participants["age_group"].map(AGE_BAND)
    BEHAVIORAL_IDS.update(participants.loc[participants["paper_behavioral"], "participant_id"])
    participants.to_csv(PAPER_DERIVED / "participants_paper.csv", index=False)
    impressions = pd.read_csv(DERIVED_DIR / "impressions_analysis.csv", low_memory=False)
    playback = pd.read_csv(DERIVED_DIR / "actual_playback_exposures.csv", low_memory=False)

    exp = build_exposures(impressions, playback)
    exp = exp.merge(participants[["participant_id", "age_group", "age_band", "education_scale", "political_orientation",
                                  "video_platform_use_scale", "cohabitation_status"]], on="participant_id", how="left")
    exp.to_csv(PAPER_DERIVED / "exposures_time_before_swipe.csv", index=False)

    # Logging diagnostics and exposure counts.
    diag = pd.DataFrame([
        {"metric": "impression rows per served video, median", "value": exp["impression_rows"].median()},
        {"metric": "impression rows per served video, mean", "value": exp["impression_rows"].mean()},
        {"metric": "served videos per participant, median", "value": exp.groupby("participant_id").size().median()},
        {"metric": "impression rows per participant, median", "value": exp.groupby("participant_id")["impression_rows"].sum().median()},
        {"metric": "Spearman time before swipe vs actual playback",
         "value": exp[["dwell_seconds", "actual_playing_seconds"]].corr("spearman").iloc[0, 1]},
        {"metric": "share of served videos with time before swipe > 30 s", "value": (exp["dwell_seconds"] > 30).mean()},
        {"metric": "Spearman client vs server time before swipe",
         "value": exp[["client_dwell_seconds", "dwell_seconds"]].corr("spearman").iloc[0, 1]},
        {"metric": "median |client - server| time before swipe (s)",
         "value": (exp["client_dwell_seconds"] - exp["dwell_seconds"]).abs().median()},
        {"metric": "share of served videos without client time before swipe (timer-ended or invalid)",
         "value": exp["client_dwell_seconds"].isna().mean()},
    ])
    diag.to_csv(PAPER_TABLES / "paper_logging_diagnostics.csv", index=False)

    # How the two watch-time measures differ: non-playing time (loading, buffering, pauses, background)
    # = time before swipe (device) minus playback time, by clip type, treatment arm.
    both = exp[(exp["condition_clean"] == "treatment")].dropna(subset=["client_dwell_seconds", "actual_playing_seconds"]).copy()
    both["non_playing_seconds"] = both["client_dwell_seconds"] - both["actual_playing_seconds"]
    comp = both.groupby("manosphere_video").agg(
        served_videos=("non_playing_seconds", "size"),
        median_time_before_swipe=("client_dwell_seconds", "median"), median_playback=("actual_playing_seconds", "median"),
        median_non_playing=("non_playing_seconds", "median"), mean_non_playing=("non_playing_seconds", "mean"),
        share_never_played=("actual_playing_seconds", lambda v: (v == 0).mean())).reset_index()
    comp.to_csv(PAPER_TABLES / "paper_measure_components.csv", index=False)

    treat = exp[exp["condition_clean"] == "treatment"].copy()
    rows = []
    for measure, col in MEASURES.items():
        for cap_label, cap in [("uncapped", None), ("cap60", 60), ("cap30", 30), ("cap15", 15)]:
            sub_treat = treat.dropna(subset=[col]).copy()
            sub_treat["y"] = sub_treat[col] if cap is None else sub_treat[col].clip(upper=cap)
            med = sub_treat.groupby(["gender_clean", "manosphere_video"])["y"].median()
            clip_medians = sub_treat[sub_treat["manosphere_video"] == 1].groupby("video_id")["y"].median()
            rows += [{"measure": measure, "cap": cap_label, "statistic": f"median seconds, {g}, {'manosphere' if m else 'non-manosphere'}", "value": v}
                     for (g, m), v in med.items()]
            rows += [{"measure": measure, "cap": cap_label, "statistic": "manosphere clip median, min", "value": clip_medians.min()},
                     {"measure": measure, "cap": cap_label, "statistic": "manosphere clip median, max", "value": clip_medians.max()},
                     {"measure": measure, "cap": cap_label, "statistic": "manosphere clips", "value": len(clip_medians)}]
            gaps = participant_gaps(sub_treat, "y", participants)
            for age in AGE_ORDER:
                sub = gaps.loc[gaps["age_band"] == age, "gap"]
                rows.append({"measure": measure, "cap": cap_label, "statistic": f"participant gap mean, age {age} (n={len(sub)})",
                             "value": sub.mean(), "p_unadjusted": stats.ttest_1samp(sub, 0).pvalue})
    pd.DataFrame(rows).to_csv(PAPER_TABLES / "paper_descriptives_by_cap.csv", index=False)

    # Exploratory dose-response: total manosphere time before swipe (per 10 s) vs post-survey items, treatment arm.
    post = participants[participants["paper_post"] & (participants["condition_clean"] == "treatment")]
    dose_rows = []
    for measure, col in MEASURES.items():
        for cap_label, cap in [("uncapped", None), ("cap60", 60), ("cap30", 30), ("cap15", 15)]:
            y = treat[col] if cap is None else treat[col].clip(upper=cap)
            total = y[treat["manosphere_video"] == 1].groupby(treat["participant_id"]).sum().rename("total")
            data = post.merge(total, on="participant_id", how="left")
            data["total_10s"] = data["total"].fillna(0) / 10
            for outcome in OUTCOMES:
                sub = data[["total_10s", outcome]].dropna()
                fit = stats.linregress(sub["total_10s"], sub[outcome])
                dose_rows.append({"measure": measure, "cap": cap_label, "outcome": outcome, "estimate_per_10s": fit.slope,
                                  "p": fit.pvalue, "n": len(sub)})
    pd.DataFrame(dose_rows).to_csv(PAPER_TABLES / "paper_exploratory_dose_response.csv", index=False)
    write_sample_and_manipulation_tables(participants, exp, impressions)
    print(f"Data written to {PAPER_DIR}")


if __name__ == "__main__":
    main()
