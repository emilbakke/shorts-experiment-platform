from scripts.study_postgres_dashboard import display, render, table


def test_dashboard_formats_general_activity_without_special_participant():
    snapshot = {"active_minutes": 5, "summary": {"total_users": 4, "active_users": 1, "completed": 2, "screened_age": 1, "declined": 0, "control_total": 2, "control_active": 1, "control_completed": 1, "treatment_total": 2, "treatment_active": 0, "treatment_completed": 1, "newest_activity": "2026-06-09T20:00:00+02:00"}, "recent": [{"norstat_pid": "60000", "study_state": "reel_active", "consent_status": "accepted", "screened_reason": None, "condition": "control_recommendation", "impressions": 8, "events": 10, "activity_at": "2026-06-09T20:00:00+02:00"}]}
    output = render(snapshot)
    assert "TOTAL USERS: 4" in output and "60000" in output
    assert "CONTROL: total=2 active=1 complete=1" in output
    assert "TREATMENT: total=2 active=0 complete=1" in output
    assert "EVENTS" in output and "STATE" in output
    assert "Participant detail" not in output
    assert display(None) == "-"
    assert "complete" in table(["STATE"], [["complete"]], [10])
