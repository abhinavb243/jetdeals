"""Link flights to companies and deals, and score the links.

A *signal* is a pair (visitor company A, host company B): A's aircraft land at an airport
that serves B's HQ city. The score (0-100) as of a given time `asof` combines:

  frequency  (0-40)  landings in B's city in the last 30 days above A's baseline rate (6+ extra = full)
  novelty    (0-25)  how unusual this is compared to A's baseline (days 31-210 before asof)
  recency    (0-15)  how recent the last landing is
  day trips  (0-10)  share of visits with a short stay (< 12 h), typical for meetings
  watchlist  (0-10)  A or B is on the watchlist
Leisure airports (Aspen, Sun Valley, Palm Beach) are multiplied by 0.3.

Status:
  confirmed    a deal involving both A and B came within 120 days after the first visit
  corroborated a single-party M&A filing/rumor for A or B came after the visits started
  open         no deal found yet  -> alert if score >= ALERT_SCORE_THRESHOLD
The score is computed both now and at the deal date (backtest), which shows how much
warning the flights gave.

These signals are informational only. They are not investment advice.
"""
import time
from collections import defaultdict

from . import airports, config

DAY = 86400
RECENT_DAYS = 30
BASELINE_DAYS = 180
DEAL_LOOKAHEAD_DAYS = 120


def _company_cities(conn):
    """Map airport ICAO -> list of company ids headquartered near it, and company -> home airports."""
    by_airport = defaultdict(list)
    home = {}
    for c in conn.execute("SELECT id, hq_airports, hq_city FROM companies"):
        apts = [a for a in (c["hq_airports"] or "").split(",") if a]
        home[c["id"]] = set(apts)
        # every airport in the same metro as any HQ airport counts too
        cities = {airports.city(a) for a in apts} | {c["hq_city"]}
        for icao, (_n, metro) in airports.AIRPORTS.items():
            if metro in cities:
                by_airport[icao].append(c["id"])
        for a in apts:
            if c["id"] not in by_airport[a]:
                by_airport[a].append(c["id"])
    return by_airport, home


def _landings(conn):
    """Yield landings with the stay length (hours) until the next departure of the same aircraft."""
    rows = conn.execute(
        """SELECT f.icao24, f.dest, f.arr_ts, f.dep_ts, a.company_id, a.tail
           FROM flights f JOIN aircraft a ON a.icao24 = f.icao24
           WHERE f.dest IS NOT NULL ORDER BY f.icao24, f.dep_ts""").fetchall()
    out = []
    for i, r in enumerate(rows):
        nxt = rows[i + 1] if i + 1 < len(rows) and rows[i + 1]["icao24"] == r["icao24"] else None
        stay = (nxt["dep_ts"] - r["arr_ts"]) / 3600 if nxt and r["arr_ts"] else None
        out.append({**dict(r), "stay_h": stay})
    return out


def _deals(conn):
    return [dict(d) for d in conn.execute("SELECT * FROM deals ORDER BY ts")]


def score_pair(visits, baseline_count, asof, watched):
    """visits: landings in B's city within the last RECENT_DAYS before asof."""
    n = len(visits)
    if n == 0:
        return 0.0, {}
    baseline_per_30 = baseline_count / (BASELINE_DAYS / RECENT_DAYS)
    excess = max(0.0, n - baseline_per_30)  # visits above A's normal rate to this city
    freq = 40 * min(excess, 6) / 6
    novelty = 25 * max(0.0, 1 - baseline_per_30 / n)
    last = max(v["arr_ts"] for v in visits)
    recency = 15 * max(0.0, 1 - (asof - last) / (RECENT_DAYS * DAY))
    short = [v for v in visits if v["stay_h"] is not None and v["stay_h"] < 12]
    daytrip = 10 * len(short) / n
    watch = 10 if watched else 0
    total = freq + novelty + recency + daytrip + watch
    leisure = all(v["dest"] in airports.LEISURE for v in visits)
    if leisure:
        total *= 0.3
    parts = {"frequency": round(freq, 1), "novelty": round(novelty, 1), "recency": round(recency, 1),
             "day_trips": round(daytrip, 1), "watchlist": watch, "leisure_penalty": leisure}
    return round(min(total, 100), 1), parts


def compute(conn, asof: int | None = None) -> list[dict]:
    asof = asof or int(time.time())
    by_airport, home = _company_cities(conn)
    companies = {c["id"]: dict(c) for c in conn.execute("SELECT * FROM companies")}
    landings = _landings(conn)
    deals = _deals(conn)

    # Group landings by (A, B)
    pairs = defaultdict(list)
    for l in landings:
        a = l["company_id"]
        if l["dest"] in home.get(a, set()):
            continue  # flying home
        for b in by_airport.get(l["dest"], []):
            if b != a and l["dest"] not in home.get(a, set()):
                pairs[(a, b)].append(l)

    results = []
    for (a, b), ls in pairs.items():
        watched = bool(companies[a]["watch"] or companies[b]["watch"])

        def score_at(t):
            recent = [l for l in ls if t - RECENT_DAYS * DAY <= l["arr_ts"] <= t]
            base = [l for l in ls if t - (RECENT_DAYS + BASELINE_DAYS) * DAY <= l["arr_ts"] < t - RECENT_DAYS * DAY]
            return score_pair(recent, len(base), t, watched), recent

        (score_now, parts), recent_now = score_at(asof)
        first_visit = min(l["arr_ts"] for l in ls)

        both = [d for d in deals if {d["acquirer_id"], d["target_id"]} == {a, b} and d["ts"] >= first_visit]
        # single-party items (one side unknown): an EDGAR filing or a rumor about A or B alone
        single = [d for d in deals if None in (d["acquirer_id"], d["target_id"])
                  and {d["acquirer_id"], d["target_id"]} & {a, b}
                  and first_visit <= d["ts"] <= asof + DAY]
        status, deal, backtest = "open", None, None
        if both:
            deal = both[0]
            # visits that came before the deal, inside the lookahead window
            pre = [l for l in ls if deal["ts"] - DEAL_LOOKAHEAD_DAYS * DAY <= l["arr_ts"] < deal["ts"]]
            if pre:
                status = "confirmed"
                # best score reached in the run-up, and how early it crossed the threshold
                best, lead = 0.0, None
                for day in range(DEAL_LOOKAHEAD_DAYS, 0, -1):
                    (s, _p), _r = score_at(deal["ts"] - day * DAY)
                    best = max(best, s)
                    if lead is None and s >= config.ALERT_SCORE_THRESHOLD:
                        lead = day
                backtest = {"peak_score": best, "lead_days": lead, "pre_deal_visits": len(pre)}
        elif single:
            status, deal = "corroborated", single[-1]

        if score_now == 0 and status == "open":
            continue
        results.append({
            "visitor_id": a, "visitor": companies[a]["name"], "visitor_ticker": companies[a]["ticker"],
            "host_id": b, "host": companies[b]["name"], "host_ticker": companies[b]["ticker"],
            "host_city": companies[b]["hq_city"],
            "score": score_now, "parts": parts,
            "visits_30d": len(recent_now), "visits_total": len(ls),
            "last_visit": max(l["arr_ts"] for l in ls),
            "tails": sorted({l["tail"] for l in ls}),
            "status": status, "deal": deal, "backtest": backtest,
            "alert": status == "open" and score_now >= config.ALERT_SCORE_THRESHOLD,
            "is_sample": bool(companies[a]["is_sample"]),
        })
    results.sort(key=lambda r: (r["alert"], r["score"]), reverse=True)
    return results


def timeline(conn, a: int, b: int) -> dict:
    by_airport, home = _company_cities(conn)
    host_airports = {icao for icao, ids in by_airport.items() if b in ids}
    flights = [dict(r) for r in conn.execute(
        f"""SELECT f.*, a.tail FROM flights f JOIN aircraft a ON a.icao24=f.icao24
            WHERE a.company_id=? AND f.dest IN ({",".join("?" * len(host_airports))})
            ORDER BY f.arr_ts""", (a, *host_airports))] if host_airports else []
    all_flights = conn.execute(
        "SELECT COUNT(*) FROM flights f JOIN aircraft a ON a.icao24=f.icao24 WHERE a.company_id=?", (a,)
    ).fetchone()[0]
    deals = [dict(d) for d in conn.execute(
        "SELECT * FROM deals WHERE acquirer_id IN (?,?) OR target_id IN (?,?) ORDER BY ts", (a, b, a, b))]
    return {"flights": flights, "deals": deals, "total_flights_visitor": all_flights}
