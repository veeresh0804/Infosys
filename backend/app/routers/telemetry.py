"""Telemetry API - read-only observability over the Agent Router telemetry pipeline."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.services.telemetry_service import telemetry_service

router = APIRouter(prefix="/api/telemetry", tags=["Telemetry"])


@router.get("/summary")
async def get_telemetry_summary(
    window_size: int = Query(500, ge=1, le=1000)
):
    """Aggregated Agent Router telemetry: totals, intent/agent/engine distributions, latency & confidence."""
    return await telemetry_service.get_summary(window_size=window_size)


@router.get("/health")
async def telemetry_health():
    """Confirms the telemetry pipeline is reachable (used by developer dashboards)."""
    summary = await telemetry_service.get_summary(window_size=1)
    return {"status": "healthy", "total_queries": summary["total_queries"]}
