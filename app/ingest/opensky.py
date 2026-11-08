"""OpenSky Network flight ingest (OAuth2 client credentials).

Uses GET /api/flights/aircraft for each tracked aircraft. OpenSky builds flight records
in a nightly batch, so flights from the current day may not show up until the next day.
Requests are split into short intervals because the endpoint limits the interval length.
"""
import time
from datetime import datetime, timedelta

import httpx

from .. import config, sample_data

TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
API = "https://opensky-network.org/api"
TOKEN_REFRESH_MARGIN = 30
CHUNK_DAYS = 2


class TokenManager:
    """Keeps a valid bearer token and refreshes it shortly before it expires."""

    def __init__(self, client_id: str, client_secret: str, http: httpx.Client):
        self.client_id = client_id
        self.client_secret = client_secret
        self.http = http
        self.token = None
        self.expires_at = None

    def get_token(self) -> str:
        if self.token and self.expires_at and datetime.now() < self.expires_at:
            return self.token
        r = self.http.post(TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        })
        r.raise_for_status()
        data = r.json()
        self.token = data["access_token"]
        self.expires_at = datetime.now() + timedelta(seconds=data.get("expires_in", 1800) - TOKEN_REFRESH_MARGIN)
        return self.token

    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.get_token()}"}


def fetch_aircraft_flights(http, tokens, icao24: str, begin: int, end: int) -> list[dict]:
    out = []
    t = begin
    while t < end:
        t2 = min(t + CHUNK_DAYS * 86400, end)
        r = http.get(f"{API}/flights/aircraft", params={"icao24": icao24, "begin": t, "end": t2},
                     headers=tokens.headers())
        if r.status_code == 404:  # OpenSky returns 404 when there are no flights
            pass
        elif r.status_code == 429:
            raise RuntimeError("OpenSky rate limit or daily credit limit reached; try again later")
        else:
            r.raise_for_status()
            out.extend(r.json() or [])
        t = t2
    return out


def _insert(conn, rows) -> int:
    n = 0
    for icao, cs, origin, dest, dep, arr, src in rows:
        cur = conn.execute(
            """INSERT OR IGNORE INTO flights(icao24, callsign, origin, dest, dep_ts, arr_ts, source)
               VALUES (?,?,?,?,?,?,?)""", (icao, cs, origin, dest, dep, arr, src))
        n += cur.rowcount
    return n


def ingest(conn, use_sample: bool, lookback_days: int = 30) -> dict:
    rows = conn.execute("SELECT icao24, is_sample FROM aircraft").fetchall()
    sample_ac = {r["icao24"] for r in rows if r["is_sample"]}
    tracked = [r["icao24"] for r in rows if not r["is_sample"]]
    report = {"mode": "sample", "inserted": 0, "aircraft": len(rows), "errors": []}
    if sample_ac:  # fictional aircraft always get fictional flights
        report["inserted"] += _insert(conn, [f for f in sample_data.flights(sample_data.now_ts()) if f[0] in sample_ac])
    if use_sample or not tracked:
        return report
    if not config.opensky_configured():
        report["errors"].append("OpenSky credentials missing; real aircraft have no flights")
        return report

    end = int(time.time())
    begin = end - lookback_days * 86400
    inserted, errors = 0, []
    with httpx.Client(timeout=30) as http:
        tokens = TokenManager(config.OPENSKY_CLIENT_ID, config.OPENSKY_CLIENT_SECRET, http)
        for icao in tracked:
            try:
                flights = fetch_aircraft_flights(http, tokens, icao, begin, end)
            except Exception as e:  # keep going for other aircraft
                errors.append(f"{icao}: {e}")
                if "rate limit" in str(e):
                    break
                continue
            rows = [(icao, (f.get("callsign") or "").strip(), f.get("estDepartureAirport"),
                     f.get("estArrivalAirport"), f.get("firstSeen"), f.get("lastSeen"), "opensky")
                    for f in flights]
            inserted += _insert(conn, rows)
    report["mode"] = "live" if not sample_ac else "live+sample"
    report["inserted"] += inserted
    report["errors"] = errors[:10]
    return report
