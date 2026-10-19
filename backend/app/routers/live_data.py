import logging
from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException
from backend.app.models.schemas import MandiPriceItem, WeatherData, SchemeEligibilityItem
from backend.app.services.live_data.mandi_service import mandi_service
from backend.app.services.live_data.weather_service import weather_service
from backend.app.services.live_data.scheme_checker import scheme_checker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/live-data", tags=["Real-time Agricultural APIs"])

@router.get("/mandi-prices", response_model=List[MandiPriceItem])
async def get_mandi_prices(
    commodity: Optional[str] = Query(None, description="Crop name (e.g., Tomato, Paddy, Wheat)"),
    state: Optional[str] = Query(None, description="State name (e.g., Karnataka, Punjab)"),
    limit: int = Query(5, ge=1, le=20)
):
    """
    Fetches real-time APMC mandi market prices from AGMARKNET API (data.gov.in) with mock fallback.
    """
    try:
        return await mandi_service.get_mandi_prices(commodity=commodity, state=state, limit=limit)
    except Exception as e:
        logger.exception("Failed to retrieve mandi prices")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/weather", response_model=WeatherData)
async def get_weather(
    district: Optional[str] = Query("Bengaluru Rural", description="District or agricultural zone"),
    latitude: Optional[float] = Query(None, description="Latitude"),
    longitude: Optional[float] = Query(None, description="Longitude")
):
    """
    Fetches real-time weather and agro-meteorological advisory from Open-Meteo.
    """
    try:
        return await weather_service.get_weather(district=district, latitude=latitude, longitude=longitude)
    except Exception as e:
        logger.exception("Failed to retrieve weather")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/scheme-eligibility", response_model=List[SchemeEligibilityItem])
async def check_schemes(
    landholding_acres: float = Query(2.0, ge=0.0, le=1000.0, description="Farmer landholding in acres"),
    crops: Optional[str] = Query("Tomato,Paddy", description="Comma-separated crops grown"),
    state: str = Query("Karnataka", description="Farmer state")
):
    """
    Evaluates farmer eligibility against major government schemes (PM-KISAN, PMFBY, KCC, Soil Health Card).
    """
    try:
        crops_list = [c.strip() for c in crops.split(",") if c.strip()]
        return scheme_checker.check_eligibility(
            landholding_acres=landholding_acres,
            crops_grown=crops_list,
            state=state
        )
    except Exception as e:
        logger.exception("Failed to evaluate scheme eligibility")
        raise HTTPException(status_code=500, detail=str(e))
