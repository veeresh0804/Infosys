# 🌾 KisanSahayak Extension Dashboard (Streamlit)

A human-in-the-loop console for agricultural extension workers built on top of the
KisanSahayak FastAPI backend. Extension staff can ask multilingual questions, inspect
RAG telemetry, review low-confidence flags, browse live AGMARKNET/weather/scheme data,
re-index the knowledge base, and inspect or edit farmer session state. The dashboard is
a thin REST client: it never opens SQLite or the vector store directly.

---

## Prerequisites

- **Python 3.12** with the backend virtual environment at `backend\venv`.
- **Backend running** from `C:\Users\manoh\Desktop\Infosys`:
  ```powershell
  cd C:\Users\manoh\Desktop\Infosys
  backend\venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8000
  ```
- The **same `backend\.env`** as the API. The dashboard adds no secrets of its own.

---

## Install & run

From the project root (`C:\Users\manoh\Desktop\Infosys`):

```powershell
cd dashboard
..\backend\venv\Scripts\python.exe -m pip install -r requirements.txt
..\backend\venv\Scripts\streamlit.exe run app.py
```

Run from the `dashboard` folder so `.streamlit/config.toml` is picked up. The
default URL is **http://localhost:8501**. Keep the backend terminal running.

---

## Configuration

Use the sidebar before interacting with the tabs:

- **Backend API URL** — defaults to `http://127.0.0.1:8000`; change it to target
  another deployment.
- **Answer language** — Hindi, Kannada, or English for both typed and synthesized answers.
- **Session ID** — identifies the farmer conversation. Reusing the same ID shares
  history and profile context with the farmer voice UI.

The dashboard works with mock providers when backend API keys are absent. Live-data
endpoints may return clearly-labelled sample sources (for example APMC mandi prices)
until government API keys are configured.

---

## Feature tour

| Tab | What it does |
|---|---|
| **Ask** | Send a multilingual question and inspect the routed sub-agent, intent, entities, confidence, retrieved chunks, and live-data snapshot. Play the synthesized answer. |
| **Review queue** | Browse queries the backend flagged below its confidence threshold and inspect the question, answer, agent, and flag reason. |
| **Live data** | Query AGMARKNET APMC mandi prices, Open-Meteo weather and advisories, and rule-based government scheme eligibility. |
| **Knowledge base** | Trigger a knowledge-base re-index and review the ingestion result; re-indexing re-chunks and re-embeds the curated documents. |
| **Farmer session** | Inspect and edit the SQLite-backed profile (language, state, district, landholding, crops), read conversation history, and open the raw session JSON. |

---

## Architecture

```
dashboard/
├── app.py                     # Shell: sidebar, KPIs, Ask and Review queue tabs
├── api_client.py              # Typed REST client (AgriApiClient, BackendError)
├── ui.py                      # Theme CSS, pills, formatters, shared helpers
├── views/
│   ├── live_data.py           # Mandi, weather, and scheme panels
│   ├── knowledge_base.py      # Re-index control and ingestion results
│   └── session_view.py        # Farmer profile, conversation history, raw JSON
├── .streamlit/config.toml     # Green agricultural theme and server defaults
├── requirements.txt           # streamlit, requests, pandas
└── README.md
```

Every request flows through `api_client.py` to the public FastAPI endpoints documented
in the root `README.md`. There is no direct database or vector-store access from
Streamlit, so the same dashboard can point at a remote backend.

---

## Troubleshooting

| Symptom | What to do |
|---|---|
| "Cannot reach the backend" or the session tab shows a load error | Start the backend with the command in **Prerequisites** and confirm http://127.0.0.1:8000/docs opens. Check the sidebar URL. |
| Port `8501` is already in use | Run `..\backend\venv\Scripts\streamlit.exe run app.py --server.port 8502` and open http://localhost:8502. |
| Re-index seems to hang | Re-indexing re-chunks and re-embeds the whole knowledge base; it is intentionally long-running, so wait for it to finish. |
| Audio plays as a generic WAV | Synthesis uses a clearly-labelled mock when `SARVAM_API_KEY` is missing or exhausted; set the key in `backend\.env` and restart the API. |
| A profile edit is not visible on another tab yet | Session reads are cached for 45 seconds; press **🔄 Reload session** or rerun after the TTL. |
| `streamlit.exe` is not found | Install dependencies with the command in **Install & run** using the backend virtual environment. |
