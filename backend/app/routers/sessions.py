import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.database import get_db
from backend.app.models.schemas import SessionResponse, SessionUpdate
from backend.app.services.session.session_service import session_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["Conversation & State Management"])

@router.get("/{session_id}", response_model=SessionResponse)
async def get_session_state(
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieves farmer session context, preferences (language, location, crops), and conversation history.
    """
    try:
        session = await session_service.get_or_create_session(session_id, db)
        return SessionResponse(
            session_id=session.session_id,
            user_id=session.user_id,
            preferred_language=session.preferred_language,
            state=session.state,
            district=session.district,
            landholding_acres=session.landholding_acres,
            crops_grown=list(session.crops_grown or []),
            history=list(session.history or []),
            created_at=session.created_at,
            updated_at=session.updated_at
        )
    except Exception as e:
        logger.exception("Failed to fetch session state")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session_state(
    session_id: str,
    updates: SessionUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Updates user preferences (preferred language, location, landholding size, crops grown).
    """
    try:
        session = await session_service.update_session(session_id, updates, db)
        return SessionResponse(
            session_id=session.session_id,
            user_id=session.user_id,
            preferred_language=session.preferred_language,
            state=session.state,
            district=session.district,
            landholding_acres=session.landholding_acres,
            crops_grown=list(session.crops_grown or []),
            history=list(session.history or []),
            created_at=session.created_at,
            updated_at=session.updated_at
        )
    except Exception as e:
        logger.exception("Failed to update session state")
        raise HTTPException(status_code=500, detail=str(e))
