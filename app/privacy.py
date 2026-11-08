"""Privacy guardrails.

Rules applied everywhere aircraft enter the system:
1. Only aircraft registered to organizations are kept (corporation, LLC, partnership,
   non-citizen corporation). Aircraft registered to individuals or co-owners are dropped.
2. Only aircraft that resolve to a company in the `companies` table are tracked.
   Unresolved LLCs (which may be personal holding companies) are not tracked.
3. Any tail number or ICAO24 address in the block list is dropped and purged.
   Put FAA LADD (Limiting Aircraft Data Displayed) entries and owner opt-out requests here.
4. PIA (Privacy ICAO Address) aircraft broadcast a temporary address that is not in the
   FAA registry. Flights are only requested for registry addresses, so PIA aircraft are
   never linked to an owner.
"""
import csv

from . import config

ORG_REGISTRANT_TYPES = {
    "2": "partnership",
    "3": "corporation",
    "7": "llc",
    "8": "non-citizen corporation",
}
# Dropped: 1 individual, 4 co-owned, 5 government, 9 non-citizen co-owned


def load_blocklist() -> set[str]:
    """Return a set of normalized tail numbers and ICAO24 hex codes."""
    blocked: set[str] = set()
    path = config.BLOCKLIST_PATH
    if not path.exists():
        return blocked
    with open(path, newline="") as f:
        for row in csv.reader(f):
            if not row or row[0].strip().startswith("#"):
                continue
            value = row[0].strip()
            if value.lower() == "identifier":
                continue
            blocked.add(normalize(value))
    return blocked


def normalize(ident: str) -> str:
    ident = ident.strip().upper()
    return ident


def is_blocked(tail: str, icao24: str, blocked: set[str]) -> bool:
    tail_n = normalize(tail)
    tail_n = tail_n if tail_n.startswith("N") else "N" + tail_n
    return tail_n in blocked or normalize(icao24) in blocked


def purge_blocked(conn) -> int:
    """Remove blocked aircraft and their flights. Returns number of aircraft removed."""
    blocked = load_blocklist()
    removed = 0
    for row in conn.execute("SELECT icao24, tail FROM aircraft").fetchall():
        if is_blocked(row["tail"], row["icao24"], blocked):
            conn.execute("DELETE FROM flights WHERE icao24=?", (row["icao24"],))
            conn.execute("DELETE FROM aircraft WHERE icao24=?", (row["icao24"],))
            removed += 1
    return removed
