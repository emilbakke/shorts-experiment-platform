"""Shared helpers for the ViewTube/manosphere analysis pipeline."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from pandas.errors import EmptyDataError

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DIR = ROOT / "analysis"
OUTPUT_DIR = ANALYSIS_DIR / "outputs"
RAW_DIR = OUTPUT_DIR / "raw"
DERIVED_DIR = OUTPUT_DIR / "derived"
TABLE_DIR = OUTPUT_DIR / "tables"
FIGURE_DIR = OUTPUT_DIR / "figures"
LOG_DIR = OUTPUT_DIR / "logs"

BEHAVIOR_TABLES = ["users", "sessions", "impressions", "events", "search_queries"]
CONTENT_TABLES = ["content_pools", "videos"]
POST_SURVEY_KEYS = [
    "feminist_attitude",
    "feminism_taken_too_far",
    "traditional_gender_attitude",
    "harder_to_be_a_man_today",
    "social_division",
    "gender_conflict_exaggeration",
    "online_misinformation",
    "perceived_content_type",
]
LIKERT_KEYS = [key for key in POST_SURVEY_KEYS if key != "perceived_content_type"]
ANTI_FEMINIST_ITEMS = [
    "feminist_attitude_rev",
    "feminism_taken_too_far",
    "traditional_gender_attitude",
    "harder_to_be_a_man_today",
]
BROADER_ITEMS = ["social_division", "gender_conflict_exaggeration", "online_misinformation"]
TEST_PATTERNS = re.compile(r"(test|pilot|debug|dev|persona|incomplete|completeflow|survey-|sess-)", re.I)


def ensure_output_dirs() -> None:
    for path in [RAW_DIR, DERIVED_DIR, TABLE_DIR, FIGURE_DIR, LOG_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def read_csv_if_exists(path: Path, **kwargs: Any) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, **kwargs)
    except EmptyDataError:
        return pd.DataFrame()


def parse_timestamp_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if col.endswith("_at") or col == "timestamp" or col == "created_at" or col == "started_at":
            out[col] = pd.to_datetime(out[col], errors="coerce", utc=True)
    return out


def safe_json_loads(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    except json.JSONDecodeError:
        return {}


def first_present(row: pd.Series, columns: Iterable[str], default: Any = np.nan) -> Any:
    for col in columns:
        if col in row.index and pd.notna(row[col]) and row[col] != "":
            return row[col]
    return default


def normalize_condition(value: Any) -> str:
    text = str(value or "").strip()
    if text == "treatment_problematic_content" or text == "treatment":
        return "treatment"
    if text == "control_recommendation" or text == "control":
        return "control"
    return text or "unknown"


def treatment_indicator(value: Any) -> float:
    return 1.0 if normalize_condition(value) == "treatment" else 0.0 if normalize_condition(value) == "control" else np.nan


def normalize_gender(value: Any) -> str:
    text = str(value or "").strip().lower()
    mapping = {
        "male": "man",
        "mand": "man",
        "m": "man",
        "female": "woman",
        "kvinde": "woman",
        "f": "woman",
        "unspecified": "unknown",
        "": "unknown",
        "nan": "unknown",
    }
    return mapping.get(text, text)


def is_likely_test_id(value: Any) -> bool:
    text = str(value or "")
    return bool(TEST_PATTERNS.search(text))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
