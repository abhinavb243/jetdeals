"""Settings, read from environment variables or a local .env file."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DB_PATH = Path(os.getenv("JETDEAL_DB", DATA_DIR / "jetdeal.db"))

# OpenSky Network, OAuth2 client credentials (https://opensky-network.org -> Account -> API client)
OPENSKY_CLIENT_ID = os.getenv("OPENSKY_CLIENT_ID", "").strip()
OPENSKY_CLIENT_SECRET = os.getenv("OPENSKY_CLIENT_SECRET", "").strip()

# SEC EDGAR asks every automated client to send a descriptive User-Agent with a contact,
# e.g. "JetDeal research tool you@example.com". If unset, EDGAR ingest uses sample data.
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "").strip()

# FAA registry: path to an unzipped ReleasableAircraft folder (MASTER.txt, ACFTREF.txt).
# Download from https://registry.faa.gov/database/ReleasableAircraft.zip
FAA_REGISTRY_DIR = os.getenv("FAA_REGISTRY_DIR", "").strip()

# Privacy block list (LADD / PIA / owner opt-outs). One tail number or ICAO24 hex per row.
BLOCKLIST_PATH = Path(os.getenv("BLOCKLIST_PATH", DATA_DIR / "blocklist.csv"))

# Signal settings
SIGNAL_WINDOW_DAYS = int(os.getenv("SIGNAL_WINDOW_DAYS", "90"))
ALERT_SCORE_THRESHOLD = float(os.getenv("ALERT_SCORE_THRESHOLD", "60"))


def opensky_configured() -> bool:
    return bool(OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET)


def edgar_configured() -> bool:
    return bool(SEC_USER_AGENT)


def faa_configured() -> bool:
    return bool(FAA_REGISTRY_DIR) and (Path(FAA_REGISTRY_DIR) / "MASTER.txt").exists()
