from fastapi.testclient import TestClient

from backend.app.main import app


def test_event_requires_condition_and_content_pool():
    payload = {
        "video_id": "1",
        "video_title": "Test",
        "event_type": "click",
        "click_from": "search",
        "content_pool": "safe",
    }
    with TestClient(app) as client:
        missing_condition = client.post("/event", json=payload)
        missing_pool = client.post("/event", json={key: value for key, value in payload.items() if key != "content_pool"} | {"condition": "treatment_search"})

    assert missing_condition.status_code == 400
    assert missing_pool.status_code == 400
