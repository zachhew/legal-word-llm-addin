from fastapi.testclient import TestClient

from app.main import app


def test_risk_review_selection_returns_suggested_action() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/legal/run",
        json={
            "scenario": "risk_review",
            "message": "Проверь риски.",
            "document_context": {
                "mode": "selection",
                "text": "Ответственность не ограничена.",
                "character_count": 29,
                "captured_at": "2026-07-08T00:00:00Z",
            },
            "provider": {"provider": "mock", "api_key": "should-not-be-returned"},
        },
    )

    payload = response.json()

    assert response.status_code == 200
    assert payload["scenario"] == "risk_review"
    assert payload["suggested_actions"][0]["type"] == "replace_selection"
    assert payload["suggested_actions"][0]["original_text"] == "Ответственность не ограничена."
    assert "api_key" not in str(payload)


def test_empty_context_returns_warning() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/legal/run",
        json={
            "scenario": "chat",
            "message": "Что с документом?",
            "document_context": {
                "mode": "full_document",
                "text": "",
                "character_count": 0,
            },
            "provider": {"provider": "mock"},
        },
    )

    assert response.status_code == 200
    assert "Document context is empty." in response.json()["warnings"]
