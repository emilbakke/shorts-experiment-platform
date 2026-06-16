from fastapi.testclient import TestClient

from backend.app.main import app


def test_compact_event_has_condition_session_and_pool():
    with TestClient(app) as client:
        video_id = client.get("/videos").json()[0]["id"]
        payload = {
            "video_id": video_id,
            "video_title": "Test",
            "event_type": "click",
            "click_from": "search",
            "condition": "treatment_search",
            "content_pool": "safe",
        }
        response = client.post("/event", json=payload)

    assert response.status_code == 200
    row = response.json()
    assert row["session_id"]
    assert row["condition"] == "treatment_search"
    assert row["surface"] == "search"
    assert row["click_from"] == "search"
    assert row["content_pool"] == "safe"


def test_compact_event_rejects_unknown_video_id():
    payload = {
        "video_id": "missing-video-id",
        "video_title": "Missing",
        "event_type": "click",
        "click_from": "search",
        "condition": "treatment_search",
        "content_pool": "safe",
    }
    with TestClient(app) as client:
        response = client.post("/event", json=payload)

    assert response.status_code == 400
