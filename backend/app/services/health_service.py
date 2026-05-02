from app.core.config import Settings


class HealthService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def status(self) -> dict[str, str]:
        return {
            "status": "ok",
            "environment": self._settings.environment,
        }
