"""SEC EDGAR M&A filings ingest (free, no key; needs a descriptive User-Agent).

For each company with a CIK, reads https://data.sec.gov/submissions/CIK##########.json
and keeps deal-related filings from the last year:
  - 8-K with item 1.01 (material agreement), 2.01 (completed acquisition), 5.01 (change in control)
  - SC 13D / SCHEDULE 13D (activist or >5% stake), SC TO-T (tender offer), S-4, 425, DEFM14A, PREM14A
Single-company filings are stored with that company as the only party.
"""
import time

import httpx

from .. import config, sample_data

DEAL_FORMS = {"SC 13D", "SC 13D/A", "SCHEDULE 13D", "SCHEDULE 13D/A", "SC TO-T", "SC TO-C",
              "S-4", "425", "DEFM14A", "PREM14A"}
DEAL_8K_ITEMS = {"1.01", "2.01", "5.01"}
TARGET_SIDE_FORMS = {"SC 13D", "SC 13D/A", "SCHEDULE 13D", "SCHEDULE 13D/A", "SC TO-T", "DEFM14A", "PREM14A"}


def _insert(conn, acquirer_id, target_id, kind, ts, title, url, source) -> int:
    cur = conn.execute(
        """INSERT OR IGNORE INTO deals(acquirer_id, target_id, kind, ts, title, url, source)
           VALUES (?,?,?,?,?,?,?)""", (acquirer_id, target_id, kind, ts, title, url, source))
    return cur.rowcount


def _sample(conn) -> int:
    ids = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM companies")}
    now = sample_data.now_ts()
    n = 0
    for acq, tgt, kind, days_ago, title in sample_data.deals(now):
        n += _insert(conn, ids.get(acq), ids.get(tgt), kind, now - days_ago * 86400, title,
                     f"sample://{kind}/{days_ago}", "sample")
    return n


def ingest(conn, use_sample: bool) -> dict:
    companies = conn.execute("SELECT id, name, cik FROM companies WHERE cik IS NOT NULL AND cik != ''").fetchall()
    has_sample = conn.execute("SELECT 1 FROM companies WHERE is_sample=1 LIMIT 1").fetchone()
    sample_n = _sample(conn) if has_sample else 0
    if use_sample or not companies:
        return {"mode": "sample", "inserted": sample_n, "errors": []}
    if not config.edgar_configured():
        return {"mode": "sample", "inserted": sample_n,
                "errors": ["SEC_USER_AGENT not set; EDGAR filings skipped"]}

    cutoff = time.time() - 365 * 86400
    inserted, errors = 0, []
    with httpx.Client(timeout=30, headers={"User-Agent": config.SEC_USER_AGENT}) as http:
        for c in companies:
            cik = c["cik"].lstrip("0").zfill(10)
            try:
                r = http.get(f"https://data.sec.gov/submissions/CIK{cik}.json")
                r.raise_for_status()
            except Exception as e:
                errors.append(f'{c["name"]}: {e}')
                continue
            recent = r.json().get("filings", {}).get("recent", {})
            for i, form in enumerate(recent.get("form", [])):
                date = recent["filingDate"][i]
                ts = int(time.mktime(time.strptime(date, "%Y-%m-%d")))
                if ts < cutoff:
                    continue
                items = set((recent.get("items", [""] * (i + 1))[i] or "").split(","))
                if form == "8-K" and items & DEAL_8K_ITEMS:
                    kind = "8-K " + ",".join(sorted(items & DEAL_8K_ITEMS))
                elif form in DEAL_FORMS:
                    kind = form
                else:
                    continue
                acc = recent["accessionNumber"][i].replace("-", "")
                doc = recent.get("primaryDocument", [""] * (i + 1))[i]
                url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}"
                desc = recent.get("primaryDocDescription", [""] * (i + 1))[i] or form
                title = f'{c["name"]}: {form} {desc}'.strip()
                if form in TARGET_SIDE_FORMS:
                    inserted += _insert(conn, None, c["id"], kind, ts, title, url, "edgar")
                else:
                    inserted += _insert(conn, c["id"], None, kind, ts, title, url, "edgar")
            time.sleep(0.15)  # stay well under SEC's 10 requests/second limit
    return {"mode": "live+sample" if has_sample else "live", "inserted": inserted + sample_n, "errors": errors[:10]}
