"""Адаптер требования: POST /ai/plan_and_collect."""

from fastapi import APIRouter, Depends

from app.api.deps import get_intelligence_service
from app.schemas.intelligence import AIPlanAndCollectRequest, AIPlanAndCollectResponse
from app.services.intelligence_service import IntelligenceService

router = APIRouter()


@router.post(
    "/plan_and_collect",
    response_model=AIPlanAndCollectResponse,
    summary="ИИ-планирование запроса (строгий JSON)",
    description=(
        "Принимает `query`, выполняет текущий planner/review слой и возвращает контрактный JSON "
        "с plan_steps/api_url/fields_to_keep/confidence/needs_review без запуска фактического сбора."
    ),
)
async def ai_plan_and_collect(
    body: AIPlanAndCollectRequest,
    svc: IntelligenceService = Depends(get_intelligence_service),
) -> AIPlanAndCollectResponse:
    return await svc.plan_and_collect_adapter(body)
