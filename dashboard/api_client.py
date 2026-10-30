"""HTTP client for the KisanSahayak FastAPI backend.

The Streamlit dashboard never talks to SQLite or the vector store directly;
it only uses the public REST API so it stays useful against a remote backend.
"""

from __future__ import annotations

from typing import Any, Optional

import requests

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


class BackendError(RuntimeError):
    """Raised when the backend is unreachable or returns an error."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class AgriApiClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        long_timeout: float = 300.0,
    ):
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.long_timeout = long_timeout
        self._session = requests.Session()

    # ------------------------------------------------------------------ helpers
    def _request(self, method: str, path: str, *, timeout: Optional[float] = None, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = self._session.request(
                method, url, timeout=timeout or self.timeout, **kwargs
            )
        except requests.RequestException as exc:
            raise BackendError(
                f"Cannot reach the backend at {self.base_url}. "
                f"Start it with: python -m uvicorn backend.app.main:app --port 8000. "
                f"({exc.__class__.__name__})"
            ) from exc

        if not response.ok:
            detail = response.text.strip()
            try:
                payload = response.json()
                if isinstance(payload, dict) and "detail" in payload:
                    detail = str(payload["detail"])
            except ValueError:
                pass
            raise BackendError(f"HTTP {response.status_code}: {detail}", status_code=response.status_code)

        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    # -------------------------------------------------------------------- status
    def health(self) -> dict:
        return self._request("GET", "/health")

    def status(self) -> dict:
        return self._request("GET", "/")

    # ------------------------------------------------------------------ pipeline
    def query(self, text: str, language: str, session_id: str) -> dict:
        return self._request(
            "POST",
            "/api/rag/query",
            json={"text": text, "language": language, "session_id": session_id},
            timeout=90.0,
        )

    def translate(self, text: str, target_language: str = "en", source_language: Optional[str] = None) -> dict:
        return self._request(
            "POST",
            "/api/nlp/translate",
            json={
                "text": text,
                "target_language": target_language,
                "source_language": source_language,
            },
        )

    def intent_entities(self, text: str) -> dict:
        return self._request("POST", "/api/nlp/intent-entities", json={"text": text})

    # ------------------------------------------------------------------- reviews
    def flagged_reviews(self, limit: int = 50) -> list[dict]:
        return self._request("GET", "/api/rag/flagged-reviews", params={"limit": limit})

    # ----------------------------------------------------------------- live data
    def mandi_prices(
        self,
        commodity: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if commodity:
            params["commodity"] = commodity
        if state:
            params["state"] = state
        return self._request("GET", "/api/live-data/mandi-prices", params=params)

    def weather(
        self,
        district: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> dict:
        params: dict[str, Any] = {}
        if district:
            params["district"] = district
        if latitude is not None:
            params["latitude"] = latitude
        if longitude is not None:
            params["longitude"] = longitude
        return self._request("GET", "/api/live-data/weather", params=params)

    def scheme_eligibility(self, landholding_acres: float, crops: str, state: str) -> list[dict]:
        return self._request(
            "GET",
            "/api/live-data/scheme-eligibility",
            params={
                "landholding_acres": landholding_acres,
                "crops": crops,
                "state": state,
            },
        )

    # ------------------------------------------------------------------ sessions
    def get_session(self, session_id: str) -> dict:
        return self._request("GET", f"/api/sessions/{session_id}")

    def update_session(self, session_id: str, updates: dict) -> dict:
        return self._request("PATCH", f"/api/sessions/{session_id}", json=updates)

    # ----------------------------------------------------------------- ingestion
    def reindex(self) -> dict:
        return self._request("POST", "/api/ingestion/reindex", timeout=self.long_timeout)

    # -------------------------------------------------------------------- speech
    def synthesize_speech(self, text: str, target_language: str, speaker: str = "meera") -> dict:
        return self._request(
            "POST",
            "/api/speech/synthesize",
            json={"text": text, "target_language": target_language, "speaker": speaker},
            timeout=90.0,
        )
