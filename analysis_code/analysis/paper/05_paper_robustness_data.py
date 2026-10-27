"""Robustness inputs: navigation mode, repeat views, and stimulus durations.
Inputs: analysis/outputs/raw/events.csv, analysis/outputs/paper/derived/*.csv, study_media/sequence_manifest.csv
Outputs: analysis/outputs/paper/derived/exposures_robustness.csv and tables paper_navigation.csv, paper_stimulus_durations.csv
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "analysis" / "outputs" / "paper"
TABLES = PAPER / "tables"


def is_true(s):
    return s.astype(str).str.strip().str.lower().isin(["true", "1"])


def main():
    exp = pd.read_csv(PAPER / "derived" / "exposures_time_before_swipe.csv")
    p = pd.read_csv(PAPER / "derived" / "participants_paper.csv", low_memory=False)
    events = pd.read_csv(ROOT / "analysis" / "outputs" / "raw" / "events.csv", low_memory=False)

    # Navigation actions per participant (analysis sample, sessions with a started feed).
    ids = set(p.loc[is_true(p["paper_behavioral"]), "participant_id"])
    clicks = events[(events["event_type"] == "click") & events["user_id"].isin(ids)].copy()
    clicks["action"] = clicks["metadata_json"].map(lambda m: json.loads(m).get("action"))
    nav = clicks[clicks["action"].isin(["touch_swipe_up", "touch_swipe_down", "next_button"]) | clicks["action"].astype(str).str.contains("key|prev|wheel")]
    per = nav.pivot_table(index="user_id", columns="action", values="id", aggfunc="count", fill_value=0)
    per = per.reindex(sorted(ids)).fillna(0)
    non_touch = [c for c in per.columns if not c.startswith("touch_")]
    per["touch_only"] = per[non_touch].sum(axis=1).eq(0) & per[[c for c in per.columns if c.startswith("touch_")]].sum(axis=1).gt(0)
    rows = [{"metric": f"navigation actions: {a}", "value": int(n)} for a, n in nav["action"].value_counts().items()]
    rows += [{"metric": "participants with a started feed", "value": len(per)},
             {"metric": "participants navigating by touch swipes only", "value": int(per["touch_only"].sum())},
             {"metric": "participants who used the next button at least once", "value": int(per.get("next_button", pd.Series(0, index=per.index)).gt(0).sum())},
             {"metric": "participants who swiped backward at least once", "value": int(per.get("touch_swipe_down", pd.Series(0, index=per.index)).gt(0).sum())},
             {"metric": "participants who liked at least one video", "value": int(clicks.loc[clicks["action"] == "like_toggle", "user_id"].nunique())},
             {"metric": "participants who shared at least one video", "value": int(clicks.loc[clicks["action"] == "share_toggle", "user_id"].nunique())}]

    # Repeat views: the same video served again to the same participant after a backward swipe.
    exp = exp.sort_values(["participant_id", "exposure_index"])
    exp["repeat_view"] = exp.duplicated(["participant_id", "video_id"], keep="first")
    exp["touch_only"] = exp["participant_id"].map(per["touch_only"]).fillna(False)
    rows += [{"metric": "served videos (all exposures)", "value": len(exp)},
             {"metric": "share of exposures that are repeat views", "value": exp["repeat_view"].mean()},
             {"metric": "participants with at least one repeat view", "value": int(exp.groupby("participant_id")["repeat_view"].any().sum())}]
    pd.DataFrame(rows).to_csv(TABLES / "paper_navigation.csv", index=False)
    exp.to_csv(PAPER / "derived" / "exposures_robustness.csv", index=False)

    # Stimulus durations: manosphere clips vs the ordinary videos they replaced vs other ordinary videos.
    manifest = ROOT / "study_media" / "sequence_manifest.csv"
    if not manifest.exists():
        print(pd.DataFrame(rows).to_string(index=False))
        print(f"{manifest} not found: skipping the stimulus-duration comparison.")
        return
    man = pd.read_csv(manifest)
    t, c = man[man["arm"] == "treatment"], man[man["arm"] == "control"]
    slots = set(t.loc[t["is_manosphere"].astype(str).str.lower() == "true", "order"])
    groups = {"Manosphere clips (treatment feed)": t[t["order"].isin(slots)], "Replaced ordinary videos (control feed)": c[c["order"].isin(slots)],
              "Other ordinary videos (both feeds)": c[~c["order"].isin(slots)]}
    pd.DataFrame([{"group": g, "n": len(d), "median_duration_s": d["duration_sec"].median(), "mean_duration_s": d["duration_sec"].mean(),
                   "min_duration_s": d["duration_sec"].min(), "max_duration_s": d["duration_sec"].max()} for g, d in groups.items()]
                 ).to_csv(TABLES / "paper_stimulus_durations.csv", index=False)

    print(pd.DataFrame(rows).to_string(index=False))
    print(pd.read_csv(TABLES / "paper_stimulus_durations.csv").to_string(index=False))


if __name__ == "__main__":
    main()
