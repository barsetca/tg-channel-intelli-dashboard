"""GET /api/v1/telegram/status для UI поиска live."""

from fastapi.testclient import TestClient

from app.main import app


def test_telegram_status_shape() -> None:
    with TestClient(app) as client:
        r = client.get("/api/v1/telegram/status")
        assert r.status_code == 200
        data = r.json()
        assert "api_configured" in data
        assert "session_ready" in data
        assert "interactive_login_enabled" in data
        assert "interactive_login_available" in data
        assert "startup_failure" in data
        assert isinstance(data["api_configured"], bool)
        assert isinstance(data["session_ready"], bool)
