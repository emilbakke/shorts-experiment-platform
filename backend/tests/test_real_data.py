from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_videos_not_empty():
    r = client.get("/videos")
    assert r.status_code == 200
    assert len(r.json()) > 0
