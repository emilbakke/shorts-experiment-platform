from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_event_requires_condition_and_pool():
    payload = {
        "video_id": "1",
        "video_title": "Test",
        "event_type": "click",
        "click_from": "search"
    }
    r = client.post("/event", json=payload)
    assert r.status_code in (400, 422)

def test_event_accepts_condition_and_pool():
    video_id = client.get("/videos").json()[0]["id"]
    payload = {
        "video_id": video_id,
        "video_title": "Test",
        "event_type": "click",
        "click_from": "search",
        "condition": "treatment_search",
        "content_pool": "safe",
        "surface": "search"
    }
    r = client.post("/event", json=payload)
    assert r.status_code == 200
