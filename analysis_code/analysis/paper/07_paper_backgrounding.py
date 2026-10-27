"""Exploratory: did participants put the feed in the background (tab hidden / window blurred),
and did this differ by condition or by clip type?
Inputs: analysis/outputs/raw/events.csv, analysis/outputs/paper/derived/*.csv
Output: analysis/outputs/paper/tables/paper_backgrounding.csv
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "analysis" / "outputs" / "paper"


def main():
    p = pd.read_csv(PAPER / "derived" / "participants_paper.csv", low_memory=False)
    p = p[p["paper_behavioral"].astype(str).str.lower() == "true"][["participant_id", "condition_clean", "gender_clean"]]
    exp = pd.read_csv(PAPER / "derived" / "exposures_time_before_swipe.csv")
    e = pd.read_csv(ROOT / "analysis" / "outputs" / "raw" / "events.csv", low_memory=False)
    e = e[e["user_id"].isin(p["participant_id"])].copy()
    meta = e["metadata_json"].map(lambda m: json.loads(m) if isinstance(m, str) else {})
    e["hidden_ms"] = meta.map(lambda d: d.get("hidden_duration_ms"))
    e["blurred_ms"] = meta.map(lambda d: d.get("blurred_duration_ms"))

    per = p.set_index("participant_id").copy()
    per["hidden_events"] = e[e["event_type"] == "visibility_hidden"].groupby("user_id").size()
    per["blur_events"] = e[e["event_type"] == "window_blur"].groupby("user_id").size()
    per["hidden_seconds"] = e.groupby("user_id")["hidden_ms"].sum() / 1000
    per["left_page"] = e[(e["event_type"] == "exposure_end") & meta.map(lambda d: d.get("reason") == "pagehide")].groupby("user_id").size()
    per = per.fillna(0)
    per["any_hidden"] = per["hidden_events"] > 0
    per["any_background"] = (per["hidden_events"] + per["blur_events"]) > 0
    rows = []
    c, t = per[per["condition_clean"] == "control"], per[per["condition_clean"] == "treatment"]
    for label, col in [("Tab or app hidden at least once", "any_hidden"), ("Hidden or window lost focus at least once", "any_background")]:
        tab = [[int(c[col].sum()), int((~c[col]).sum())], [int(t[col].sum()), int((~t[col]).sum())]]
        rows.append({"measure": label, "control": c[col].mean(), "treatment": t[col].mean(), "n_control": tab[0][0], "n_treatment": tab[1][0],
                     "p_value": stats.fisher_exact(tab)[1], "test": "Fisher exact"})
    for label, col in [("Hidden events per participant (mean)", "hidden_events"), ("Seconds hidden per participant (mean)", "hidden_seconds")]:
        rows.append({"measure": label, "control": c[col].mean(), "treatment": t[col].mean(), "n_control": len(c), "n_treatment": len(t),
                     "p_value": stats.mannwhitneyu(c[col], t[col]).pvalue, "test": "Mann-Whitney"})

    # Which clip was on screen when the feed was hidden? (events carry the exposure id)
    hid = e[e["event_type"] == "visibility_hidden"].drop(columns=["rank"]).merge(exp[["exposure_id", "manosphere_video", "rank", "condition_clean"]], on="exposure_id", how="left")
    served = exp.copy()
    served["slot4"] = served["rank"] % 4 == 0
    hid["slot4"] = hid["rank"] % 4 == 0
    for arm in ["treatment", "control"]:
        for slot, name in [(True, "every fourth slot (manosphere in treatment)"), (False, "other slots")]:
            n_served = int(((served["condition_clean"] == arm) & (served["slot4"] == slot)).sum())
            n_hid = int(((hid["condition_clean"] == arm) & (hid["slot4"] == slot)).sum())
            rows.append({"measure": f"Hidden events per 1,000 served videos, {arm}, {name}", "control": np.nan, "treatment": np.nan,
                         "n_control": n_hid, "n_treatment": n_served, "p_value": np.nan, "test": f"rate = {1000 * n_hid / n_served:.2f}"})
    tt = hid[hid["condition_clean"] == "treatment"]
    sv = served[served["condition_clean"] == "treatment"]
    tab = [[int((tt["slot4"]).sum()), int(sv["slot4"].sum())], [int((~tt["slot4"].astype(bool)).sum()), int((~sv["slot4"]).sum())]]
    rows.append({"measure": "Treatment: hidden while manosphere vs other clip on screen", "control": np.nan, "treatment": np.nan, "n_control": tab[0][0],
                 "n_treatment": tab[1][0], "p_value": stats.fisher_exact([[tab[0][0], tab[0][1] - tab[0][0]], [tab[1][0], tab[1][1] - tab[1][0]]])[1], "test": "Fisher exact"})
    out = pd.DataFrame(rows)
    out.to_csv(PAPER / "tables" / "paper_backgrounding.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 80)
    print(out.round(4).to_string(index=False))
    print("events without a matched served video:", int(hid["rank"].isna().sum()), "of", len(hid))
    print("left the page during the feed (pagehide):", per.groupby("condition_clean")["left_page"].apply(lambda s: int((s > 0).sum())).to_dict())
    print("hidden seconds among those who hid, median:", per[per.any_hidden].groupby("condition_clean")["hidden_seconds"].median().round(1).to_dict())


if __name__ == "__main__":
    main()
