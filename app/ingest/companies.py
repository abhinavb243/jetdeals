"""Load the company universe: data/companies.csv (your list) or the fictional sample set."""
import csv

from .. import config, sample_data


def _rows_from_csv():
    path = config.DATA_DIR / "companies.csv"
    if not path.exists():
        return []
    with open(path, newline="") as f:
        lines = [ln for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines))


def load(conn, use_sample: bool) -> dict[str, list[str]]:
    """Insert companies. Returns {company name: [registry owner aliases]}."""
    aliases: dict[str, list[str]] = {}
    rows = _rows_from_csv()
    for r in rows:
        name = r["name"].strip()
        conn.execute(
            """INSERT INTO companies(name, ticker, cik, hq_city, hq_airports, sector, watch, is_sample)
               VALUES (?,?,?,?,?,?,?,0)
               ON CONFLICT(name) DO UPDATE SET ticker=excluded.ticker, cik=excluded.cik,
                 hq_city=excluded.hq_city, hq_airports=excluded.hq_airports, sector=excluded.sector""",
            (name, r.get("ticker") or None, (r.get("cik") or "").strip() or None, r.get("hq_city"),
             (r.get("hq_airports") or "").replace(" ", ""), r.get("sector"), int(r.get("watch") or 0)),
        )
        aliases[name] = [a.strip().upper() for a in (r.get("owner_aliases") or "").split("|") if a.strip()]
    if use_sample or not rows:
        for name, ticker, cik, city, apts, sector, watch in sample_data.COMPANIES:
            conn.execute(
                """INSERT INTO companies(name, ticker, cik, hq_city, hq_airports, sector, watch, is_sample)
                   VALUES (?,?,?,?,?,?,?,1) ON CONFLICT(name) DO NOTHING""",
                (name, ticker, cik, city, apts, sector, watch),
            )
            aliases.setdefault(name, [])
        for tail, icao, registrant, _t, _m, owner in sample_data.REGISTRY:
            if owner:
                aliases.setdefault(owner, []).append(registrant)
    return aliases
