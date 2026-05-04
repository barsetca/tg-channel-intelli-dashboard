"""GET /api/v1/orchestration/jobs/{job_id}."""

from fastapi.testclient import TestClient

from app.main import app


def test_orchestration_job_unknown_returns_404() -> None:
    with TestClient(app) as client:
        r = client.get("/api/v1/orchestration/jobs/00000000-0000-4000-8000-000000000001")
        assert r.status_code == 404
