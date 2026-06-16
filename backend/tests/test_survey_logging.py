from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.main import app


def test_entry_survey_stores_demographics_and_logs_gender():
    session_id = f"survey-{uuid4()}"
    user_id = f"user-{uuid4()}"
    survey = {
        "user_id": user_id,
        "condition": "control_recommendation",
        "gender": "woman",
        "age": 24,
        "household_living_arrangement": "living_with_partner_or_roommate",
        "education": "bachelor",
        "region_dk": "hovedstaden",
        "left_right_orientation": 4,
    }

    with TestClient(app) as client:
        survey_response = client.post(f"/sessions/{session_id}/survey", json=survey)
        first_video = client.get("/recommendations/homepage", params={"condition": "control_recommendation"}).json()[0]
        log_payload = {
            "user_id": user_id,
            "session_id": session_id,
            "condition": "control_recommendation",
            "gender": "woman",
            "video_id": first_video["id"],
            "video_title": first_video["title"],
            "surface": "recommendation",
            "click_from": "recommendation",
            "content_pool": first_video["content_pool"],
            "rank": first_video["rank"],
        }
        impression = client.post("/impressions", json=log_payload)
        event = client.post("/events", json={**log_payload, "event_type": "watch_start"})

    assert survey_response.status_code == 200
    session = survey_response.json()
    assert session["session_id"] == session_id
    assert session["user_id"] == user_id
    assert session["survey_completed"] is True
    assert session["gender"] == "woman"
    assert session["age"] == 24
    assert session["household_living_arrangement"] == "living_with_partner_or_roommate"
    assert session["education"] == "bachelor"
    assert session["region_dk"] == "hovedstaden"
    assert session["left_right_orientation"] == 4

    assert impression.status_code == 200
    assert impression.json()["gender"] == "woman"
    assert impression.json()["user_id"] == user_id
    assert event.status_code == 200
    assert event.json()["gender"] == "woman"
    assert event.json()["video_title"] == first_video["title"]
