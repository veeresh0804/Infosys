"use client";

import React, { useState } from "react";
import Link from "next/link";
import { ChatInterface } from "../../components/ChatInterface";
import { KnowledgeInspector } from "../../components/KnowledgeInspector";
import { LiveDataInspector } from "../../components/LiveDataInspector";
import { SessionStateInspector } from "../../components/SessionStateInspector";
import { QueryResponse } from "../../lib/api";

export default function DevPage() {
  const [sessionId, setSessionId] = useState("farmer-session-1");
  const [selectedLanguage, setSelectedLanguage] = useState("hi");
  const [lastResponse, setLastResponse] = useState<QueryResponse | null>(null);

  return (
    <main className="app-container">
      <header className="app-header">
        <div>
          <div className="brand-title">
            🛠️ KisanSahayak Developer & Extension Dashboard <span className="brand-badge">Milestone 1 & 2 Verification</span>
          </div>
          <p style={{ color: "#9ca3af", fontSize: "13px", marginTop: "4px" }}>
            Telemetry, Vector DB chunks, intent/entity inspection, and human review queue.
          </p>
        </div>
        <Link href="/" className="btn-primary" style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "6px" }}>
          🌱 Open Farmer Voice View
        </Link>
      </header>

      {lastResponse?.is_fallback && (
        <div style={{
          background: "rgba(245, 158, 11, 0.15)",
          border: "1px solid #f59e0b",
          color: "#fcd34d",
          padding: "10px 16px",
          borderRadius: "8px",
          marginBottom: "16px",
          fontSize: "13px"
        }}>
          ⚠️ <strong>Developer Notice:</strong> This response utilized <em>fallback / mock provider data</em> (e.g. mock APMC data or offline synthesis).
        </div>
      )}

      <div className="app-layout">
        {/* Left Column: Chat with full Telemetry Badges */}
        <section>
          <ChatInterface
            sessionId={sessionId}
            selectedLanguage={selectedLanguage}
            onLanguageChange={setSelectedLanguage}
            onQueryComplete={(res) => setLastResponse(res)}
          />
        </section>

        {/* Right Column: Telemetry & Verification Inspectors */}
        <aside>
          <KnowledgeInspector
            chunks={lastResponse?.retrieved_chunks || []}
          />

          <LiveDataInspector
            liveData={lastResponse?.live_data}
          />

          <SessionStateInspector
            sessionId={sessionId}
            onSessionUpdated={(updated) => {
              if (updated.preferred_language) {
                setSelectedLanguage(updated.preferred_language);
              }
            }}
          />
        </aside>
      </div>
    </main>
  );
}
