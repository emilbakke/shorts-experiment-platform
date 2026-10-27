"""Exploratory: who watched manosphere clips relatively longer?

Participant-level gap = mean watch time on manosphere clips minus on other clips, treatment arm,
capped at 30 s. Two measures are reported side by side:
time before swipe (device timestamps; the paper's primary watch-time measure) and logged media
playback time.
Writes (1) subgroup means with 95% CIs and tests against zero (exploratory profile figure),
and (2) unadjusted and adjusted OLS models of the gap, with joint Wald tests per variable
(adjusted for the pre-survey covariates, plus time of day and categorical political groups).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import OUTPUT_DIR  # noqa: E402

PAPER = OUTPUT_DIR / "paper"
GROUPS = {
    "age_band": ["18-29", "30-34", "35-44", "45-54", "55-64"],
    "time_of_day": ["Daytime (06-17)", "Evening/night (18-05)"],
    "living": ["Living alone", "Cohabiting", "Living with parents"],
    "political": ["Left (0-4)", "Centre (5-6)", "Right (7-10)"],
}


def main() -> None:
    p = pd.read_csv(PAPER / "derived" / "participants_paper.csv", low_memory=False)
    p = p[p["paper_post"].astype(str).str.lower().isin(["true", "1"]) & (p["condition_clean"] == "treatment")].copy()
    hour = pd.to_datetime(p["reel_started_at"], utc=True, format="mixed", errors="coerce").dt.tz_convert("Europe/Copenhagen").dt.hour
    p["time_of_day"] = np.where((hour >= 6) & (hour < 18), "Daytime (06-17)", "Evening/night (18-05)")
    p.loc[hour.isna(), "time_of_day"] = np.nan
    p["living"] = p["cohabitation_status"].map({"alene": "Living alone", "samlevere": "Cohabiting", "foraeldre": "Living with parents"})
    p["political"] = pd.cut(p["political_orientation"], bins=[-0.1, 4, 6, 10], labels=GROUPS["political"]).astype(object)

    e = pd.read_csv(PAPER / "derived" / "exposures_time_before_swipe.csv", low_memory=False)
    e = e[(e["condition_clean"] == "treatment") & e["participant_id"].isin(p["participant_id"])]
    pb = pd.read_csv(OUTPUT_DIR / "derived" / "actual_playback_exposures.csv", low_memory=False)
    pb = pb[(pb["condition_clean"] == "treatment") & pb["participant_id"].isin(p["participant_id"])
            & ~pb["likely_test"].astype(str).str.lower().isin(["true", "1"])]
    sources = {"Time before swipe": e.dropna(subset=["client_dwell_seconds"]).assign(y=lambda d: d["client_dwell_seconds"].clip(upper=30)),
               "Playback time": pb.dropna(subset=["actual_playing_seconds"]).assign(y=lambda d: d["actual_playing_seconds"].clip(upper=30))}
    terms = {"age_band": "C(age_band, Treatment('18-29'))", "time_of_day": "C(time_of_day)",
             "living": "C(living, Treatment('Living alone'))", "political": "C(political, Treatment('Left (0-4)'))"}
    controls = "C(gender_clean) + C(employment_status) + education_scale + video_platform_use_scale"
    rows, tests, all_gaps = [], [], []
    for measure, src in sources.items():
        m = src.groupby(["participant_id", "manosphere_video"])["y"].mean().unstack().dropna()
        m.columns = ["other", "manosphere"]
        m["gap"] = m["manosphere"] - m["other"]
        g = m.reset_index().merge(p, on="participant_id", how="left").assign(measure=measure)
        all_gaps.append(g)
        for var, levels in GROUPS.items():
            for lev in levels:
                s_ = g.loc[g[var] == lev, "gap"].dropna()
                mean, se = s_.mean(), s_.std(ddof=1) / np.sqrt(len(s_))
                tcrit = stats.t.ppf(0.975, len(s_) - 1)
                rows.append({"measure": measure, "variable": var, "group": lev, "n": len(s_), "mean_gap": mean,
                             "ci_low": mean - tcrit * se, "ci_high": mean + tcrit * se, "p_vs_zero": stats.ttest_1samp(s_, 0).pvalue})
        d = g.dropna(subset=["gap", "age_band", "time_of_day", "living", "political", "gender_clean", "employment_status",
                             "education_scale", "video_platform_use_scale"])
        adjusted = smf.ols("gap ~ " + " + ".join(terms.values()) + " + " + controls, data=d).fit()
        for var, term in terms.items():
            unadj = smf.ols(f"gap ~ {term}", data=d).fit()
            joint = lambda mod: float(mod.f_test(", ".join(f"{n} = 0" for n in mod.params.index if n.startswith(term))).pvalue)
            tests.append({"measure": measure, "test": var, "n": int(adjusted.nobs), "p_unadjusted": joint(unadj), "p_adjusted": joint(adjusted)})
        d = d.assign(age35=d["age_band"].isin(["35-44", "45-54", "55-64"]).astype(int))
        un = smf.ols("gap ~ age35", data=d).fit()
        ad = smf.ols("gap ~ age35 + C(time_of_day) + C(living) + C(political) + " + controls, data=d).fit()
        tests.append({"measure": measure, "test": "age 35+ vs younger", "n": int(ad.nobs), "estimate_unadjusted": un.params["age35"],
                      "p_unadjusted": un.pvalues["age35"], "estimate_adjusted": ad.params["age35"], "p_adjusted": ad.pvalues["age35"]})
    pd.concat(all_gaps).to_csv(PAPER / "derived" / "participant_gaps_paper.csv", index=False)
    pd.DataFrame(rows).to_csv(PAPER / "tables" / "paper_profile_gaps.csv", index=False)
    pd.DataFrame(tests).to_csv(PAPER / "tables" / "paper_profile_gap_tests.csv", index=False)
    print("profile gaps written")


if __name__ == "__main__":
    main()
