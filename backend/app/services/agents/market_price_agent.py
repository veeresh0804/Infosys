from typing import Dict, Any, Tuple, List
from backend.app.services.live_data.mandi_service import mandi_service
from backend.app.models.schemas import RetrievedChunk

class MarketPriceAgent:
    """
    Specialized Sub-Agent for Mandi & Market Prices.
    Retrieves live AGMARKNET APMC prices for specified crops and districts.
    """

    async def execute(
        self,
        query: str,
        farmer_profile: Dict[str, Any],
        entities: List[Any]
    ) -> Tuple[str, List[RetrievedChunk], Dict[str, Any]]:
        # Identify crop and state from extracted entities or farmer profile
        crop = None
        state = farmer_profile.get("state", "Karnataka")

        for ent in entities:
            if ent.label == "CROP" and not crop:
                crop = ent.text
            elif ent.label == "LOCATION":
                state = ent.text

        if not crop:
            # Fall back to farmer's primary crop
            farmer_crops = farmer_profile.get("crops_grown", ["Tomato"])
            crop = farmer_crops[0] if farmer_crops else "Tomato"

        prices = await mandi_service.get_mandi_prices(commodity=crop, state=state, limit=3)

        if prices:
            p = prices[0]
            answer = (
                f"Today's AGMARKNET Mandi Price for {p.commodity} in {p.market} ({p.district}, {p.state}):\n"
                f"• Modal Price: ₹{p.modal_price:,.2f} per quintal\n"
                f"• Minimum Price: ₹{p.min_price:,.2f} / quintal\n"
                f"• Maximum Price: ₹{p.max_price:,.2f} / quintal\n"
                f"(Source: {p.source}, Arrival: {p.arrival_date})"
            )
            live_data_dict = {
                "mandi_prices": [p.model_dump() for p in prices],
                "commodity": crop,
                "state": state
            }
        else:
            answer = f"No active APMC mandi price arrivals found for {crop} in {state}. Please check nearby district mandis."
            live_data_dict = {"commodity": crop, "state": state, "mandi_prices": []}

        # Empty chunks as this is real-time API lookup
        return answer, [], live_data_dict

market_price_agent = MarketPriceAgent()
