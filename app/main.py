"""FastAPI server: JSON API + static dashboard.  Run:  uvicorn app.main:app --reload"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import airports, config, db, pipeline, signals

app = FastAPI(title="JetDeal Signals")
STATIC = config.ROOT / "static"


@app.on_event("startup")
def _startup():
    db.init()
    with db.session() as conn:
        empty = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 0
    if empty:
        pipeline.run(use_sample=False)  # each source falls back to sample data on its own


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
def status():
    with db.session() as conn:
        runs = [dict(r) for r in conn.execute(
            "SELECT * FROM ingest_runs WHERE id IN (SELECT MAX(id) FROM ingest_runs GROUP BY source)")]
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("companies", "aircraft", "flights", "deals")}
    return {
        "sources": {
            "opensky": {"configured": config.opensky_configured()},
            "faa": {"configured": config.faa_configured()},
            "edgar": {"configured": config.edgar_configured()},
        },
        "runs": runs, "counts": counts, "alert_threshold": config.ALERT_SCORE_THRESHOLD,
    }


@app.get("/api/signals")
def get_signals():
    with db.session() as conn:
        return signals.compute(conn)


@app.get("/api/timeline")
def get_timeline(visitor: int, host: int):
    with db.session() as conn:
        t = signals.timeline(conn, visitor, host)
    for f in t["flights"]:
        f["dest_name"] = airports.name(f["dest"])
        f["origin_name"] = airports.name(f["origin"]) if f["origin"] else None
    return t


@app.get("/api/companies")
def get_companies():
    with db.session() as conn:
        rows = conn.execute(
            """SELECT c.*, (SELECT COUNT(*) FROM aircraft a WHERE a.company_id=c.id) AS aircraft,
                      (SELECT COUNT(*) FROM deals d WHERE d.acquirer_id=c.id OR d.target_id=c.id) AS deals
               FROM companies c ORDER BY c.watch DESC, c.name""").fetchall()
        return [dict(r) for r in rows]


class Watch(BaseModel):
    watch: bool


@app.post("/api/companies/{cid}/watch")
def set_watch(cid: int, body: Watch):
    with db.session() as conn:
        cur = conn.execute("UPDATE companies SET watch=? WHERE id=?", (int(body.watch), cid))
        if cur.rowcount == 0:
            raise HTTPException(404)
    return {"ok": True}


@app.get("/api/flights")
def get_flights(limit: int = 300):
    with db.session() as conn:
        rows = conn.execute(
            """SELECT f.*, a.tail, a.model, c.name AS company FROM flights f
               JOIN aircraft a ON a.icao24=f.icao24 LEFT JOIN companies c ON c.id=a.company_id
               ORDER BY f.dep_ts DESC LIMIT ?""", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["origin_city"] = airports.city(d["origin"]) if d["origin"] else None
        d["dest_city"] = airports.city(d["dest"]) if d["dest"] else None
        out.append(d)
    return out


@app.get("/api/aircraft")
def get_aircraft():
    with db.session() as conn:
        return [dict(r) for r in conn.execute(
            """SELECT a.*, c.name AS company FROM aircraft a LEFT JOIN companies c ON c.id=a.company_id
               ORDER BY c.name""")]


@app.get("/api/deals")
def get_deals():
    with db.session() as conn:
        return [dict(r) for r in conn.execute(
            """SELECT d.*, ca.name AS acquirer, ct.name AS target FROM deals d
               LEFT JOIN companies ca ON ca.id=d.acquirer_id LEFT JOIN companies ct ON ct.id=d.target_id
               ORDER BY d.ts DESC""")]


class IngestReq(BaseModel):
    sample: bool = False
    reset: bool = False
    days: int = 30


@app.post("/api/ingest")
def ingest(req: IngestReq):
    return pipeline.run(req.sample, req.reset, req.days)


app.mount("/static", StaticFiles(directory=STATIC), name="static")
