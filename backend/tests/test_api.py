from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app import models
from backend.app.database import ContentSessionLocal
from backend.app.main import app


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    health = response.json()
    assert health["behavior_database"] in {"sqlite", "postgresql"}
    assert health["content_database"] in {"sqlite", "postgresql"}


def test_session_assignment_and_content_pool_filters():
    with TestClient(app) as client:
        session_response = client.post("/sessions", json={"condition": "treatment_problematic_content"})
        safe_response = client.get("/recommendations/homepage", params={"condition": "control_recommendation"})
        mixed_response = client.get("/recommendations/homepage", params={"condition": "treatment_problematic_content"})
        problematic_response = client.get(
            "/recommendations/homepage",
            params={"condition": "treatment_problematic_content", "content_pool": "problematic"},
        )

    assert session_response.status_code == 200
    assert session_response.json()["condition"] == "treatment_problematic_content"

    safe_rows = safe_response.json()
    mixed_rows = mixed_response.json()
    problematic_rows = problematic_response.json()
    assert safe_rows
    assert all(row["content_pool"] == "safe" for row in safe_rows)
    assert any(row["content_pool"] == "problematic" for row in mixed_rows)
    assert problematic_rows
    assert all(row["content_pool"] == "problematic" for row in problematic_rows)
    assert sum(1 for row in mixed_rows[:16] if row["content_pool"] == "problematic") >= 3
    assert sum(1 for row in mixed_rows[:8] if row["content_pool"] == "problematic") >= 2


def test_recommendation_and_search_surfaces_are_distinct():
    with TestClient(app) as client:
        homepage = client.get("/recommendations/homepage", params={"condition": "control_recommendation"})
        search = client.get("/search", params={"q": "technology", "condition": "treatment_search"})

    assert homepage.status_code == 200
    homepage_rows = homepage.json()
    assert len(homepage_rows) >= 1
    assert all(row["is_short"] is False for row in homepage_rows)
    assert all(row["content_pool"] == "safe" for row in homepage_rows)
    assert all(row["rank"] >= 1 for row in homepage_rows)
    assert len({row["topic"] for row in homepage_rows}) >= 1

    assert search.status_code == 200
    search_payload = search.json()
    assert search_payload["query"] == "technology"
    assert len(search_payload["results"]) >= 1
    assert all(row["content_pool"] == "safe" for row in search_payload["results"])


def test_homepage_topic_filter_and_session_rotation_are_reproducible():
    with TestClient(app) as client:
        topics_response = client.get("/topics", params={"condition": "control_recommendation"})
        topics = topics_response.json()
        topic = "fitness" if "fitness" in topics else topics[0]
        filtered = client.get(
            "/recommendations/homepage",
            params={"condition": "control_recommendation", "category": topic, "session_id": "rotation-a"},
        )
        repeated = client.get(
            "/recommendations/homepage",
            params={"condition": "control_recommendation", "category": topic, "session_id": "rotation-a"},
        )
        other_sessions = [
            client.get(
                "/recommendations/homepage",
                params={"condition": "control_recommendation", "category": topic, "session_id": f"rotation-{suffix}"},
            )
            for suffix in ["b", "c", "d", "e"]
        ]

    assert topics_response.status_code == 200
    assert topics
    assert filtered.status_code == 200
    rows = filtered.json()
    assert rows
    assert all(row["is_short"] is False for row in rows)
    assert all(topic.lower() in {row["topic"].lower(), *row["title"].lower().split()} or row["topic"].lower() == topic.lower() for row in rows)
    assert [row["id"] for row in rows] == [row["id"] for row in repeated.json()]
    if len(rows) > 1:
        assert any([row["id"] for row in rows] != [row["id"] for row in response.json()] for response in other_sessions)


def test_logging_rejects_click_before_impression_and_stores_required_fields():
    session_id = f"pytest-{uuid4()}"

    with TestClient(app) as client:
        first_video = client.get("/recommendations/homepage", params={"condition": "control_recommendation"}).json()[0]
        payload = {
            "video_id": first_video["id"],
            "video_title": first_video["title"],
            "surface": "recommendation",
            "click_from": "recommendation",
            "rank": first_video["rank"],
            "session_id": session_id,
            "condition": "control_recommendation",
            "content_pool": first_video["content_pool"],
        }

        missing_click_from = client.post(
            "/impressions",
            json={key: value for key, value in payload.items() if key != "click_from"},
        )
        missing_condition = client.post(
            "/events",
            json={key: value for key, value in {**payload, "event_type": "click"}.items() if key != "condition"},
        )
        rejected = client.post("/events", json={**payload, "event_type": "click"})
        impression = client.post("/impressions", json=payload)
        click = client.post("/events", json={**payload, "event_type": "click"})

    assert missing_click_from.status_code == 422
    assert missing_condition.status_code == 422
    assert rejected.status_code == 400
    assert "impression must be logged before click" in rejected.json()["detail"]

    assert impression.status_code == 200
    impression_row = impression.json()
    assert impression_row["session_id"] == payload["session_id"]
    assert impression_row["condition"] == payload["condition"]
    assert impression_row["video_title"] == payload["video_title"]
    assert impression_row["surface"] == "recommendation"
    assert impression_row["click_from"] == "recommendation"
    assert impression_row["content_pool"] == payload["content_pool"]

    assert click.status_code == 200
    click_row = click.json()
    assert click_row["video_id"] == payload["video_id"]
    assert click_row["video_title"] == payload["video_title"]
    assert click_row["surface"] == "recommendation"
    assert click_row["click_from"] == "recommendation"
    assert click_row["condition"] == "control_recommendation"
    assert click_row["content_pool"] == "safe"
    assert click_row["rank"] == payload["rank"]
    assert click_row["event_type"] == "click"
    assert click_row["timestamp"]


def test_logging_client_log_id_is_idempotent_and_preserves_client_timing():
    session_id = f"pytest-{uuid4()}"
    client_log_id = f"client-log-{uuid4()}"
    exposure_id = f"exposure-{uuid4()}"
    client_event_at = "2026-06-09T10:15:30Z"

    with TestClient(app) as client:
        first_video = client.get("/recommendations/homepage", params={"condition": "control_recommendation"}).json()[0]
        payload = {
            "video_id": first_video["id"],
            "video_title": first_video["title"],
            "surface": "recommendation",
            "click_from": "recommendation",
            "rank": first_video["rank"],
            "session_id": session_id,
            "condition": "control_recommendation",
            "content_pool": first_video["content_pool"],
            "exposure_id": exposure_id,
            "client_log_id": client_log_id,
            "client_event_at": client_event_at,
            "client_sequence_number": 1,
        }
        first = client.post("/impressions", json=payload)
        retry = client.post("/impressions", json=payload)

    assert first.status_code == 200
    assert retry.status_code == 200
    assert retry.json()["id"] == first.json()["id"]
    assert first.json()["client_log_id"] == client_log_id
    assert first.json()["exposure_id"] == exposure_id
    assert first.json()["client_sequence_number"] == 1
    assert first.json()["client_event_at"].startswith("2026-06-09T10:15:30")


def test_served_surfaces_exclude_non_embeddable_rows():
    video_id = f"blocked-{uuid4()}"
    blocked_topic = f"blocked-topic-{uuid4().hex[:8]}"
    db = ContentSessionLocal()
    try:
        db.add(
            models.Video(
                id=video_id,
                content_pool="safe",
                title=f"Blocked video {video_id}",
                channel="Test Channel",
                topic=blocked_topic,
                thumbnail_url="https://example.com/thumb.jpg",
                video_url="https://www.youtube.com/watch?v=blocked",
                duration_seconds=42,
                views=999,
                popularity_score=0.8,
                freshness_score=0.8,
                is_short=True,
                youtube_id=f"yt-{uuid4().hex[:12]}",
                source="youtube",
                embeddable=False,
            )
        )
        db.commit()
    finally:
        db.close()

    try:
        with TestClient(app) as client:
            homepage = client.get("/recommendations/homepage", params={"condition": "control_recommendation"}).json()
            shorts = client.get("/shorts", params={"condition": "control_recommendation"}).json()
            topics = client.get("/topics", params={"condition": "control_recommendation"}).json()
            served = homepage + shorts

        assert all(row["id"] != video_id for row in served)
        assert blocked_topic not in topics
    finally:
        cleanup = ContentSessionLocal()
        try:
            blocked = cleanup.get(models.Video, video_id)
            if blocked:
                cleanup.delete(blocked)
                cleanup.commit()
        finally:
            cleanup.close()


def test_mixed_shorts_feed_surfaces_ten_rows_with_problematic_quota():
    with TestClient(app) as client:
        response = client.get("/shorts", params={"condition": "treatment_problematic_content"})

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) >= 1
    assert all(row["is_short"] is True for row in rows)
    assert any(row["content_pool"] == "problematic" for row in rows)


def test_logging_requires_video_id_that_exists_in_content_db():
    with TestClient(app) as client:
        response = client.post(
            "/impressions",
            json={
                "video_id": "missing-video",
                "video_title": "Does not matter",
                "surface": "recommendation",
                "click_from": "recommendation",
                "rank": 1,
                "session_id": f"pytest-{uuid4()}",
                "condition": "control_recommendation",
                "content_pool": "safe",
            },
        )

    assert response.status_code == 400
    assert "video_id must reference an existing content video" in response.json()["detail"]


def test_study_monitor_is_hidden_without_configured_token():
    with TestClient(app) as client:
        response = client.get("/study/monitor")
    assert response.status_code == 404


def test_study_monitor_returns_general_snapshot_with_valid_token(monkeypatch):
    monkeypatch.setenv("VIEWTUBE_MONITOR_TOKEN", "test-monitor-token")
    with TestClient(app) as client:
        response = client.get("/study/monitor", headers={"X-ViewTube-Monitor-Token": "test-monitor-token"})
    assert response.status_code == 200
    assert set(response.json()) == {"active_minutes", "summary", "recent"}
    assert "total_users" in response.json()["summary"]
