#!/usr/bin/env python3
from __future__ import annotations

import json
import random
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DB = REPO_ROOT / "backend" / "app.db"
OUTPUT_DIR = REPO_ROOT / "analysis" / "ministudy"
OUTPUT_DB = OUTPUT_DIR / "ministudy.sqlite"
SEED = 20260430
STUDY_DURATION_SECONDS = 480
N_PARTICIPANTS = 10


@dataclass(frozen=True)
class VideoRow:
    id: str
    title: str
    channel: str
    content_pool: str
    duration_seconds: int


def iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def reset_output_db() -> sqlite3.Connection:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_DB, OUTPUT_DB)
    con = sqlite3.connect(OUTPUT_DB)
    cur = con.cursor()
    for table in ("events", "impressions", "search_queries", "sessions", "users"):
        cur.execute(f"DELETE FROM {table}")
    con.commit()
    return con


def fetch_short_inventory(con: sqlite3.Connection) -> tuple[list[VideoRow], list[VideoRow]]:
    rows = con.execute(
        """
        SELECT id, title, channel, content_pool, duration_seconds
        FROM videos
        WHERE is_short = 1 AND embeddable = 1
        ORDER BY views DESC, id
        """
    ).fetchall()
    safe = [VideoRow(*row) for row in rows if row[3] == "safe"]
    problematic = [VideoRow(*row) for row in rows if row[3] == "problematic"]
    return safe, problematic


def generate_feed(
    rng: random.Random,
    safe_inventory: list[VideoRow],
    problematic_inventory: list[VideoRow],
    *,
    condition: str,
    length: int = 20,
) -> list[VideoRow]:
    if condition == "control_recommendation":
        return rng.sample(safe_inventory, length)

    problematic_slots = {3, 9, 15}
    safe_sample = rng.sample(safe_inventory, length - len(problematic_slots))
    problematic_sample = rng.sample(problematic_inventory, len(problematic_slots))
    feed: list[VideoRow] = []
    safe_idx = 0
    problematic_idx = 0
    for idx in range(length):
        if idx in problematic_slots:
            feed.append(problematic_sample[problematic_idx])
            problematic_idx += 1
        else:
            feed.append(safe_sample[safe_idx])
            safe_idx += 1
    return feed


def scaled_durations(
    rng: random.Random,
    feed: list[VideoRow],
    *,
    condition: str,
    gender: str,
    total_seconds: int = STUDY_DURATION_SECONDS,
) -> list[float]:
    draws: list[float] = []
    for idx, video in enumerate(feed):
        if condition == "control_recommendation":
            base = rng.uniform(16, 28)
        elif video.content_pool == "problematic":
            if gender == "man":
                base = rng.uniform(24, 38)
            elif gender == "woman":
                base = rng.uniform(20, 32)
            else:
                base = rng.uniform(22, 34)
        else:
            base = rng.uniform(14, 24)
        if idx == len(feed) - 1:
            base *= 0.9
        draws.append(base)

    scale = total_seconds / sum(draws)
    scaled = [round(value * scale, 3) for value in draws]
    scaled[-1] = round(total_seconds - sum(scaled[:-1]), 3)
    return scaled


def participant_rows(index: int) -> dict[str, str | int]:
    genders = ["woman", "man", "woman", "man", "prefer_not_to_say"] * 2
    ages = [22, 24, 27, 31, 36, 23, 26, 29, 34, 41]
    households = [
        "living_alone",
        "living_with_partner_or_roommate",
        "living_with_parents",
        "living_alone",
        "living_with_partner_or_roommate",
        "living_alone",
        "living_with_parents",
        "living_with_partner_or_roommate",
        "living_alone",
        "living_with_partner_or_roommate",
    ]
    educations = [
        "gymnasium",
        "kort_videregaende",
        "lang_videregaende",
        "erhvervsuddannelse",
        "mellem_videregaende",
        "gymnasium",
        "lang_videregaende",
        "kort_videregaende",
        "mellem_videregaende",
        "lang_videregaende",
    ]
    regions = [
        "hovedstaden",
        "sjælland",
        "syddanmark",
        "midtjylland",
        "nordjylland",
        "hovedstaden",
        "sjælland",
        "syddanmark",
        "midtjylland",
        "nordjylland",
    ]
    return {
        "gender": genders[index],
        "age": ages[index],
        "household_living_arrangement": households[index],
        "education": educations[index],
        "region_dk": regions[index],
        "left_right_orientation": [3, 4, 5, 6, 7, 2, 5, 6, 4, 7][index],
    }


def insert_simulated_participant(
    con: sqlite3.Connection,
    rng: random.Random,
    *,
    participant_index: int,
    safe_inventory: list[VideoRow],
    problematic_inventory: list[VideoRow],
) -> None:
    participant_no = participant_index + 1
    condition = "control_recommendation" if participant_no <= 5 else "treatment_problematic_content"
    session_id = f"simstudy-session-{participant_no:02d}"
    user_id = f"simstudy-user-{participant_no:02d}"
    study_meta = participant_rows(participant_index)
    start_time = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc) + timedelta(minutes=12 * participant_index)
    expires_at = start_time + timedelta(seconds=STUDY_DURATION_SECONDS)
    feed = generate_feed(rng, safe_inventory, problematic_inventory, condition=condition, length=20)
    durations = scaled_durations(rng, feed, condition=condition, gender=str(study_meta["gender"]))

    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO users (id, username, created_at)
        VALUES (?, ?, ?)
        """,
        (user_id, user_id, iso(start_time - timedelta(minutes=1))),
    )
    cur.execute(
        """
        INSERT INTO sessions (
          id, user_id, condition, created_at, started_at, survey_completed, gender, age,
          household_living_arrangement, education, region_dk, left_right_orientation,
          study_state, reel_duration_seconds, reel_started_at, reel_expires_at,
          reel_completed_at, post_survey_completed_at
        )
        VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, 'complete', ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            user_id,
            condition,
            iso(start_time - timedelta(minutes=2)),
            iso(start_time - timedelta(minutes=2)),
            study_meta["gender"],
            study_meta["age"],
            study_meta["household_living_arrangement"],
            study_meta["education"],
            study_meta["region_dk"],
            study_meta["left_right_orientation"],
            STUDY_DURATION_SECONDS,
            iso(start_time),
            iso(expires_at),
            iso(expires_at),
            iso(expires_at + timedelta(minutes=1)),
        ),
    )

    elapsed = 0.0
    attention_inserted = False
    for rank, (video, watch_seconds) in enumerate(zip(feed, durations), start=1):
        impression_time = start_time + timedelta(seconds=elapsed)
        impression_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO impressions (
              id, user_id, session_id, condition, video_id, video_title, surface,
              click_from, content_pool, rank, timestamp, gender
            )
            VALUES (?, ?, ?, ?, ?, ?, 'shorts', 'shorts', ?, ?, ?, ?)
            """,
            (
                impression_id,
                user_id,
                session_id,
                condition,
                video.id,
                video.title,
                video.content_pool,
                rank,
                iso(impression_time),
                study_meta["gender"],
            ),
        )

        events: list[tuple[str, datetime, dict[str, object] | None]] = [
            ("watch_start", impression_time + timedelta(milliseconds=250), {"source": "simulated"}),
            (
                "progress",
                impression_time + timedelta(seconds=max(1.0, min(watch_seconds * 0.25, 6.0))),
                {"percent": 25, "source": "simulated"},
            ),
        ]

        if rng.random() < 0.18:
            events.append(("click", impression_time + timedelta(seconds=min(2.0, watch_seconds / 3)), {"action": "like_toggle"}))
        if rng.random() < 0.08:
            events.append(("click", impression_time + timedelta(seconds=min(4.0, watch_seconds / 2)), {"action": "share_toggle"}))

        if not attention_inserted and participant_no in {2, 4, 7, 9} and rank in {5, 6, 7}:
            hidden_duration_ms = int(rng.uniform(4000, 9000))
            blur_duration_ms = int(rng.uniform(1500, 5000))
            hidden_at = impression_time + timedelta(seconds=min(5.0, watch_seconds / 2))
            events.extend(
                [
                    ("visibility_hidden", hidden_at, {"hidden": True}),
                    ("visibility_visible", hidden_at + timedelta(milliseconds=hidden_duration_ms), {"hidden_duration_ms": hidden_duration_ms}),
                    ("window_blur", hidden_at + timedelta(milliseconds=300), {"blurred": True}),
                    ("window_focus", hidden_at + timedelta(milliseconds=300 + blur_duration_ms), {"blurred_duration_ms": blur_duration_ms}),
                ]
            )
            attention_inserted = True

        if watch_seconds >= min(max(video.duration_seconds * 0.9, 6), 30):
            events.append(("complete", impression_time + timedelta(seconds=max(1.0, watch_seconds - 0.5)), {"source": "simulated"}))

        for event_type, event_time, metadata in sorted(events, key=lambda item: item[1]):
            cur.execute(
                """
                INSERT INTO events (
                  id, user_id, session_id, condition, video_id, video_title, event_type,
                  surface, click_from, content_pool, rank, metadata_json, timestamp, gender
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'shorts', 'shorts', ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    user_id,
                    session_id,
                    condition,
                    video.id,
                    video.title,
                    event_type,
                    video.content_pool,
                    rank,
                    json.dumps(metadata or {}),
                    iso(event_time),
                    study_meta["gender"],
                ),
            )
        elapsed += watch_seconds

    con.commit()


def export_tables(con: sqlite3.Connection) -> None:
    for table in ("sessions", "impressions", "events"):
        df = pd.read_sql_query(f"SELECT * FROM {table} ORDER BY id", con)
        df.to_csv(OUTPUT_DIR / f"{table}.csv", index=False)


DERIVED_SQL = """
WITH ordered_impressions AS (
  SELECT
    i.session_id,
    i.video_id,
    i.video_title,
    i.condition,
    i.content_pool,
    i.rank,
    i.timestamp AS impression_ts,
    s.reel_expires_at,
    LEAD(i.timestamp) OVER (
      PARTITION BY i.session_id
      ORDER BY i.timestamp
    ) AS next_impression_ts
  FROM impressions i
  JOIN sessions s ON i.session_id = s.id
  WHERE i.surface = 'shorts'
)
SELECT
  session_id,
  video_id,
  video_title,
  condition,
  content_pool,
  rank,
  impression_ts,
  next_impression_ts,
  CASE
    WHEN next_impression_ts IS NOT NULL THEN
      (julianday(next_impression_ts) - julianday(impression_ts)) * 86400.0
    WHEN reel_expires_at IS NOT NULL THEN
      (julianday(reel_expires_at) - julianday(impression_ts)) * 86400.0
    ELSE NULL
  END AS viewing_time_seconds
FROM ordered_impressions
ORDER BY session_id, impression_ts
"""


def export_derived(con: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(DERIVED_SQL, con)
    df.to_csv(OUTPUT_DIR / "derived_viewing_times.csv", index=False)
    return df


def save_plots(df: pd.DataFrame) -> None:
    clean = df.dropna(subset=["viewing_time_seconds"]).copy()
    clean = clean[clean["viewing_time_seconds"] >= 0]
    sns.set_theme(style="whitegrid")

    by_condition = clean.groupby("condition", as_index=False)["viewing_time_seconds"].mean()
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.barplot(
        data=by_condition,
        x="condition",
        y="viewing_time_seconds",
        hue="condition",
        legend=False,
        ax=ax,
        palette="deep",
    )
    ax.set_title("Mean viewing time in control vs. treatment")
    ax.set_xlabel("Condition")
    ax.set_ylabel("Mean viewing time (seconds)")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "mean_viewing_time_control_vs_treatment.png", dpi=180)
    plt.close(fig)

    treatment_only = clean[clean["condition"] == "treatment_problematic_content"].copy()
    treatment_only["content_type"] = treatment_only["content_pool"].map(
        {"problematic": "Manosphere/problematic", "safe": "Non-manosphere/safe"}
    )
    by_pool = treatment_only.groupby("content_type", as_index=False)["viewing_time_seconds"].mean()
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.barplot(
        data=by_pool,
        x="content_type",
        y="viewing_time_seconds",
        hue="content_type",
        legend=False,
        ax=ax,
        palette="muted",
    )
    ax.set_title("Mean watchtime: manosphere vs. non-manosphere content")
    ax.set_xlabel("Content type (treatment sessions only)")
    ax.set_ylabel("Mean viewing time (seconds)")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "mean_watchtime_manosphere_vs_nonmanosphere.png", dpi=180)
    plt.close(fig)


def write_helper_files(df: pd.DataFrame) -> None:
    (OUTPUT_DIR / "extract_viewing_times.sql").write_text(DERIVED_SQL.strip() + "\n", encoding="utf-8")

    readme = f"""# Mini-study simulation output

This folder contains a reproducible simulated 10-participant Shorts study.

## Files
- `ministudy.sqlite`: isolated SQLite database with simulated study data
- `sessions.csv`, `impressions.csv`, `events.csv`: raw exports
- `derived_viewing_times.csv`: impression-level derived watchtime data
- `mean_viewing_time_control_vs_treatment.png`
- `mean_watchtime_manosphere_vs_nonmanosphere.png`
- `extract_viewing_times.sql`: SQL used to derive watchtime

## How to inspect the database
```bash
sqlite3 analysis/ministudy/ministudy.sqlite
.tables
SELECT id, condition, study_state, reel_started_at, reel_expires_at FROM sessions;
SELECT session_id, video_title, condition, content_pool, rank, timestamp FROM impressions LIMIT 20;
SELECT session_id, event_type, metadata_json, timestamp FROM events WHERE event_type IN ('visibility_hidden','visibility_visible','window_blur','window_focus');
```

## How to export data yourself
```bash
sqlite3 -header -csv analysis/ministudy/ministudy.sqlite "SELECT * FROM sessions;" > my_sessions.csv
sqlite3 -header -csv analysis/ministudy/ministudy.sqlite "$(cat analysis/ministudy/extract_viewing_times.sql)" > my_viewing_times.csv
```

## Study design in this simulation
- 10 participants total
- 5 control sessions
- 5 treatment sessions
- 20 Shorts impressions per participant
- treatment sessions contain approximately 1 in 6 problematic/manosphere-coded videos
- some sessions contain simulated blur/focus and visibility hidden/visible events

## Quick summary
Rows in derived viewing-time dataset: {len(df)}
"""
    (OUTPUT_DIR / "README.md").write_text(readme, encoding="utf-8")


def main() -> None:
    rng = random.Random(SEED)
    con = reset_output_db()
    try:
        safe_inventory, problematic_inventory = fetch_short_inventory(con)
        if len(safe_inventory) < 20 or len(problematic_inventory) < 3:
            raise RuntimeError("Not enough Shorts inventory to simulate the mini-study.")

        for participant_index in range(N_PARTICIPANTS):
            insert_simulated_participant(
                con,
                rng,
                participant_index=participant_index,
                safe_inventory=safe_inventory,
                problematic_inventory=problematic_inventory,
            )

        export_tables(con)
        derived = export_derived(con)
        save_plots(derived)
        write_helper_files(derived)
    finally:
        con.close()

    print(f"Mini-study simulation complete: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
