"""Fictional sample data, used when a live source is not configured.

All companies are invented. Tail numbers start with "N0", which the FAA never issues,
so they cannot match a real aircraft. ICAO24 codes use the unassigned f0xxxx block.
"""
import random
import time

DAY = 86400

# name, ticker, cik, hq_city, hq_airports, sector, watch
COMPANIES = [
    ("Halvorsen Industrial", "HVSN.X", None, "Chicago", "KMDW,KPWK", "Industrials", 1),
    ("Ridgeline Pumps", "RDGP.X", None, "Dallas", "KDAL,KADS", "Industrials", 0),
    ("Corvane Biotherapeutics", "CRVB.X", None, "Boston", "KBED,KBOS", "Healthcare", 1),
    ("Lumora Diagnostics", "LUMD.X", None, "San Francisco Bay Area", "KSJC,KSFO,KOAK", "Healthcare", 1),
    ("Meridian Freight Systems", "MFRS.X", None, "Atlanta", "KPDK,KATL", "Transportation", 0),
    ("Starling Capital Partners", None, None, "New York", "KTEB,KHPN,KJFK", "Private Equity", 1),
    ("Prairie Foods", "PRFD.X", None, "Omaha", "KOMA", "Consumer Staples", 0),
    ("Talbot Software", "TLBT.X", None, "Austin", "KAUS", "Technology", 0),
    ("Kestrel Energy", "KSTL.X", None, "Houston", "KHOU,KSGR", "Energy", 0),
]

# Registry rows: tail, icao24, registrant, type code (FAA TYPE REGISTRANT), model, owner company
REGISTRY = [
    ("N0HV1", "f00001", "HALVORSEN AVIATION LLC", "7", "Gulfstream G650", "Halvorsen Industrial"),
    ("N0HV2", "f00002", "HALVORSEN INDUSTRIAL INC", "3", "Bombardier Challenger 350", "Halvorsen Industrial"),
    ("N0CV1", "f00003", "CORVANE FLIGHT OPERATIONS LLC", "7", "Dassault Falcon 2000", "Corvane Biotherapeutics"),
    ("N0MF1", "f00004", "MERIDIAN FREIGHT SYSTEMS INC", "3", "Embraer Praetor 600", "Meridian Freight Systems"),
    ("N0SC1", "f00005", "SCP AIR HOLDINGS LLC", "7", "Gulfstream G550", "Starling Capital Partners"),
    ("N0KE1", "f00006", "KESTREL ENERGY CORP", "3", "Cessna Citation Latitude", "Kestrel Energy"),
    # Guardrail demos: these two are dropped at ingest.
    ("N0IND1", "f00007", "SAMPLE PRIVATE INDIVIDUAL", "1", "Cessna Citation CJ4", None),
    ("N0BLK1", "f00008", "LUMORA DIAGNOSTICS INC", "3", "Pilatus PC-24", "Lumora Diagnostics"),
]

# Typical non-deal destinations per company (routine business, customers, leisure).
ROUTINE = {
    "f00001": ["KTEB", "KIAD", "KMSP", "KASE"],
    "f00002": ["KTEB", "KBNA", "KCLT"],
    "f00003": ["KTEB", "KIAD", "KPBI"],
    "f00004": ["KTEB", "KDAL", "KCLT", "KMDW", "KASE"],
    "f00005": ["KPBI", "KBED", "KMDW", "KSUN", "KHOU"],
    "f00006": ["KTEB", "KAPA", "KDAL"],
    "f00007": ["KPBI", "KASE"],
    "f00008": ["KVNY", "KBFI"],
}
HOME = {
    "f00001": "KPWK", "f00002": "KMDW", "f00003": "KBED", "f00004": "KPDK",
    "f00005": "KTEB", "f00006": "KSGR", "f00007": "KPBI", "f00008": "KSJC",
}

# Planted signal patterns: (icao24, destination, list of days-ago for each visit)
PATTERNS = [
    # Halvorsen visits Ridgeline's city 6 times in the 2 months before the deal (deal 12 days ago).
    ("f00001", "KADS", [72, 58, 47, 39, 31, 20]),
    ("f00002", "KDAL", [44, 25]),
    # Corvane visits Lumora's city 5 times in the last 5 weeks. No deal yet: open alert.
    ("f00003", "KSJC", [34, 26, 19, 11, 4]),
    # Starling (PE) visits Prairie Foods in Omaha before an SC 13D filing (filed 6 days ago).
    ("f00005", "KOMA", [41, 28, 15, 9]),
    # Kestrel visits Austin twice. Weak signal, Talbot is not an obvious fit.
    ("f00006", "KAUS", [52, 8]),
]


def deals(now: int):
    """(acquirer, target, kind, days_ago, title)"""
    return [
        ("Halvorsen Industrial", "Ridgeline Pumps", "announced", 12,
         "SAMPLE: Halvorsen Industrial to acquire Ridgeline Pumps for $2.1B"),
        ("Halvorsen Industrial", "Ridgeline Pumps", "8-K", 11,
         "SAMPLE: 8-K Item 1.01 Entry into a Material Definitive Agreement (Ridgeline merger)"),
        ("Starling Capital Partners", "Prairie Foods", "SC 13D", 6,
         "SAMPLE: SC 13D, Starling Capital Partners reports 7.4% stake in Prairie Foods"),
        ("Meridian Freight Systems", "Kestrel Energy", "rumor", 140,
         "SAMPLE: Report says Meridian explored fuel supply JV with Kestrel (talks ended)"),
        (None, "Talbot Software", "rumor", 3,
         "SAMPLE: Talbot Software said to explore strategic options, hires advisers"),
    ]


def flights(now: int, days: int = 200, seed: int = 7):
    """Generate round-trip flights: routine background traffic plus planted patterns."""
    rng = random.Random(seed)
    out = []

    def trip(icao, dest, day_ago, stay_hours=None):
        home = HOME[icao]
        dep = now - day_ago * DAY + rng.randint(6, 10) * 3600 + rng.randint(0, 59) * 60
        block = rng.randint(90, 280) * 60
        stay = (stay_hours if stay_hours is not None else rng.choice([5, 7, 9, 26, 50])) * 3600
        cs = f"SMP{icao[-2:]}"
        out.append((icao, cs, home, dest, dep, dep + block, "sample"))
        back = dep + block + stay
        out.append((icao, cs, dest, home, back, back + block, "sample"))

    for icao, routine in ROUTINE.items():
        day = days
        while day > 1:
            day -= rng.randint(3, 9)
            if day <= 1:
                break
            trip(icao, rng.choice(routine), day)

    for icao, dest, visits in PATTERNS:
        for d in visits:
            trip(icao, dest, d, stay_hours=rng.choice([5, 6, 8]))  # short day trips
    return out


def now_ts() -> int:
    return int(time.time())
