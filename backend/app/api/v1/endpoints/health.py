from fastapi import APIRouter, Depends

from app.api.deps import get_health_service
from app.schemas.common import HealthResponse
from app.services.health_service import HealthService

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(service: HealthService = Depends(get_health_service)) -> HealthResponse:
    data = service.status()
    return HealthResponse(**data)
