"use client";

import React, { useState, useEffect } from "react";
import { api, SessionState } from "../lib/api";

interface SessionStateInspectorProps {
  sessionId: string;
  onSessionUpdated?: (updated: SessionState) => void;
}

export const SessionStateInspector: React.FC<SessionStateInspectorProps> = ({ sessionId, onSessionUpdated }) => {
  const [session, setSession] = useState<SessionState | null>(null);
  const [flaggedReviews, setFlaggedReviews] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [stateName, setStateName] = useState("Karnataka");
  const [district, setDistrict] = useState("Bengaluru Rural");
  const [acres, setAcres] = useState(2.5);
  const [cropsStr, setCropsStr] = useState("Tomato, Paddy");
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const s = await api.getSession(sessionId);
      setSession(s);
      setStateName(s.state || "Karnataka");
      setDistrict(s.district || "Bengaluru Rural");
      setAcres(s.landholding_acres || 2.5);
      setCropsStr((s.crops_grown || []).join(", "));

      const flagged = await api.getFlaggedReviews();
      setFlaggedReviews(flagged);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadData();
  }, [sessionId]);

  const handleSave = async () => {
    setLoading(true);
    setSaveMsg(null);
    try {
      const crops = cropsStr.split(",").map((c) => c.trim()).filter(Boolean);
      const updated = await api.updateSession(sessionId, {
        state: stateName,
        district: district,
        landholding_acres: Number(acres),
        crops_grown: crops
      });
      setSession(updated);
      setSaveMsg("Preferences saved!");
      if (onSessionUpdated) onSessionUpdated(updated);
    } catch (err: any) {
      setSaveMsg(`Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="inspector-card">
      <div className="inspector-header">
        <div>
          <h3>🧑‍🌾 Conversation Context & Session State</h3>
          <p className="inspector-subtitle">
            Farmer profile, multilingual preferences, and quality review queue.
          </p>
        </div>
        <button onClick={loadData} className="btn-secondary">
          Refresh
        </button>
      </div>

      {saveMsg && <div className="notice-banner">{saveMsg}</div>}

      <div className="session-grid">
        <div className="form-group">
          <label>Session ID:</label>
          <input type="text" value={sessionId} disabled className="text-input disabled" />
        </div>
        <div className="form-group">
          <label>Preferred Language:</label>
          <input type="text" value={session?.preferred_language || "hi"} disabled className="text-input disabled" />
        </div>
        <div className="form-group">
          <label>Farmer State:</label>
          <input
            type="text"
            value={stateName}
            onChange={(e) => setStateName(e.target.value)}
            className="text-input"
          />
        </div>
        <div className="form-group">
          <label>District:</label>
          <input
            type="text"
            value={district}
            onChange={(e) => setDistrict(e.target.value)}
            className="text-input"
          />
        </div>
        <div className="form-group">
          <label>Landholding (Acres):</label>
          <input
            type="number"
            step="0.5"
            value={acres}
            onChange={(e) => setAcres(parseFloat(e.target.value) || 0)}
            className="text-input"
          />
        </div>
        <div className="form-group">
          <label>Crops Grown (comma-separated):</label>
          <input
            type="text"
            value={cropsStr}
            onChange={(e) => setCropsStr(e.target.value)}
            className="text-input"
          />
        </div>
      </div>

      <div style={{ marginTop: "12px", display: "flex", gap: "10px" }}>
        <button onClick={handleSave} disabled={loading} className="btn-primary">
          {loading ? "Saving..." : "💾 Update Farmer Context"}
        </button>
      </div>

      <div className="flagged-section">
        <h4>
          🚩 Low-Confidence Review Queue ({flaggedReviews.length} items flagged for extension workers)
        </h4>
        {flaggedReviews.length > 0 ? (
          <div className="flagged-list">
            {flaggedReviews.slice(0, 5).map((f) => (
              <div key={f.id} className="flagged-item">
                <div className="flagged-meta">
                  <span className="badge badge-warning">Score: {(f.confidence_score * 100).toFixed(0)}%</span>
                  <span className="badge badge-source">{f.sub_agent}</span>
                  <small style={{ color: "#777" }}>{f.created_at ? new Date(f.created_at).toLocaleTimeString() : ""}</small>
                </div>
                <div style={{ marginTop: "4px" }}>
                  <strong>Query:</strong> {f.original_query} ({f.canonical_query})
                </div>
                <div style={{ color: "#d9534f", fontSize: "12px", marginTop: "2px" }}>
                  <strong>Reason:</strong> {f.flag_reason}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="empty-notice">No responses flagged below confidence threshold yet.</p>
        )}
      </div>
    </div>
  );
};
