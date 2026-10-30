# Playwright E2E suite (KisanSahayak AI)

End-to-end coverage for the farmer voice UI (`frontend/`, port 3000) and the
FastAPI pipeline (`backend/`, port 8000).

## Run

```bash
# from repo root
cd e2e
npm install
npx playwright install chromium   # first time only

npm test                          # headless
npm run test:headed               # watch the browser
npm run test:debug                # Playwright Inspector
npm run report                    # open the HTML report
```

The config starts (or reuses) both servers automatically via `webServer`.

## Layout

```
e2e/
├── playwright.config.ts   # baseURL, artifacts, projects, webServer
├── pages/FarmerPage.ts    # Page Object Model for the farmer UI
├── tests/
│   ├── smoke.spec.ts          # landing, session bootstrap, form guard
│   ├── language.spec.ts       # hi / kn / en switch + persistence
│   ├── query.spec.ts          # typed ask, mandi & weather tiles, expansion
│   ├── error-handling.spec.ts # network / HTTP 500 / mic denial / recovery
│   ├── navigation.spec.ts     # farmer UI <-> developer dashboard
│   └── api-contract.spec.ts   # backend payload contracts
├── artifacts/             # screenshots taken by tests (and on failure)
├── test-results/          # traces, videos, failure screenshots, junit.xml
└── playwright-report/     # HTML report
```

## Artifacts

| Artifact | When | Where |
|---|---|---|
| Screenshots | explicit + on failure | `artifacts/*.png`, `test-results/*.png` |
| Video | on failure | `test-results/*.webm` |
| Trace | on failure | `test-results/*.zip` (`npx playwright show-trace <file>`) |
| JUnit XML | always | `test-results/junit.xml` |
| HTML report | always | `playwright-report/index.html` |

## Environment overrides

- `E2E_BASE_URL` – frontend URL (default `http://localhost:3000`)
- `E2E_API_URL` – backend URL (default `http://127.0.0.1:8000`)
- `CI=true` – 2 retries, 2 workers, fresh `webServer` instances
