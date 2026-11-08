import os
import tempfile

os.environ["JETDEAL_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from app import db, pipeline, signals  # noqa: E402
from app.ingest.faa import resolve_company  # noqa: E402


def setup_module():
    pipeline.run(use_sample=True, reset=True)


def test_privacy_guardrails():
    with db.session() as c:
        tails = {r["tail"] for r in c.execute("SELECT tail FROM aircraft")}
        types = {r["registrant_type"] for r in c.execute("SELECT registrant_type FROM aircraft")}
    assert "N0IND1" not in tails  # registered to an individual
    assert "N0BLK1" not in tails  # in blocklist.csv
    assert types <= {"corporation", "llc", "partnership", "non-citizen corporation"}


def test_open_alert_and_confirmed_backtest():
    with db.session() as c:
        sig = {(s["visitor"], s["host"]): s for s in signals.compute(c)}
    corvane = sig[("Corvane Biotherapeutics", "Lumora Diagnostics")]
    assert corvane["alert"] and corvane["status"] == "open"
    halv = sig[("Halvorsen Industrial", "Ridgeline Pumps")]
    assert halv["status"] == "confirmed"
    assert halv["backtest"]["lead_days"] and halv["backtest"]["lead_days"] > 14


def test_routine_hub_trips_do_not_alert():
    with db.session() as c:
        sig = {(s["visitor"], s["host"]): s for s in signals.compute(c)}
    assert not sig[("Halvorsen Industrial", "Starling Capital Partners")]["alert"]


def test_resolve_company():
    aliases = {"Acme Widgets": ["ACME FLIGHT LLC"], "Beta Corp": []}
    assert resolve_company("ACME FLIGHT LLC", aliases) == "Acme Widgets"
    assert resolve_company("BETA CORP INC", aliases) == "Beta Corp"
    assert resolve_company("BETA CORPORATION", aliases) == "Beta Corp"
    assert resolve_company("JOHN SMITH", aliases) is None
