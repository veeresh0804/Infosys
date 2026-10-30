import logging
import httpx
from typing import Optional, Dict
from backend.app.models.schemas import WeatherData

logger = logging.getLogger(__name__)

# Geo-coordinates for key agricultural districts across Karnataka, Punjab, Maharashtra, etc.
DISTRICT_COORDINATES: Dict[str, Dict[str, float]] = {
    "bengaluru": {"lat": 12.9716, "lon": 77.5946},
    "bengaluru rural": {"lat": 13.2846, "lon": 77.5457},
    "mandya": {"lat": 12.5218, "lon": 76.8951},
    "mysore": {"lat": 12.2958, "lon": 76.6394},
    "mysuru": {"lat": 12.2958, "lon": 76.6394},
    "kolar": {"lat": 13.1367, "lon": 78.1291},
    "dharwad": {"lat": 15.4589, "lon": 75.0078},
    "belagavi": {"lat": 15.8497, "lon": 74.4977},
    "shivamogga": {"lat": 13.9299, "lon": 75.5681},
    "shimoga": {"lat": 13.9299, "lon": 75.5681},
    "ludhiana": {"lat": 30.9010, "lon": 75.8573},
    "karnal": {"lat": 29.6857, "lon": 76.9905},
    "nagpur": {"lat": 21.1458, "lon": 79.0882},
    "pune": {"lat": 18.5204, "lon": 73.8567},
}

class WeatherService:
    """
    Agricultural Weather Forecast Service.
    Powered by Open-Meteo free API (no API key required).
    Provides real-time temperature, humidity, precipitation probability, and agronomic advisory.
    """

    async def get_weather(
        self,
        district: Optional[str] = "Bengaluru Rural",
        latitude: Optional[float] = None,
        longitude: Optional[float] = None
    ) -> WeatherData:
        """
        Fetches live agricultural weather forecast for given district or coordinates.
        """
        dist_key = (district or "bengaluru rural").lower().strip()
        coords = DISTRICT_COORDINATES.get(dist_key, {"lat": 12.9716, "lon": 77.5946})
        lat = latitude if latitude is not None else coords["lat"]
        lon = longitude if longitude is not None else coords["lon"]

        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto"
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    current = data.get("current", {})
                    daily = data.get("daily", {})

                    temp = float(current.get("temperature_2m", 26.0))
                    humidity = float(current.get("relative_humidity_2m", 65.0))
                    wind_speed = float(current.get("wind_speed_10m", 8.5))
                    precip_prob = float(daily.get("precipitation_probability_max", [20.0])[0])

                    # Formulate agricultural advice based on meteorology
                    advisory_parts = []
                    if precip_prob > 50.0:
                        advisory_parts.append("High probability of rainfall (>50%). Postpone foliar pesticide sprays and top-dress fertilizers. Ensure drainage channels are clear.")
                    elif humidity > 80.0 and temp > 25.0:
                        advisory_parts.append("High humidity and warm conditions favor fungal spore germination (powdery mildew / blight). Monitor lower leaf canopies.")
                    elif wind_speed > 20.0:
                        advisory_parts.append("High wind speeds (>20 km/h). Avoid fine mist spraying to prevent pesticide drift.")
                    else:
                        advisory_parts.append("Favorable weather conditions for field operations, irrigation, and crop scouting.")

                    summary = f"Temperature: {temp}°C | Humidity: {humidity}% | Rain Probability: {precip_prob}% | Wind: {wind_speed} km/h"

                    return WeatherData(
                        location=district.capitalize() if district else "Current Field Location",
                        latitude=lat,
                        longitude=lon,
                        temperature=temp,
                        humidity=humidity,
                        precipitation_prob=precip_prob,
                        wind_speed=wind_speed,
                        forecast_summary=summary,
                        advisory=" ".join(advisory_parts),
                        source="Open-Meteo Live API"
                    )
        except Exception as e:
            logger.warning(f"Open-Meteo API call error: {e}. Returning reliable agricultural fallback.")

        # Reliable mock fallback
        return WeatherData(
            location=district.capitalize() if district else "Bengaluru Rural",
            latitude=lat,
            longitude=lon,
            temperature=27.5,
            humidity=68.0,
            precipitation_prob=25.0,
            wind_speed=9.0,
            forecast_summary="Partly cloudy, mild breeze with 25% chance of light showers.",
            advisory="Normal field operations and irrigation recommended. Conditions are suitable for weeding and scouting.",
            source="MOCK_WEATHER_DATA (Fallback)"
        )

weather_service = WeatherService()
