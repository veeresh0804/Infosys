/** Absolute backend URL for tests that must bypass the Next.js frontend. */
export const API_BASE = process.env.E2E_API_URL || "http://127.0.0.1:8000";

/** Backend session endpoint (the UI's relative /api/... paths resolve to
 *  localhost:3000, which has no API routes - always call the API directly). */
export function sessionUrl(sessionId: string): string {
  return `${API_BASE}/api/sessions/${sessionId}`;
}
