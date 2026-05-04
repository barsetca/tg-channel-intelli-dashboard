"""Очередь оркестратора: стадии и статусы job."""

from __future__ import annotations

import asyncio

import pytest

from app.orchestration.coordinator import JobStatus, OrchestrationCoordinator


@pytest.mark.asyncio
async def test_telegram_discovery_job_reaches_completed() -> None:
    coord = OrchestrationCoordinator()
    await coord.start()
    try:
        jid = await coord.schedule_telegram_channel_discovery(payload={"topic": "test niche", "count": 3})
        for _ in range(100):
            job = coord.get_job(jid)
            assert job is not None
            if job.status == JobStatus.COMPLETED:
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("job did not complete in time")

        final = coord.get_job(jid)
        assert final is not None
        assert final.status == JobStatus.COMPLETED
        assert final.stage is None
        assert final.stage_label is None
    finally:
        await coord.stop()
