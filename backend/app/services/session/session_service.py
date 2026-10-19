import logging
import uuid
import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from backend.app.models.schemas import SessionModel, SessionUpdate, SessionResponse, FlaggedReviewModel

logger = logging.getLogger(__name__)

class SessionService:
    """
    Conversation State Management Service.
    Stores and manages farmer session context, user preferences (language, location, landholding, crops),
    and conversational history in SQLite.
    """

    async def get_or_create_session(self, session_id: Optional[str], db: AsyncSession) -> SessionModel:
        sid = session_id.strip() if session_id and session_id.strip() else f"farmer_{uuid.uuid4().hex[:12]}"

        result = await db.execute(select(SessionModel).where(SessionModel.session_id == sid))
        session = result.scalars().first()

        if not session:
            logger.info(f"Creating new session state: {sid}")
            session = SessionModel(
                session_id=sid,
                user_id="farmer_" + str(uuid.uuid4())[:8],
                preferred_language="en",
                state=None,
                district=None,
                landholding_acres=None,
                crops_grown=[],
                history=[]
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)

        return session

    async def update_session(self, session_id: str, updates: SessionUpdate, db: AsyncSession) -> SessionModel:
        session = await self.get_or_create_session(session_id, db)

        if updates.user_id is not None:
            session.user_id = updates.user_id
        if updates.preferred_language is not None:
            session.preferred_language = updates.preferred_language
        if updates.state is not None:
            session.state = updates.state
        if updates.district is not None:
            session.district = updates.district
        if updates.landholding_acres is not None:
            session.landholding_acres = updates.landholding_acres
        if updates.crops_grown is not None:
            session.crops_grown = updates.crops_grown

        session.updated_at = datetime.datetime.utcnow()
        await db.commit()
        await db.refresh(session)
        return session

    async def append_history(
        self,
        session_id: str,
        role: str,
        text: str,
        canonical_text: str,
        metadata: Optional[Dict[str, Any]],
        db: AsyncSession
    ):
        session = await self.get_or_create_session(session_id, db)
        current_history = list(session.history or [])
        current_history.append({
            "role": role,
            "text": text,
            "canonical_text": canonical_text,
            "metadata": metadata or {},
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
        # Cap stored history to the last 50 messages to prevent memory/storage bloat
        session.history = current_history[-50:]
        session.updated_at = datetime.datetime.utcnow()
        await db.commit()

    async def get_flagged_reviews(self, db: AsyncSession, limit: int = 50) -> List[FlaggedReviewModel]:
        result = await db.execute(
            select(FlaggedReviewModel)
            .order_by(FlaggedReviewModel.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

session_service = SessionService()
