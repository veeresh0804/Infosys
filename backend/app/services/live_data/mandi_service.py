import logging
import httpx
from typing import List, Optional
from backend.app.models.schemas import MandiPriceItem
from backend.app.config import settings

logger = logging.getLogger(__name__)

# Fallback realistic APMC Mandi prices for major Indian agricultural markets
MOCK_MANDI_DATA = [
    {
        "commodity": "Tomato",
        "state": "Karnataka",
        "district": "Kolar",
        "market": "Kolar APMC",
        "min_price": 1400.0,
        "max_price": 2200.0,
        "modal_price": 1850.0,
        "arrival_date": "Today",
        "source": "MOCK_AGMARKNET_DATA (Kolar APMC)"
    },
    {
        "commodity": "Paddy",
        "state": "Karnataka",
        "district": "Mandya",
        "market": "Mandya APMC",
        "min_price": 2183.0,
        "max_price": 2350.0,
        "modal_price": 2250.0,
        "arrival_date": "Today",
        "source": "MOCK_AGMARKNET_DATA (Mandya APMC)"
    },
    {
        "commodity": "Wheat",
        "state": "Punjab",
        "district": "Ludhiana",
        "market": "Khanna APMC",
        "min_price": 2275.0,
        "max_price": 2400.0,
        "modal_price": 2320.0,
        "arrival_date": "Today",
        "source": "MOCK_AGMARKNET_DATA (Khanna APMC)"
    },
    {
        "commodity": "Cotton",
        "state": "Maharashtra",
        "district": "Nagpur",
        "market": "Nagpur APMC",
        "min_price": 6800.0,
        "max_price": 7500.0,
        "modal_price": 7120.0,
        "arrival_date": "Today",
        "source": "MOCK_AGMARKNET_DATA (Nagpur APMC)"
    },
    {
        "commodity": "Maize",
        "state": "Karnataka",
        "district": "Davanagere",
        "market": "Davanagere APMC",
        "min_price": 1950.0,
        "max_price": 2150.0,
        "modal_price": 2090.0,
        "arrival_date": "Today",
        "source": "MOCK_AGMARKNET_DATA (Davanagere APMC)"
    }
]

class MandiService:
    """
    AGMARKNET Mandi Prices Service.
    Official Source: data.gov.in AGMARKNET API (resource: 9ef84268-d588-465a-a308-a864a43d0070)
    Gracefully falls back to clearly-labelled mock data if API key is not configured or portal is unavailable.
    """

    def __init__(self):
        self.api_key = settings.DATA_GOV_IN_API_KEY
        self.resource_id = settings.AGMARKNET_RESOURCE_ID

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip() and not self.api_key.startswith("your_"))

    async def get_mandi_prices(
        self,
        commodity: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 5
    ) -> List[MandiPriceItem]:
        """
        Retrieves real-time APMC mandi prices from AGMARKNET API or clearly-labelled mock data.
        """
        if self.is_configured:
            try:
                params = {
                    "api-key": self.api_key,
                    "format": "json",
                    "limit": limit
                }
                if commodity:
                    params["filters[commodity]"] = commodity.capitalize()
                if state:
                    params["filters[state]"] = state.capitalize()

                url = f"https://api.data.gov.in/resource/{self.resource_id}"
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(url, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        records = data.get("records", [])
                        if records:
                            return [
                                MandiPriceItem(
                                    commodity=r.get("commodity", commodity or "Unknown"),
                                    state=r.get("state", state or "Unknown"),
                                    district=r.get("district", "APMC"),
                                    market=r.get("market", "APMC Market"),
                                    min_price=float(r.get("min_price", 0.0)),
                                    max_price=float(r.get("max_price", 0.0)),
                                    modal_price=float(r.get("modal_price", 0.0)),
                                    arrival_date=r.get("arrival_date", "Today"),
                                    source="AGMARKNET_API (data.gov.in)"
                                )
                                for r in records
                            ]
            except Exception as e:
                logger.warning(f"Error fetching from live AGMARKNET API: {e}. Falling back to mock dataset.")

        # Clearly-labelled mock fallback
        logger.info("[MOCK] Serving clearly-labelled AGMARKNET mock mandi prices.")
        results = []
        target_commodity = (commodity or "").lower()
        target_state = (state or "").lower()

        for item in MOCK_MANDI_DATA:
            matches_commodity = not target_commodity or target_commodity in item["commodity"].lower()
            matches_state = not target_state or target_state in item["state"].lower()
            if matches_commodity or matches_state:
                results.append(MandiPriceItem(**item))

        return results[:limit] if results else [MandiPriceItem(**MOCK_MANDI_DATA[0])]

mandi_service = MandiService()
