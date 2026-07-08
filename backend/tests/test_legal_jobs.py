from fastapi.testclient import TestClient

from app.main import app


def test_create_and_get_mock_legal_job() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/legal/jobs",
        json={
            "scenario": "chat",
            "message": "Проверь документ.",
            "document_context": {
                "mode": "selection",
                "text": "Текст договора.",
                "character_count": 14,
            },
            "provider": {"provider": "mock"},
        },
    )

    assert response.status_code == 200
    created = response.json()
    assert created["job_id"].startswith("legal_job_")
    assert created["status"] in {"queued", "running", "succeeded"}

    status_response = client.get(f"/api/legal/jobs/{created['job_id']}")

    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["job_id"] == created["job_id"]
    assert payload["status"] in {"queued", "running", "succeeded"}
    if payload["status"] == "succeeded":
        assert payload["response"]["scenario"] == "chat"


def test_get_unknown_legal_job_returns_404() -> None:
    client = TestClient(app)

    response = client.get("/api/legal/jobs/unknown")

    assert response.status_code == 404
    assert response.json()["detail"]["error_code"] == "JOB_NOT_FOUND"
