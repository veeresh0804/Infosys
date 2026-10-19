import logging
from typing import Dict, Any, Tuple, List
from backend.app.services.live_data.weather_service import weather_service
from backend.app.models.schemas import RetrievedChunk

logger = logging.getLogger(__name__)

class WeatherAgent:
    """
    Specialized Sub-Agent for Weather Forecasts & Meteorological Advisories.
    Fetches real-time agro-meteorological data from Open-Meteo.
    """

    async def execute(
        self,
        query: str,
        farmer_profile: Dict[str, Any],
        entities: List[Any]
    ) -> Tuple[str, List[RetrievedChunk], Dict[str, Any]]:
        # Check if location entity specified in query
        location = None
        for ent in entities:
            if ent.label == "LOCATION":
                location = ent.text
                break

        if not location:
            location = farmer_profile.get("district", "Bengaluru Rural")

        weather_info = await weather_service.get_weather(district=location)

        answer = (
            f"Current Weather & Advisory for {weather_info.location}:\n"
            f"• Temperature: {weather_info.temperature}°C\n"
            f"• Relative Humidity: {weather_info.humidity}%\n"
            f"• Precipitation Probability: {weather_info.precipitation_prob}%\n"
            f"• Wind Speed: {weather_info.wind_speed} km/h\n\n"
            f"🌾 Agricultural Advisory:\n{weather_info.advisory}\n"
            f"(Source: {weather_info.source})"
        )

        live_data_dict = {
            "weather": weather_info.model_dump()
        }
        return answer, [], live_data_dict

weather_agent = WeatherAgent()
