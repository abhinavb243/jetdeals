"""FAA aircraft registry ingest.

Live mode reads the FAA Releasable Aircraft database (MASTER.txt + ACFTREF.txt) from
FAA_REGISTRY_DIR. Download: https://registry.faa.gov/database/ReleasableAircraft.zip

Only turbofan / turbojet aircraft registered to organizations, and whose registrant
name resolves to a company in the company list, are stored (see app/privacy.py).
"""
import csv
import re
from pathlib import Path

from .. import config, privacy, sample_data

JET_ENGINE_TYPES = {"4", "5"}  # 4 turbo-jet, 5 turbo-fan
_SUFFIX = re.compile(r"\b(INC|LLC|CORP|CORPORATION|CO|COMPANY|LTD|LP|HOLDINGS|GROUP|THE)\b\.?")


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", _SUFFIX.sub("", re.sub(r"[^A-Z0-9 ]", " ", name.upper()))).strip()


def resolve_company(registrant: str, aliases: dict[str, list[str]]) -> str | None:
    """Match a registry name to a company: exact alias first, then normalized company-name prefix."""
    reg = registrant.strip().upper()
    for company, names in aliases.items():
        if reg in names:
            return company
    reg_n = _norm(reg)
    for company in aliases:
        c = _norm(company)
        if c and (reg_n == c or reg_n.startswith(c + " ")):
            return company
    return None


def _read_csv(path: Path):
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader)]
        for row in reader:
            yield {header[i]: (row[i].strip() if i < len(row) else "") for i in range(len(header))}


def _live_rows():
    base = Path(config.FAA_REGISTRY_DIR)
    models = {}
    ref = base / "ACFTREF.txt"
    if ref.exists():
        for r in _read_csv(ref):
            models[r.get("CODE", "")] = f'{r.get("MFR", "").title()} {r.get("MODEL", "")}'.strip()
    for r in _read_csv(base / "MASTER.txt"):
        if r.get("TYPE ENGINE") not in JET_ENGINE_TYPES:
            continue
        hexcode = r.get("MODE S CODE HEX", "").lower()
        if not hexcode:
            continue
        yield ("N" + r["N-NUMBER"], hexcode, r.get("NAME", ""), r.get("TYPE REGISTRANT", ""),
               models.get(r.get("MFR MDL CODE", ""), ""))


def ingest(conn, aliases: dict[str, list[str]], use_sample: bool) -> dict:
    blocked = privacy.load_blocklist()
    stats = {"seen": 0, "kept": 0, "dropped_individual": 0, "dropped_blocked": 0, "unresolved": 0}
    live = config.faa_configured() and not use_sample
    rows = _live_rows() if live else ((t, i, n, ty, m) for t, i, n, ty, m, _o in sample_data.REGISTRY)
    company_ids = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM companies")}
    for tail, icao24, registrant, rtype, model in rows:
        stats["seen"] += 1
        if rtype not in privacy.ORG_REGISTRANT_TYPES:
            stats["dropped_individual"] += 1
            continue
        if privacy.is_blocked(tail, icao24, blocked):
            stats["dropped_blocked"] += 1
            continue
        company = resolve_company(registrant, aliases)
        if not company:
            stats["unresolved"] += 1
            continue
        conn.execute(
            """INSERT INTO aircraft(icao24, tail, registrant, registrant_type, company_id, model, is_sample)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(icao24) DO UPDATE SET tail=excluded.tail, registrant=excluded.registrant,
                 registrant_type=excluded.registrant_type, company_id=excluded.company_id, model=excluded.model""",
            (icao24, tail, registrant, privacy.ORG_REGISTRANT_TYPES[rtype], company_ids[company], model,
             0 if live else 1),
        )
        stats["kept"] += 1
    stats["mode"] = "live" if live else "sample"
    return stats
