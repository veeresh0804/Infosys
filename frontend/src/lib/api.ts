const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface EntityItem {
  text: string;
  label: string;
  confidence: number;
}

export interface RetrievedChunk {
  id: string;
  content: string;
  source: string;
  similarity_score: number;
  metadata: Record<string, any>;
}

export interface QueryResponse {
  session_id: string;
  original_query: string;
  detected_language: string;
  canonical_query: string;
  intent: string;
  intent_confidence: number;
  entities: EntityItem[];
  sub_agent: string;
  answer_canonical: string;
  answer_translated: string;
  confidence_score: number;
  is_low_confidence: boolean;
  flag_reason?: string;
  is_fallback?: boolean;
  short_answer_canonical?: string;
  short_answer_translated?: string;
  retrieved_chunks: RetrievedChunk[];
  live_data?: any;
  audio_base64?: string;
}

export interface SessionState {
  session_id: string;
  user_id: string;
  preferred_language: string;
  state: string;
  district: string;
  landholding_acres: number;
  crops_grown: string[];
  history: any[];
}

export interface MandiPriceItem {
  commodity: string;
  state: string;
  district: string;
  market: string;
  min_price: number;
  max_price: number;
  modal_price: number;
  arrival_date: string;
  source: string;
}

export interface WeatherData {
  location: string;
  temperature: number;
  humidity: number;
  precipitation_prob: number;
  wind_speed: number;
  forecast_summary: string;
  advisory: string;
  source: string;
}

export interface SchemeItem {
  scheme_id: string;
  scheme_name: string;
  is_eligible: boolean;
  reason: string;
  benefits: string;
  portal_url: string;
}

export const api = {
  async queryPipeline(params: {
    sessionId?: string;
    text?: string;
    language?: string;
    audioBase64?: string;
  }): Promise<QueryResponse> {
    const res = await fetch(`${API_BASE}/api/rag/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: params.sessionId,
        text: params.text,
        language: params.language,
        audio_base64: params.audioBase64
      })
    });
    if (!res.ok) {
      const err = await res.text();
      throw new Error(`Query failed: ${res.status} - ${err}`);
    }
    return res.json();
  },

  async synthesizeSpeech(text: string, targetLanguage: string): Promise<string> {
    const res = await fetch(`${API_BASE}/api/speech/synthesize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        target_language: targetLanguage,
        speaker: "meera"
      })
    });
    if (!res.ok) throw new Error("TTS failed");
    const data = await res.json();
    return data.audio_base64;
  },

  async getSession(sessionId: string): Promise<SessionState> {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`);
    if (!res.ok) throw new Error("Failed to load session");
    return res.json();
  },

  async updateSession(sessionId: string, updates: Partial<SessionState>): Promise<SessionState> {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates)
    });
    if (!res.ok) throw new Error("Failed to update session");
    return res.json();
  },

  async getMandiPrices(commodity?: string, state?: string): Promise<MandiPriceItem[]> {
    const params = new URLSearchParams();
    if (commodity) params.set("commodity", commodity);
    if (state) params.set("state", state);
    const res = await fetch(`${API_BASE}/api/live-data/mandi-prices?${params.toString()}`);
    if (!res.ok) throw new Error("Failed to load mandi prices");
    return res.json();
  },

  async getWeather(district?: string): Promise<WeatherData> {
    const params = new URLSearchParams();
    if (district) params.set("district", district);
    const res = await fetch(`${API_BASE}/api/live-data/weather?${params.toString()}`);
    if (!res.ok) throw new Error("Failed to load weather");
    return res.json();
  },

  async checkSchemes(landholding?: number, crops?: string, state?: string): Promise<SchemeItem[]> {
    const params = new URLSearchParams();
    if (landholding !== undefined) params.set("landholding_acres", landholding.toString());
    if (crops) params.set("crops", crops);
    if (state) params.set("state", state);
    const res = await fetch(`${API_BASE}/api/live-data/scheme-eligibility?${params.toString()}`);
    if (!res.ok) throw new Error("Failed to check schemes");
    return res.json();
  },

  async reindexKB(): Promise<any> {
    const res = await fetch(`${API_BASE}/api/ingestion/reindex`, {
      method: "POST"
    });
    if (!res.ok) throw new Error("Failed to reindex knowledge base");
    return res.json();
  },

  async getFlaggedReviews(): Promise<any[]> {
    const res = await fetch(`${API_BASE}/api/rag/flagged-reviews`);
    if (!res.ok) throw new Error("Failed to load flagged reviews");
    return res.json();
  }
};
