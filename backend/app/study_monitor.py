from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def study_monitor_snapshot(db: Session, *, active_minutes: int = 5, latest_limit: int = 15) -> dict[str, Any]:
    active_minutes = min(max(active_minutes, 1), 120)
    latest_limit = min(max(latest_limit, 1), 100)
    activity_cte = """
      WITH latest_activity AS (
        SELECT session_id, MAX(activity_at) AS activity_at FROM (
          SELECT id AS session_id, created_at AS activity_at FROM sessions
          UNION ALL SELECT session_id, timestamp FROM impressions
          UNION ALL SELECT session_id, timestamp FROM events
        ) activity GROUP BY session_id
      )
    """
    summary = db.execute(text(activity_cte + """
      SELECT
        COUNT(DISTINCT CASE WHEN s.norstat_pid IS NOT NULL THEN s.norstat_pid END) AS total_users,
        COUNT(DISTINCT CASE WHEN s.study_state = 'complete' THEN s.norstat_pid END) AS completed,
        COUNT(DISTINCT CASE WHEN s.screened_reason = 'age_65_plus' THEN s.norstat_pid END) AS screened_age,
        COUNT(DISTINCT CASE WHEN s.screened_reason = 'declined_participation' THEN s.norstat_pid END) AS declined,
        COUNT(DISTINCT CASE WHEN s.condition = 'control_recommendation' THEN s.norstat_pid END) AS control_total,
        COUNT(DISTINCT CASE WHEN s.condition = 'control_recommendation' AND s.study_state = 'complete' THEN s.norstat_pid END) AS control_completed,
        COUNT(DISTINCT CASE WHEN s.condition = 'treatment_problematic_content' THEN s.norstat_pid END) AS treatment_total,
        COUNT(DISTINCT CASE WHEN s.condition = 'treatment_problematic_content' AND s.study_state = 'complete' THEN s.norstat_pid END) AS treatment_completed,
        COUNT(DISTINCT CASE WHEN s.norstat_pid IS NOT NULL AND s.study_state <> 'complete'
          AND s.screened_reason IS NULL AND la.activity_at >= :active_cutoff THEN s.norstat_pid END) AS active_users,
        COUNT(DISTINCT CASE WHEN s.condition = 'control_recommendation' AND s.study_state <> 'complete'
          AND s.screened_reason IS NULL AND la.activity_at >= :active_cutoff THEN s.norstat_pid END) AS control_active,
        COUNT(DISTINCT CASE WHEN s.condition = 'treatment_problematic_content' AND s.study_state <> 'complete'
          AND s.screened_reason IS NULL AND la.activity_at >= :active_cutoff THEN s.norstat_pid END) AS treatment_active,
        MAX(la.activity_at) AS newest_activity
      FROM sessions s LEFT JOIN latest_activity la ON la.session_id = s.id
    """), {"active_cutoff": datetime.now(timezone.utc) - timedelta(minutes=active_minutes)}).mappings().one()
    recent = db.execute(text(activity_cte + """
      SELECT s.norstat_pid, s.study_state, s.consent_status, s.screened_reason, s.condition,
             la.activity_at,
             (SELECT COUNT(*) FROM impressions i WHERE i.session_id = s.id) AS impressions,
             (SELECT COUNT(*) FROM events e WHERE e.session_id = s.id) AS events
      FROM sessions s LEFT JOIN latest_activity la ON la.session_id = s.id
      WHERE s.norstat_pid IS NOT NULL
      ORDER BY la.activity_at DESC NULLS LAST LIMIT :latest_limit
    """), {"latest_limit": latest_limit}).mappings().all()

    def serializable(row):
        return {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in dict(row).items()}

    return {"active_minutes": active_minutes, "summary": serializable(summary), "recent": [serializable(row) for row in recent]}
