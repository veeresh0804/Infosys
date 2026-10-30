"""Agent Router telemetry pipeline.

Records one telemetry row per routed farmer query (intent, sub-agent, engine,
confidence, latency, chunk count) into SQLite and exposes aggregates so
extension workers and the developer dashboard can observe system behaviour.

Telemetry must never break the farmer-facing flow: every telemetry failure is
swallowed and logged as a warning.
"""

import logging
import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select

from backend.app.database import AsyncSessionLocal
from backend.app.models.schemas import QueryTelemetryModel

logger = logging.getLogger(__name__)


class TelemetryService:
    """SQLite-backed telemetry pipeline for the Central Agent Router."""

    _table_ready = False

    async def _ensure_table(self) -> None:
        """Self-healing on upgrade: creates the telemetry table if an older database lacks it."""
        if TelemetryService._table_ready:
            return
        async with AsyncSessionLocal() as db:
            conn = await db.connection()
            await conn.run_sync(lambda sync_conn: QueryTelemetryModel.metadata.create_all(sync_conn, tables=[QueryTelemetryModel.__table__]))
        TelemetryService._table_ready = True

    async def record_query_event(
        self,
        session_id: Optional[str],
        canonical_query: str,
        detected_language: str,
        intent: str,
        intent_confidence: float,
        sub_agent: str,
        engine_used: Optional[str] = None,
        confidence_score: float = 0.0,
        is_low_confidence: bool = False,
        is_fallback: bool = False,
        chunk_count: int = 0,
        latency_ms: int = 0,
    ) -> None:
        """Persists one query telemetry row. Never raises - observability must not break queries."""
        try:
            await self._ensure_table()
            async with AsyncSessionLocal() as db:
                row = QueryTelemetryModel(
                    session_id=session_id,
                    canonical_query=canonical_query[:2000],
                    detected_language=detected_language,
                    intent=intent,
                    intent_confidence=float(intent_confidence or 0.0),
                    sub_agent=sub_agent,
                    engine_used=(engine_used or "")[:128],
                    confidence_score=float(confidence_score or 0.0),
                    is_low_confidence=1 if is_low_confidence else 0,
                    is_fallback=1 if is_fallback else 0,
                    chunk_count=int(chunk_count or 0),
                    latency_ms=int(latency_ms or 0),
                    created_at=datetime.datetime.utcnow()
                )
                db.add(row)
                await db.commit()
        except Exception as e:
            logger.warning(f"Telemetry recording bypassed: {e}")

    def _row_to_dict(self, r: QueryTelemetryModel) -> Dict[str, Any]:
        return {
            "id": r.id,
            "session_id": r.session_id,
            "canonical_query": r.canonical_query,
            "detected_language": r.detected_language,
            "intent": r.intent,
            "intent_confidence": r.intent_confidence,
            "sub_agent": r.sub_agent,
            "engine_used": r.engine_used,
            "confidence_score": r.confidence_score,
            "is_low_confidence": bool(r.is_low_confidence),
            "is_fallback": bool(r.is_fallback),
            "chunk_count": r.chunk_count,
            "latency_ms": r.latency_ms,
            "created_at": r.created_at.isoformat() if r.created_at else None
        }

    async def get_summary(self, window_size: int = 500) -> Dict[str, Any]:
        """Aggregates query telemetry (totals, intent/agent/engine distributions, latency, confidence)."""
        out: Dict[str, Any] = {
            "total_queries": 0,
            "window_size": window_size,
            "by_intent": {},
            "by_sub_agent": {},
            "by_engine": {},
            "avg_confidence": None,
            "avg_intent_confidence": None,
            "avg_latency_ms": None,
            "max_latency_ms": None,
            "low_confidence_count": 0,
            "fallback_count": 0,
            "unique_sessions": 0,
            "recent": []
        }
        try:
            await self._ensure_table()
            async with AsyncSessionLocal() as db:
                res = await db.execute(
                    select(QueryTelemetryModel)
                    .order_by(QueryTelemetryModel.id.desc())
                    .limit(window_size)
                )
                rows = res.scalars().all()

                rows = list(rows)
                out["total_queries"] = len(rows)
                if not rows:
                    return out

                by_intent: Dict[str, int] = {}
                by_agent: Dict[str, int] = {}
                by_engine: Dict[str, int] = {}
                latencies = []
                intents = []
                sessions = set()

                for r in rows:
                    by_intent[r.intent] = by_intent.get(r.intent, 0) + 1
                    by_agent[r.sub_agent] = by_agent.get(r.sub_agent, 0) + 1
                    if r.engine_used:
                        by_engine[r.engine_used] = by_engine.get(r.engine_used, 0) + 1
                    latencies.append(r.latency_ms or 0)
                    intents.append((r.intent_confidence or 0.0, r.confidence_score or 0.0))
                    if r.session_id:
                        sessions.add(r.session_id)
                    if r.is_low_confidence:
                        out["low_confidence_count"] += 1
                    if r.is_fallback:
                        out["fallback_count"] += 1

                out["by_intent"] = by_intent
                out["by_sub_agent"] = by_agent
                out["by_engine"] = by_engine
                out["avg_confidence"] = round(sum(c for _, c in intents) / len(rows), 3)
                out["avg_intent_confidence"] = round(sum(i for i, _ in intents) / len(rows), 3)
                out["avg_latency_ms"] = int(sum(latencies) / len(rows))
                out["max_latency_ms"] = max(latencies) if latencies else None
                out["unique_sessions"] = len(sessions)
                out["recent"] = [self._row_to_dict(r) for r in rows if r.is_low_confidence or r.is_fallback][:10]
        except Exception as e:
            logger.warning(f"Telemetry summary bypassed: {e}")
        return out


telemetry_service = TelemetryService()
