"""Business-aviation airports and the metro area each one serves.

Extend this table as needed. Keys are ICAO codes.
"""

AIRPORTS = {
    "KTEB": ("Teterboro", "New York"),
    "KHPN": ("Westchester County", "New York"),
    "KJFK": ("John F. Kennedy Intl", "New York"),
    "KMMU": ("Morristown", "New York"),
    "KBED": ("Hanscom Field", "Boston"),
    "KBOS": ("Boston Logan", "Boston"),
    "KIAD": ("Washington Dulles", "Washington DC"),
    "KDCA": ("Reagan National", "Washington DC"),
    "KPDK": ("DeKalb-Peachtree", "Atlanta"),
    "KATL": ("Atlanta Hartsfield", "Atlanta"),
    "KMDW": ("Chicago Midway", "Chicago"),
    "KPWK": ("Chicago Executive", "Chicago"),
    "KDAL": ("Dallas Love Field", "Dallas"),
    "KADS": ("Addison", "Dallas"),
    "KHOU": ("Houston Hobby", "Houston"),
    "KSGR": ("Sugar Land", "Houston"),
    "KAPA": ("Centennial", "Denver"),
    "KSDL": ("Scottsdale", "Phoenix"),
    "KVNY": ("Van Nuys", "Los Angeles"),
    "KSMO": ("Santa Monica", "Los Angeles"),
    "KSJC": ("San Jose Intl", "San Francisco Bay Area"),
    "KSFO": ("San Francisco Intl", "San Francisco Bay Area"),
    "KOAK": ("Oakland", "San Francisco Bay Area"),
    "KBFI": ("Boeing Field", "Seattle"),
    "KMSP": ("Minneapolis-St Paul", "Minneapolis"),
    "KOPF": ("Miami-Opa Locka", "Miami"),
    "KPBI": ("Palm Beach Intl", "Palm Beach"),
    "KBNA": ("Nashville", "Nashville"),
    "KCLT": ("Charlotte Douglas", "Charlotte"),
    "KASE": ("Aspen", "Aspen"),
    "KSUN": ("Friedman Memorial", "Sun Valley"),
    "KOMA": ("Omaha Eppley", "Omaha"),
    "KBTV": ("Burlington", "Burlington VT"),
    "KRDU": ("Raleigh-Durham", "Raleigh"),
    "KAUS": ("Austin-Bergstrom", "Austin"),
    "EGLF": ("Farnborough", "London"),
    "LFPB": ("Paris Le Bourget", "Paris"),
}

# Leisure or conference destinations. Visits here are weak signals on their own.
LEISURE = {"KASE", "KSUN", "KPBI"}


def city(icao: str) -> str:
    return AIRPORTS.get(icao, (icao, icao))[1]


def name(icao: str) -> str:
    return AIRPORTS.get(icao, (icao, icao))[0]
