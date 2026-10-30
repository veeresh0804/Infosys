/**
 * Feature: Backend API Contracts
 * The UI depends on these payloads; drift here breaks the farmer journey.
 */
import { test, expect } from "@playwright/test";
import { API_BASE } from "../support/api";

test.describe("Feature: Backend API Contracts", () => {
  test("GET /api/health reports a healthy free-tier stack", async ({
    request
  }) => {
    const res = await request.get(`${API_BASE}/api/health`);
    expect(res.status()).toBe(200);

    const body = await res.json();
    expect(body.status).toBe("healthy");
    expect(body.active_engines).toBeTruthy();
    expect(body.active_engines.vector_store).toContain("chunks");
  });

  test("GET /api/live-data/mandi-prices returns numeric APMC rows", async ({
    request
  }) => {
    const res = await request.get(
      `${API_BASE}/api/live-data/mandi-prices?commodity=Tomato&state=Karnataka`
    );
    expect(res.status()).toBe(200);

    const rows = await res.json();
    expect(Array.isArray(rows)).toBeTruthy();
    expect(rows.length).toBeGreaterThan(0);

    const row = rows[0];
    expect(row.commodity).toBeTruthy();
    expect(typeof row.modal_price).toBe("number");
    expect(row.modal_price).toBeGreaterThan(0);
    expect(row.min_price).toBeLessThanOrEqual(row.modal_price);
    expect(row.modal_price).toBeLessThanOrEqual(row.max_price);
    expect(row.source, "sample vs live data must be labelled").toBeTruthy();
  });

  test("GET /api/live-data/weather returns a spoken advisory", async ({
    request
  }) => {
    const res = await request.get(
      `${API_BASE}/api/live-data/weather?district=Bengaluru+Rural`
    );
    expect(res.status()).toBe(200);

    const body = await res.json();
    expect(typeof body.temperature).toBe("number");
    expect(typeof body.humidity).toBe("number");
    expect(body.advisory.length).toBeGreaterThan(10);
    expect(body.source).toBeTruthy();
  });

  test("GET /api/live-data/scheme-eligibility explains PM-KISAN status", async ({
    request
  }) => {
    const res = await request.get(
      `${API_BASE}/api/live-data/scheme-eligibility?landholding_acres=2.5&crops=Tomato,Paddy`
    );
    expect(res.status()).toBe(200);

    const schemes = await res.json();
    expect(Array.isArray(schemes)).toBeTruthy();
    expect(schemes.length).toBeGreaterThan(0);

    const pmKisan = schemes.find(
      (s: any) =>
        s.scheme_id === "scheme-pm-kisan-01" ||
        String(s.scheme_name).includes("PM-KISAN")
    );
    expect(pmKisan, "PM-KISAN must always be evaluated").toBeTruthy();
    expect(typeof pmKisan.is_eligible).toBe("boolean");
    expect(pmKisan.reason.length).toBeGreaterThan(0);
    expect(pmKisan.benefits.length).toBeGreaterThan(0);
    expect(pmKisan.portal_url).toMatch(/^https:\/\//);
    // The full free-tier scheme set should be evaluated in one call
    expect(schemes.length).toBeGreaterThanOrEqual(4);
  });

  test("POST /api/rag/query answers a Hindi question end-to-end", async ({
    request
  }) => {
    test.setTimeout(120_000);

    const sessionId = `e2e-contract-${Date.now()}`;
    const res = await request.post(`${API_BASE}/api/rag/query`, {
      data: {
        session_id: sessionId,
        text: "पत्ती मोड़ रोग का इलाज क्या है?",
        language: "hi"
      }
    });

    expect(res.status()).toBe(200);
    const body = await res.json();

    expect(body.session_id).toBe(sessionId);
    expect(body.detected_language).toBeTruthy();
    expect(body.intent).toBeTruthy();
    expect(body.sub_agent).toBeTruthy();
    expect(body.answer_translated.length).toBeGreaterThan(10);
    expect(typeof body.confidence_score).toBe("number");
    expect(body.confidence_score).toBeGreaterThanOrEqual(0);
    expect(body.confidence_score).toBeLessThanOrEqual(1);
    // Honest labelling contract
    expect(body).toHaveProperty("is_fallback");
    expect(body).toHaveProperty("engine_used");
  });

  test("POST /api/rag/query persists the exchange into the session", async ({
    request
  }) => {
    test.setTimeout(120_000);

    const sessionId = `e2e-history-${Date.now()}`;
    const ask = await request.post(`${API_BASE}/api/rag/query`, {
      data: { session_id: sessionId, text: "What is the price of tomato?", language: "en" }
    });
    expect(ask.status()).toBe(200);

    const res = await request.get(`${API_BASE}/api/sessions/${sessionId}`);
    expect(res.status()).toBe(200);

    const session = await res.json();
    expect(session.session_id).toBe(sessionId);
    expect(Array.isArray(session.history)).toBeTruthy();
    expect(
      session.history.length,
      "the answered query must be stored in history"
    ).toBeGreaterThan(0);
  });
});
