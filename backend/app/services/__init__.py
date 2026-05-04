from app.services.channel_metrics import compute_channel_metrics
from app.services.channel_service import ChannelService
from app.services.health_service import HealthService
from app.services.vector_service import VectorService

# IntelligenceService не импортируем здесь: иначе цикл app.services → intelligence_service → ai.pipeline.

__all__ = ["ChannelService", "HealthService", "VectorService", "compute_channel_metrics"]
