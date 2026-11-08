# JetDeal Signals

Tracks business jets owned by companies, links their trips to other companies' HQ cities,
and matches those trips to M&A deals and SEC filings. Built for investing research.

> **Informational only. Not investment advice.** Flight data does not tell you who was on board or why.

## Run

```bash
cd jetdeal
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # add your keys (optional; sample data is used otherwise)
.venv/bin/uvicorn app.main:app --port 8765
```
Open http://localhost:8765. On first start the database fills itself (sample data for any source without keys).

Refresh data: the **Refresh data** button, or `python -m app.pipeline` (`--sample --reset` for fictional data, `--days 30` for OpenSky lookback).

## Data sources

| Source | What | Setup |
|---|---|---|
| OpenSky Network | Flights per aircraft (`/api/flights/aircraft`) | `OPENSKY_CLIENT_ID`, `OPENSKY_CLIENT_SECRET` (OAuth2 client credentials) |
| FAA Releasable Aircraft DB | Tail number → ICAO24 → registered owner | Download `ReleasableAircraft.zip`, unzip, set `FAA_REGISTRY_DIR` |
| SEC EDGAR submissions | 8-K (items 1.01/2.01/5.01), SC 13D, SC TO-T, S-4, 425, DEFM14A | `SEC_USER_AGENT` (app name + contact email), `cik` in companies.csv |

Add your companies to `data/companies.csv`: ticker, CIK, HQ airports, and `owner_aliases` (the name on the FAA registry, often an LLC, e.g. `XYZ AVIATION LLC`).
Add more airports in `app/airports.py`.

## Privacy guardrails
- Aircraft registered to individuals or co-owners are dropped. Only organizations are kept.
- Only aircraft that match a company in your list are tracked.
- `data/blocklist.csv`: FAA LADD entries and opt-out requests. Dropped at ingest, purged every run.
- PIA aircraft never match the registry, so they are never linked to an owner.

## Signal score (0–100)
Frequency above baseline (40) + novelty vs. prior 180 days (25) + recency (15) + day trips under 12 h (10) + watchlist (10); leisure airports ×0.3.
Status: **confirmed** (a deal between both companies followed; the backtest shows days of warning), **corroborated** (a single-company filing or rumor followed), **open** (alert if score ≥ `ALERT_SCORE_THRESHOLD`).

## Known limits / next steps
- OpenSky builds flight records nightly, so today's flights appear the next day. The free tier has daily credit limits.
- No news/rumor feed yet (only EDGAR + sample rumors). Add a news API for rumors.
- Two-party deal links come only from sample data; EDGAR filings are single-company. Parsing counterparties from 8-K text would enable "confirmed" on live data.
- No scheduled refresh yet (run the pipeline with cron).

Tests: `.venv/bin/python -m pytest -q`
