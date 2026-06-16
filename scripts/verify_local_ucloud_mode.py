#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
for candidate in (REPO_ROOT / ".python_deps", REPO_ROOT / f".python_deps_{sys.version_info.major}{sys.version_info.minor}"):
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.main import app  # noqa: E402


CONTENT_TABLES = {"content_pools", "videos"}
BEHAVIOR_TABLES = {"users", "sessions", "impressions", "events", "search_queries"}


def sqlite_path_from_env(name: str) -> Path:
    raw = os.environ.get(name)
    if not raw or not raw.startswith("sqlite:///"):
        raise RuntimeError(f"{name} must be a sqlite:/// path, got {raw!r}")
    return Path(raw.removeprefix("sqlite:///"))


def table_names(db_path: Path) -> set[str]:
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        con.close()


def scalar(db_path: Path, query: str, params: tuple[object, ...] = ()) -> int:
    con = sqlite3.connect(db_path)
    try:
        return int(con.execute(query, params).fetchone()[0])
    finally:
        con.close()


def main() -> int:
    content_db = sqlite_path_from_env("CONTENT_DATABASE_URL")
    behavior_db = sqlite_path_from_env("BEHAVIOR_DATABASE_URL")

    content_tables = table_names(content_db)
    behavior_tables = table_names(behavior_db)
    if content_tables != CONTENT_TABLES:
        raise RuntimeError(f"Content DB tables mismatch: expected {sorted(CONTENT_TABLES)}, got {sorted(content_tables)}")
    if behavior_tables != BEHAVIOR_TABLES:
        raise RuntimeError(f"Behavior DB tables mismatch: expected {sorted(BEHAVIOR_TABLES)}, got {sorted(behavior_tables)}")

    with TestClient(app) as client:
        session_response = client.post("/sessions", json={"condition": "treatment_problematic_content"})
        if session_response.status_code != 200:
            raise RuntimeError(f"Session creation failed: {session_response.status_code} {session_response.text}")
        session_id = session_response.json()["session_id"]
        user_id = f"verify-user-{uuid4()}"
        survey_response = client.post(
            f"/sessions/{session_id}/survey",
            json={
                "user_id": user_id,
                "condition": "treatment_problematic_content",
                "gender": "woman",
                "age": 28,
                "household_living_arrangement": "living_alone",
                "education": "lang_videregaende",
                "region_dk": "hovedstaden",
                "left_right_orientation": 4,
            },
        )
        if survey_response.status_code != 200:
            raise RuntimeError(f"Survey storage failed: {survey_response.status_code} {survey_response.text}")

        video = client.get("/shorts", params={"condition": "treatment_problematic_content"}).json()[0]
        payload = {
            "user_id": user_id,
            "session_id": session_id,
            "condition": "treatment_problematic_content",
            "gender": "woman",
            "video_id": video["id"],
            "video_title": video["title"],
            "surface": "shorts",
            "click_from": "shorts",
            "content_pool": video["content_pool"],
            "rank": video["rank"],
        }
        impression_response = client.post("/impressions", json=payload)
        event_response = client.post("/events", json={**payload, "event_type": "watch_start"})
        if impression_response.status_code != 200:
            raise RuntimeError(f"Impression logging failed: {impression_response.status_code} {impression_response.text}")
        if event_response.status_code != 200:
            raise RuntimeError(f"Event logging failed: {event_response.status_code} {event_response.text}")

    if scalar(behavior_db, "SELECT COUNT(*) FROM sessions WHERE id = ?", (session_id,)) != 1:
        raise RuntimeError("Expected exactly one matching session row in behavior DB")
    if scalar(behavior_db, "SELECT COUNT(*) FROM impressions WHERE session_id = ?", (session_id,)) != 1:
        raise RuntimeError("Expected exactly one matching impression row in behavior DB")
    if scalar(behavior_db, "SELECT COUNT(*) FROM events WHERE session_id = ?", (session_id,)) != 1:
        raise RuntimeError("Expected exactly one matching event row in behavior DB")

    print("Local UCloud-like split DB verification passed.")
    print(f"Content DB: {content_db}")
    print(f"Behavior DB: {behavior_db}")
    print(f"Verified session_id: {session_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
