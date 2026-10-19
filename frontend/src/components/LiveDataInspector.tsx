"use client";

import React, { useState } from "react";
import { api, MandiPriceItem, WeatherData, SchemeItem } from "../lib/api";

interface LiveDataInspectorProps {
  liveData?: any;
}

export const LiveDataInspector: React.FC<LiveDataInspectorProps> = ({ liveData }) => {
  const [activeTab, setActiveTab] = useState<"mandi" | "weather" | "schemes">("mandi");
  const [commodity, setCommodity] = useState("Tomato");
  const [district, setDistrict] = useState("Bengaluru Rural");
  const [mandiPrices, setMandiPrices] = useState<MandiPriceItem[] | null>(null);
  const [weather, setWeather] = useState<WeatherData | null>(null);
  const [schemes, setSchemes] = useState<SchemeItem[] | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchMandi = async () => {
    setLoading(true);
    try {
      const res = await api.getMandiPrices(commodity);
      setMandiPrices(res);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const fetchWeather = async () => {
    setLoading(true);
    try {
      const res = await api.getWeather(district);
      setWeather(res);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const fetchSchemes = async () => {
    setLoading(true);
    try {
      const res = await api.checkSchemes(2.0, commodity);
      setSchemes(res);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="inspector-card">
      <div className="inspector-header">
        <div>
          <h3>📡 Real-Time Agricultural Data Inspector</h3>
          <p className="inspector-subtitle">
            AGMARKNET Mandi rates, Open-Meteo weather forecasts, and Government Scheme eligibility.
          </p>
        </div>
      </div>

      <div className="tab-buttons">
        <button
          className={`tab-btn ${activeTab === "mandi" ? "active" : ""}`}
          onClick={() => setActiveTab("mandi")}
        >
          💰 Mandi Prices
        </button>
        <button
          className={`tab-btn ${activeTab === "weather" ? "active" : ""}`}
          onClick={() => setActiveTab("weather")}
        >
          🌦 Weather Forecast
        </button>
        <button
          className={`tab-btn ${activeTab === "schemes" ? "active" : ""}`}
          onClick={() => setActiveTab("schemes")}
        >
          📜 Scheme Eligibility
        </button>
      </div>

      {activeTab === "mandi" && (
        <div className="tab-content">
          <div className="inline-form">
            <input
              type="text"
              value={commodity}
              onChange={(e) => setCommodity(e.target.value)}
              placeholder="Crop (e.g. Tomato, Paddy, Wheat)"
              className="text-input"
            />
            <button onClick={fetchMandi} disabled={loading} className="btn-secondary">
              Fetch Mandi Prices
            </button>
          </div>

          {(mandiPrices || liveData?.mandi_prices) ? (
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Commodity</th>
                    <th>Market / State</th>
                    <th>Modal Price</th>
                    <th>Min / Max</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {(mandiPrices || liveData?.mandi_prices || []).map((m: any, idx: number) => (
                    <tr key={idx}>
                      <td><strong>{m.commodity}</strong></td>
                      <td>{m.market} ({m.state})</td>
                      <td><span className="price-tag">₹{m.modal_price}/Qtl</span></td>
                      <td>₹{m.min_price} - ₹{m.max_price}</td>
                      <td><small>{m.source}</small></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="empty-notice">Click Fetch to retrieve current AGMARKNET rates.</p>
          )}
        </div>
      )}

      {activeTab === "weather" && (
        <div className="tab-content">
          <div className="inline-form">
            <input
              type="text"
              value={district}
              onChange={(e) => setDistrict(e.target.value)}
              placeholder="District (e.g. Bengaluru, Mandya, Ludhiana)"
              className="text-input"
            />
            <button onClick={fetchWeather} disabled={loading} className="btn-secondary">
              Fetch Weather
            </button>
          </div>

          {(weather || liveData?.weather) ? (
            (() => {
              const w = weather || liveData?.weather;
              return (
                <div className="weather-card">
                  <h4>📍 {w.location} Forecast</h4>
                  <div className="weather-metrics">
                    <div className="metric">
                      <span className="metric-label">Temperature</span>
                      <span className="metric-val">{w.temperature}°C</span>
                    </div>
                    <div className="metric">
                      <span className="metric-label">Humidity</span>
                      <span className="metric-val">{w.humidity}%</span>
                    </div>
                    <div className="metric">
                      <span className="metric-label">Rain Probability</span>
                      <span className="metric-val">{w.precipitation_prob}%</span>
                    </div>
                    <div className="metric">
                      <span className="metric-label">Wind Speed</span>
                      <span className="metric-val">{w.wind_speed} km/h</span>
                    </div>
                  </div>
                  <div className="advisory-box">
                    <strong>🌾 Farm Advisory:</strong> {w.advisory}
                  </div>
                  <small style={{ color: "#888" }}>Source: {w.source}</small>
                </div>
              );
            })()
          ) : (
            <p className="empty-notice">Click Fetch to query live Open-Meteo agro-weather.</p>
          )}
        </div>
      )}

      {activeTab === "schemes" && (
        <div className="tab-content">
          <div className="inline-form">
            <button onClick={fetchSchemes} disabled={loading} className="btn-secondary">
              Evaluate Govt Schemes (2 Acres, {commodity})
            </button>
          </div>

          {(schemes || liveData?.schemes_evaluated) ? (
            <div className="schemes-list">
              {(schemes || liveData?.schemes_evaluated || []).map((s: any, idx: number) => (
                <div key={s.scheme_id || idx} className={`scheme-card ${s.is_eligible ? "eligible" : "ineligible"}`}>
                  <div className="scheme-title">
                    <span>{s.is_eligible ? "✅" : "❌"} {s.scheme_name}</span>
                    <a href={s.portal_url} target="_blank" rel="noreferrer" className="scheme-link">
                      Official Portal ↗
                    </a>
                  </div>
                  <p className="scheme-reason"><strong>Eligibility:</strong> {s.reason}</p>
                  <p className="scheme-benefit"><strong>Benefits:</strong> {s.benefits}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="empty-notice">Click to evaluate farmer eligibility for PM-KISAN, PMFBY, and KCC.</p>
          )}
        </div>
      )}
    </div>
  );
};
