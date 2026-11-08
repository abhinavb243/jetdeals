"""Run all ingesters in order.  Usage:  python -m app.pipeline [--sample] [--reset] [--days N]"""
import argparse
import json

from . import config, db, privacy
from .ingest import companies, edgar, faa, opensky


def run(use_sample: bool = False, reset: bool = False, lookback_days: int = 30) -> dict:
    if reset and config.DB_PATH.exists():
        config.DB_PATH.unlink()
    db.init()
    report = {}
    with db.session() as conn:
        aliases = companies.load(conn, use_sample)
        report["faa"] = faa.ingest(conn, aliases, use_sample)
        db.log_run(conn, "faa", report["faa"]["mode"], report["faa"]["kept"])
        report["purged_blocked"] = privacy.purge_blocked(conn)
        report["opensky"] = opensky.ingest(conn, use_sample, lookback_days)
        db.log_run(conn, "opensky", report["opensky"]["mode"], report["opensky"]["inserted"],
                   "; ".join(report["opensky"].get("errors", [])))
        report["edgar"] = edgar.ingest(conn, use_sample)
        db.log_run(conn, "edgar", report["edgar"]["mode"], report["edgar"]["inserted"],
                   "; ".join(report["edgar"].get("errors", [])))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sample", action="store_true", help="use fictional sample data for every source")
    p.add_argument("--reset", action="store_true", help="delete the database first")
    p.add_argument("--days", type=int, default=30, help="OpenSky lookback in days")
    a = p.parse_args()
    print(json.dumps(run(a.sample, a.reset, a.days), indent=2))
