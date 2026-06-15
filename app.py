"""
FinanceIQ - India-focused financial intelligence platform
Flask backend - all data fetched live from free APIs (yfinance, Google News RSS,
exchangerate-api.com). AI analysis powered by Anthropic Claude (Haiku).
"""

import os
import json
import time
import requests
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from flask_caching import Cache

import yfinance as yf

app = Flask(__name__)
CORS(app)

cache = Cache(app, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300})

# ---------------------------------------------------------------------------
# Finnhub — fallback data source when Yahoo Finance rate-limits us.
# Free tier: 60 API calls/minute, no daily cap.
# NSE symbols on Finnhub use the format: NSE:RELIANCE, NSE:HDFCBANK etc.
# ---------------------------------------------------------------------------
FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")
FINNHUB_BASE = "https://finnhub.io/api/v1"


def finnhub_quote(nse_symbol: str) -> dict | None:
    """Fetch a real-time quote from Finnhub for an NSE-listed stock.
    Returns a dict with keys: price, prev_close, change, change_pct
    or None if the request fails.
    """
    try:
        url = f"{FINNHUB_BASE}/quote"
        resp = YF_SESSION.get(
            url,
            params={"symbol": f"NSE:{nse_symbol}", "token": FINNHUB_KEY},
            timeout=8,
        )
        data = resp.json()
        price = data.get("c")       # current price
        prev = data.get("pc")       # previous close
        if not price:
            return None
        change = round(price - prev, 2) if prev else None
        change_pct = round((change / prev) * 100, 2) if prev and prev != 0 else None
        return {
            "price": round(price, 2),
            "prev_close": round(prev, 2) if prev else None,
            "change": change,
            "change_pct": change_pct,
        }
    except Exception:
        return None


def finnhub_index_quote(finnhub_symbol: str) -> dict | None:
    """Fetch a quote for an index (e.g. 'NIFTY 50') from Finnhub.
    Finnhub uses symbols like '^NSEI' same as Yahoo for indices.
    """
    try:
        url = f"{FINNHUB_BASE}/quote"
        resp = YF_SESSION.get(
            url,
            params={"symbol": finnhub_symbol, "token": FINNHUB_KEY},
            timeout=8,
        )
        data = resp.json()
        price = data.get("c")
        prev = data.get("pc")
        if not price:
            return None
        change_pct = round(((price - prev) / prev) * 100, 2) if prev and prev != 0 else None
        return {"price": round(price, 2), "change_pct": change_pct}
    except Exception:
        return None


def finnhub_stock_profile(nse_symbol: str) -> dict | None:
    """Fetch company profile (name, sector, market cap, logo) from Finnhub."""
    try:
        url = f"{FINNHUB_BASE}/stock/profile2"
        resp = YF_SESSION.get(
            url,
            params={"symbol": f"NSE:{nse_symbol}", "token": FINNHUB_KEY},
            timeout=8,
        )
        return resp.json() or None
    except Exception:
        return None


def finnhub_basic_financials(nse_symbol: str) -> dict | None:
    """Fetch key financial metrics from Finnhub (PE, EPS, 52w high/low etc.)."""
    try:
        url = f"{FINNHUB_BASE}/stock/metric"
        resp = YF_SESSION.get(
            url,
            params={"symbol": f"NSE:{nse_symbol}", "metric": "all", "token": FINNHUB_KEY},
            timeout=8,
        )
        data = resp.json()
        return data.get("metric") or None
    except Exception:
        return None



class TimeoutSession(requests.Session):
    """A requests.Session that always applies a default timeout.

    Used for our OWN direct HTTP calls (e.g. Yahoo's search/quote endpoints
    that we call manually). NOT passed to yfinance itself - newer yfinance
    versions (0.2.5x+) require their own internal curl_cffi session for
    Yahoo's bot-detection/cookie handling and will error if given a plain
    requests.Session.
    """

    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", 10)
        return super().request(*args, **kwargs)


YF_SESSION = TimeoutSession()
YF_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def yf_ticker(symbol: str) -> "yf.Ticker":
    """Create a yfinance Ticker, letting yfinance manage its own session."""
    return yf.Ticker(symbol)


def get_info_with_retry(ticker, retries=2, delay=1.5):
    """Fetch ticker.info with a couple of retries.

    Yahoo's quoteSummary endpoint (used by .info) is rate-limited more
    aggressively than the chart endpoint (used by .fast_info/.history),
    especially from shared cloud IPs. A short retry with backoff smooths
    over transient 429s without slowing down the normal case.
    """
    last_err = None
    for attempt in range(retries + 1):
        try:
            info = ticker.info
            if info and (info.get("regularMarketPrice") is not None or info.get("currentPrice") is not None):
                return info
            last_err = info  # empty/partial response, may be a soft rate-limit
        except Exception as e:
            last_err = e
        if attempt < retries:
            time.sleep(delay * (attempt + 1))
    if isinstance(last_err, Exception):
        raise last_err
    return last_err or {}

# ---------------------------------------------------------------------------
# Static lookup data
# ---------------------------------------------------------------------------

# Common company-name -> NSE symbol map for "smart search" auto-detection.
# ---------------------------------------------------------------------------
# Broad NSE company name lookup (~1,500 listed companies, built from official
# NSE equity-list and Nifty 500 data). Used as a fallback after COMPANY_MAP
# so searching by full/short company name works for far more stocks than the
# ~150 hand-curated common aliases below. Keyed by lowercased company name.
# ---------------------------------------------------------------------------
NSE_COMPANY_NAME_MAP = {}
try:
    with open(os.path.join(os.path.dirname(__file__), "nse_companies.json"), encoding="utf-8") as f:
        _nse_companies = json.load(f)
    for _sym, _info in _nse_companies.items():
        for _key in (_info.get("name"), _info.get("short")):
            if _key:
                NSE_COMPANY_NAME_MAP.setdefault(_key.strip().lower(), _sym)
except Exception:
    NSE_COMPANY_NAME_MAP = {}

# yfinance has no reliable free search endpoint for NSE, so we keep a curated
# map of the most commonly searched companies and fall back to trying the
# raw input (with .NS / .BO suffixes) for anything else.
COMPANY_MAP = {
    "reliance": "RELIANCE", "reliance industries": "RELIANCE",
    "tcs": "TCS", "tata consultancy": "TCS", "tata consultancy services": "TCS",
    "infosys": "INFY", "infy": "INFY",
    "hdfc bank": "HDFCBANK", "hdfc": "HDFCBANK",
    "icici bank": "ICICIBANK", "icici": "ICICIBANK",
    "sbi": "SBIN", "state bank of india": "SBIN",
    "axis bank": "AXISBANK",
    "kotak": "KOTAKBANK", "kotak mahindra bank": "KOTAKBANK",
    "bharti airtel": "BHARTIARTL", "airtel": "BHARTIARTL",
    "itc": "ITC",
    "larsen": "LT", "l&t": "LT", "larsen and toubro": "LT",
    "wipro": "WIPRO",
    "hcl tech": "HCLTECH", "hcltech": "HCLTECH",
    "asian paints": "ASIANPAINT",
    "maruti": "MARUTI", "maruti suzuki": "MARUTI",
    "bajaj finance": "BAJFINANCE",
    "bajaj finserv": "BAJAJFINSV",
    "titan": "TITAN",
    "sun pharma": "SUNPHARMA",
    "ultratech": "ULTRACEMCO", "ultratech cement": "ULTRACEMCO",
    "ntpc": "NTPC",
    "ongc": "ONGC",
    "tata motors": "TATAMOTORS",
    "tata steel": "TATASTEEL",
    "adani enterprises": "ADANIENT", "adani": "ADANIENT",
    "adani ports": "ADANIPORTS",
    "power grid": "POWERGRID",
    "coal india": "COALINDIA",
    "nestle": "NESTLEIND", "nestle india": "NESTLEIND",
    "hindustan unilever": "HINDUNILVR", "hul": "HINDUNILVR",
    "mahindra": "M&M", "m&m": "M&M", "mahindra and mahindra": "M&M",
    "nmdc": "NMDC",
    "zomato": "ETERNAL",
    "paytm": "PAYTM",
    "jsw steel": "JSWSTEEL",
    "grasim": "GRASIM",
    "dr reddy": "DRREDDY", "dr reddys": "DRREDDY",
    "cipla": "CIPLA",
    "indusind bank": "INDUSINDBK",
    "tech mahindra": "TECHM",
    "britannia": "BRITANNIA",
    "divis lab": "DIVISLAB",
    "eicher motors": "EICHERMOT",
    "shriram finance": "SHRIRAMFIN",
    "trent": "TRENT",
    "hero motocorp": "HEROMOTOCO",
    "bajaj auto": "BAJAJ-AUTO",
    # --- Banks & NBFCs ---
    "canara bank": "CANBK",
    "bank of baroda": "BANKBARODA", "bob": "BANKBARODA",
    "punjab national bank": "PNB", "pnb": "PNB",
    "bank of india": "BANKINDIA",
    "union bank of india": "UNIONBANK", "union bank": "UNIONBANK",
    "indian bank": "INDIANB",
    "muthoot finance": "MUTHOOTFIN", "muthoot": "MUTHOOTFIN",
    "federal bank": "FEDERALBNK",
    "idfc first bank": "IDFCFIRSTB", "idfc first": "IDFCFIRSTB",
    "yes bank": "YESBANK",
    "au small finance bank": "AUBANK", "au bank": "AUBANK",
    "bandhan bank": "BANDHANBNK",
    "cholamandalam investment": "CHOLAFIN", "chola finance": "CHOLAFIN",
    "l&t finance": "LTF", "lt finance": "LTF",
    "power finance corporation": "PFC", "pfc": "PFC",
    "rec limited": "RECLTD", "rec ltd": "RECLTD",
    "lic housing finance": "LICHSGFIN",
    "sbi cards": "SBICARD",
    "hdfc life": "HDFCLIFE", "hdfc life insurance": "HDFCLIFE",
    "sbi life": "SBILIFE", "sbi life insurance": "SBILIFE",
    "icici prudential life": "ICICIPRULI",
    "icici lombard": "ICICIGI",
    "bajaj holdings": "BAJAJHLDNG",
    "lic": "LICI", "life insurance corporation": "LICI",
    # --- Oil, gas & energy ---
    "indian oil corporation": "IOC", "indian oil": "IOC", "ioc": "IOC",
    "bharat petroleum": "BPCL", "bpcl": "BPCL",
    "hindustan petroleum": "HINDPETRO", "hpcl": "HINDPETRO",
    "gail": "GAIL", "gail india": "GAIL",
    "vedanta": "VEDL",
    "hindalco": "HINDALCO", "hindalco industries": "HINDALCO",
    # --- Telecom ---
    "vodafone idea": "IDEA", "vi": "IDEA",
    # --- Pharma & healthcare ---
    "lupin": "LUPIN",
    "aurobindo pharma": "AUROPHARMA",
    "apollo hospitals": "APOLLOHOSP",
    "zydus lifesciences": "ZYDUSLIFE", "zydus": "ZYDUSLIFE",
    # --- Consumer / FMCG ---
    "dabur": "DABUR", "dabur india": "DABUR",
    "godrej consumer products": "GODREJCP", "godrej consumer": "GODREJCP",
    "marico": "MARICO",
    "colgate palmolive": "COLPAL", "colgate": "COLPAL",
    "pidilite industries": "PIDILITIND", "pidilite": "PIDILITIND",
    "varun beverages": "VBL",
    "united spirits": "MCDOWELL-N",
    # --- Capital goods / industrials ---
    "siemens": "SIEMENS",
    "abb india": "ABB", "abb": "ABB",
    "havells india": "HAVELLS", "havells": "HAVELLS",
    "voltas": "VOLTAS",
    "bharat electronics": "BEL",
    "bharat forge": "BHARATFORG",
    "cummins india": "CUMMINSIND", "cummins": "CUMMINSIND",
    "cg power": "CGPOWER",
    # --- Real estate ---
    "dlf": "DLF",
    "godrej properties": "GODREJPROP",
    "oberoi realty": "OBEROIRLTY",
    # --- Adani group & cement ---
    "adani green energy": "ADANIGREEN", "adani green": "ADANIGREEN",
    "adani power": "ADANIPOWER",
    "adani total gas": "ATGL",
    "adani energy solutions": "ADANIENSOL",
    "ambuja cements": "AMBUJACEM", "ambuja": "AMBUJACEM",
    "acc": "ACC", "acc limited": "ACC",
    # --- Autos ---
    "tvs motor": "TVSMOTOR", "tvs motor company": "TVSMOTOR",
    "ashok leyland": "ASHOKLEY",
    "motherson": "MOTHERSON", "samvardhana motherson": "MOTHERSON",
    # --- IT ---
    "persistent systems": "PERSISTENT", "persistent": "PERSISTENT",
    "ltimindtree": "LTIM",
    "mphasis": "MPHASIS",
    "coforge": "COFORGE",
    # --- Other large caps ---
    "info edge": "NAUKRI", "naukri": "NAUKRI",
    "irfc": "IRFC", "indian railway finance": "IRFC",
    "irctc": "IRCTC",
    "policybazaar": "POLICYBZR", "pb fintech": "POLICYBZR",
    "indian hotels": "INDHOTEL",
    "indigo": "INDIGO", "interglobe aviation": "INDIGO",
    # --- Rest of Nifty 100 / popular F&O & midcaps ---
    "avenue supermarts": "DMART", "dmart": "DMART",
    "bharat heavy electricals": "BHEL", "bhel": "BHEL",
    "bosch": "BOSCHLTD", "bosch limited": "BOSCHLTD",
    "hdfc amc": "HDFCAMC", "hdfc asset management": "HDFCAMC",
    "indus towers": "INDUSTOWER",
    "jindal steel": "JINDALSTEL", "jindal steel and power": "JINDALSTEL",
    "max healthcare": "MAXHEALTH",
    "nhpc": "NHPC",
    "oil india": "OIL",
    "page industries": "PAGEIND",
    "polycab india": "POLYCAB", "polycab": "POLYCAB",
    "shree cement": "SHREECEM",
    "srf": "SRF", "srf limited": "SRF",
    "suzlon energy": "SUZLON", "suzlon": "SUZLON",
    "torrent pharma": "TORNTPHARM", "torrent pharmaceuticals": "TORNTPHARM",
    "zee entertainment": "ZEEL", "zee": "ZEEL",
    "tata power": "TATAPOWER",
    "tata communications": "TATACOMM",
    "tata elxsi": "TATAELXSI",
    "tata chemicals": "TATACHEM",
    "gmr airports": "GMRAIRPORT", "gmr": "GMRAIRPORT",
    "jubilant foodworks": "JUBLFOOD", "jubilant": "JUBLFOOD",
    "pvr inox": "PVRINOX", "pvr": "PVRINOX",
    "aditya birla capital": "ABCAPITAL",
    "aditya birla fashion": "ABFRL",
    "piramal enterprises": "PEL",
    "indraprastha gas": "IGL",
    "mahanagar gas": "MGL",
    "petronet lng": "PETRONET",
    "container corporation": "CONCOR", "concor": "CONCOR",
    "national aluminium": "NATIONALUM", "nalco": "NATIONALUM",
    "steel authority of india": "SAIL", "sail": "SAIL",
    "mrf": "MRF", "mrf tyres": "MRF",
    "apollo tyres": "APOLLOTYRE",
    "balkrishna industries": "BALKRISIND",
    "escorts kubota": "ESCORTS", "escorts": "ESCORTS",
    "bata india": "BATAINDIA", "bata": "BATAINDIA",
    "berger paints": "BERGEPAINT",
    "kansai nerolac": "KANSAINER",
    "united breweries": "UBL",
    "itc hotels": "ITCHOTELS",
    "macrotech developers": "LODHA", "lodha": "LODHA",
    "phoenix mills": "PHOENIXLTD",
    "prestige estates": "PRESTIGE",
    "sun tv network": "SUNTV", "sun tv": "SUNTV",
    "biocon": "BIOCON",
    "alkem laboratories": "ALKEM", "alkem": "ALKEM",
    "mankind pharma": "MANKIND",
    "laurus labs": "LAURUSLABS",
    "gland pharma": "GLAND",
    "syngene international": "SYNGENE", "syngene": "SYNGENE",
    "abbott india": "ABBOTINDIA", "abbott": "ABBOTINDIA",
    "glenmark pharmaceuticals": "GLENMARK", "glenmark": "GLENMARK",
    "torrent power": "TORNTPOWER",
    "jsw energy": "JSWENERGY",
    "ntpc green energy": "NTPCGREEN",
    "tata investment corporation": "TATAINVEST",
    "multi commodity exchange": "MCX", "mcx": "MCX",
    "bse limited": "BSE", "bse": "BSE",
    "central depository services": "CDSL", "cdsl": "CDSL",
    "angel one": "ANGELONE",
    "360 one wam": "360ONE",
    "kpit technologies": "KPITTECH", "kpit": "KPITTECH",
    "tata technologies": "TATATECH",
    "honasa consumer": "HONASA", "mamaearth": "HONASA",
    "nykaa": "NYKAA", "fsn e-commerce": "NYKAA",
    "delhivery": "DELHIVERY",
    "cartrade tech": "CARTRADE", "cartrade": "CARTRADE",
    "go digit": "GODIGIT",

    # Defence
    "hindustan aeronautics": "HAL", "hal": "HAL",
    "bharat electronics": "BEL", "bel": "BEL",
    "bharat dynamics": "BDL", "bdl": "BDL",
    "mazagon dock": "MAZDOCK", "mazagon dock shipbuilders": "MAZDOCK",
    "cochin shipyard": "COCHINSHIP",
    "solar industries": "SOLARINDS",
    "beml": "BEML",
    "data patterns": "DATAPATTNS",

    # Infra / construction
    "gmr airports": "GMRINFRA", "gmr infra": "GMRINFRA",
    "irb infrastructure": "IRB",
    "kec international": "KEC",
    "nbcc": "NBCC", "nbcc india": "NBCC",
    "ncc limited": "NCC",
    "rail vikas nigam": "RVNL", "rvnl": "RVNL",

    # Realty
    "brigade enterprises": "BRIGADE",
    "sobha limited": "SOBHA", "sobha": "SOBHA",

    # Media
    "dish tv": "DISHTV",
    "network18": "NETWORK18", "network 18": "NETWORK18",
    "saregama india": "SAREGAMA", "saregama": "SAREGAMA",
    "tips industries": "TIPSINDLTD", "tips music": "TIPSINDLTD",
    "nazara technologies": "NAZARA", "nazara": "NAZARA",

    # Mid/large cap consumer & financials
    "astral limited": "ASTRAL", "astral pipes": "ASTRAL",
    "supreme industries": "SUPREMEIND",
    "max financial services": "MFSL", "max financial": "MFSL",
    "tata consumer products": "TATACONSUM", "tata consumer": "TATACONSUM",

    # Other popular large/mid caps not yet covered
    "adani enterprises": "ADANIENT",
    "adani power": "ADANIPOWER",
    "jio financial services": "JIOFIN", "jio financial": "JIOFIN",
    "zomato": "ETERNAL", "eternal": "ETERNAL",
    "paytm": "PAYTM", "one97 communications": "PAYTM",
    "policybazaar": "PBFINTECH", "pb fintech": "PBFINTECH",
    "swiggy": "SWIGGY",
    "vodafone idea": "IDEA", "vi": "IDEA",
    "punjab national bank": "PNB",
    "bank of baroda": "BANKBARODA",
    "canara bank": "CANBK",
    "union bank of india": "UNIONBANK",
    "indian oil": "IOC", "indian oil corporation": "IOC",
    "bharat petroleum": "BPCL",
    "hindustan petroleum": "HINDPETRO",
    "ntpc limited": "NTPC", "ntpc green energy": "NTPCGREEN",
    "power grid": "POWERGRID", "power grid corporation": "POWERGRID",
    "vedanta limited": "VEDL", "vedanta": "VEDL",
    "jindal steel": "JINDALSTEL", "jindal steel and power": "JINDALSTEL",
    "sail": "SAIL", "steel authority of india": "SAIL",
    "nmdc limited": "NMDC",
    "coal india": "COALINDIA",
    "dlf limited": "DLF",
    "godrej properties": "GODREJPROP",
    "oberoi realty": "OBEROIRLTY",
    "phoenix mills": "PHOENIXLTD",
    "prestige estates": "PRESTIGE",
    "lodha": "LODHA", "macrotech developers": "LODHA",
    "indian hotels": "INDHOTEL", "taj hotels": "INDHOTEL",
    "federal bank": "FEDERALBNK",
    "au small finance bank": "AUBANK",
    "polycab india": "POLYCAB", "polycab": "POLYCAB",
    "coforge": "COFORGE",
    "page industries": "PAGEIND", "jockey": "PAGEIND",
    "zee entertainment": "ZEEL", "zee": "ZEEL",
    "sun tv network": "SUNTV", "sun tv": "SUNTV",
    "pvr inox": "PVRINOX", "pvr": "PVRINOX",
    "lupin limited": "LUPIN",
    "aurobindo pharma": "AUROPHARMA",
    "torrent pharma": "TORNTPHARM", "torrent pharmaceuticals": "TORNTPHARM",
    "zydus lifesciences": "ZYDUSLIFE", "zydus": "ZYDUSLIFE",
    "divi's laboratories": "DIVISLAB", "divis lab": "DIVISLAB",
    "marico limited": "MARICO",
    "dabur india": "DABUR",
    "godrej consumer": "GODREJCP", "godrej consumer products": "GODREJCP",
    "britannia industries": "BRITANNIA",
    "nestle india": "NESTLEIND",
    "ashok leyland": "ASHOKLEY",
    "tvs motor": "TVSMOTOR", "tvs motor company": "TVSMOTOR",
    "eicher motors": "EICHERMOT", "royal enfield": "EICHERMOT",
    "hero motocorp": "HEROMOTOCO",
    "mahindra and mahindra": "M&M", "mahindra": "M&M",
    "bajaj auto": "BAJAJ-AUTO",
    "wipro limited": "WIPRO",
    "tech mahindra": "TECHM",
    "ltimindtree": "LTIM", "lti mindtree": "LTIM",
    "mphasis": "MPHASIS",
    "persistent systems": "PERSISTENT",
    "hcl technologies": "HCLTECH", "hcl tech": "HCLTECH",
    "adani green energy": "ADANIGREEN", "adani green": "ADANIGREEN",
    "tata power": "TATAPOWER",
    "ongc": "ONGC", "oil and natural gas corporation": "ONGC",
    "adani ports": "ADANIPORTS", "adani ports and sez": "ADANIPORTS",
    "larsen and toubro": "LT", "l&t": "LT",
    "indusind bank": "INDUSINDBK",
    "bharti airtel": "BHARTIARTL", "airtel": "BHARTIARTL",
}


NIFTY50_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "SBIN", "BHARTIARTL",
    "ITC", "LT", "KOTAKBANK", "AXISBANK", "HINDUNILVR", "BAJFINANCE", "ASIANPAINT",
    "MARUTI", "TITAN", "SUNPHARMA", "ULTRACEMCO", "NTPC", "ONGC", "TATAMOTORS",
    "TATASTEEL", "ADANIENT", "ADANIPORTS", "POWERGRID", "COALINDIA", "NESTLEIND",
    "M&M", "WIPRO", "HCLTECH",
]

SECTOR_INDICES = {
    "Auto": "^CNXAUTO",
    "Bank": "^CNXBANK",
    "IT": "^CNXIT",
    "Pharma": "^CNXPHARMA",
    "FMCG": "^CNXFMCG",
    "Metal": "^CNXMETAL",
    "Realty": "^CNXREALTY",
    "Energy": "^CNXENERGY",
    "Infra": "^CNXINFRA",
    "Media": "^CNXMEDIA",
}

# Curated representative stocks shown when a heatmap cell, or one of the
# index overview cards (Nifty 50 / Sensex / Nifty Bank / Nifty Midcap), is
# clicked. "Defence" has no Yahoo sector-index ticker, so its heatmap
# change_pct is computed as the average change of these constituents instead.
SECTOR_STOCKS = {
    "Auto": ["MARUTI", "TATAMOTORS", "M&M", "BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO", "ASHOKLEY", "TVSMOTOR"],
    "Bank": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK", "BANKBARODA", "PNB"],
    "IT": ["TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "LTIM", "MPHASIS", "PERSISTENT"],
    "Pharma": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "LUPIN", "AUROPHARMA", "TORNTPHARM", "ZYDUSLIFE"],
    "FMCG": ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "DABUR", "TATACONSUM", "GODREJCP", "MARICO"],
    "Metal": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "JINDALSTEL", "SAIL", "NMDC", "COALINDIA"],
    "Realty": ["DLF", "GODREJPROP", "OBEROIRLTY", "PHOENIXLTD", "PRESTIGE", "BRIGADE", "SOBHA", "LODHA"],
    "Energy": ["RELIANCE", "ONGC", "NTPC", "POWERGRID", "ADANIGREEN", "TATAPOWER", "BPCL", "IOC"],
    "Infra": ["LT", "ADANIPORTS", "GMRINFRA", "IRB", "NBCC", "NCC", "KEC", "RVNL"],
    "Media": ["ZEEL", "SUNTV", "PVRINOX", "NETWORK18", "DISHTV", "TIPSINDLTD", "SAREGAMA", "NAZARA"],
    "Defence": ["HAL", "BEL", "BDL", "MAZDOCK", "COCHINSHIP", "SOLARINDS", "BEML", "DATAPATTNS"],
    "Nifty 50": ["RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "BHARTIARTL", "ITC", "LT", "SBIN", "HINDUNILVR"],
    "Nifty Midcap": ["PERSISTENT", "FEDERALBNK", "INDHOTEL", "POLYCAB", "COFORGE", "MFSL", "ASTRAL", "SUPREMEIND", "PAGEIND", "AUBANK"],
}

# Index-overview cards (NIFTY 50 / SENSEX / NIFTY BANK / NIFTY MIDCAP) map to
# a SECTOR_STOCKS entry for their "click to see stocks" popup. Sensex shares
# the Nifty 50 large-cap basket since the two largely overlap.
INDEX_OVERVIEW_STOCK_KEY = {
    "NIFTY 50": "Nifty 50",
    "SENSEX": "Nifty 50",
    "NIFTY BANK": "Bank",
    "NIFTY MIDCAP": "Nifty Midcap",
}

# Every stock available for the "52-Week High/Low" scanner: the union of
# NIFTY 50 and every sector-stocks basket used around the site.
ALL_WEBSITE_STOCKS = sorted(set(NIFTY50_SYMBOLS) | {s for stocks in SECTOR_STOCKS.values() for s in stocks})

TICKER_SYMBOLS = {
    "NIFTY 50": "^NSEI",
    "SENSEX": "^BSESN",
    "NIFTY BANK": "^NSEBANK",
    "NIFTY IT": "^CNXIT",
    "USD/INR": "INR=X",
    "Gold": "GC=F",
    "Crude Oil": "CL=F",
}

# Finnhub symbols for the ticker bar items (where available)
FINNHUB_TICKER_MAP = {
    "NIFTY 50": "NSE:NIFTY50",
    "SENSEX": "BSE:SENSEX",
    "NIFTY BANK": "NSE:BANKNIFTY",
    "NIFTY IT": "NSE:NIFTYIT",
    "USD/INR": "OANDA:USD_INR",
}

COMMODITY_SYMBOLS = {
    "Gold": "GC=F",
    "Silver": "SI=F",
    "Crude Oil (WTI)": "CL=F",
    "Crude Oil (Brent)": "BZ=F",
    "Natural Gas": "NG=F",
    "Wheat": "ZW=F",
    "Rice": "ZR=F",
    "Sugar": "SB=F",
}

# Yahoo quotes some futures in cents (not dollars) and with units that aren't
# obvious from the raw number alone. This maps each commodity to a
# (divisor, display_unit) pair so the displayed price is in real dollars
# with a meaningful unit label.
COMMODITY_UNIT_INFO = {
    "Gold": (1, "/oz"),
    "Silver": (1, "/oz"),
    "Crude Oil (WTI)": (1, "/barrel"),
    "Crude Oil (Brent)": (1, "/barrel"),
    "Natural Gas": (1, "/MMBtu"),
    "Wheat": (100, "/bushel"),   # CBOT quotes in cents/bushel
    "Rice": (1, "/cwt"),         # already $/cwt
    "Sugar": (100, "/lb"),       # ICE quotes in cents/lb
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def resolve_symbol(user_input: str) -> str:
    """Turn a free-text company name or symbol into a yfinance-ready NSE symbol."""
    raw = user_input.strip()
    key = raw.lower()

    if key in COMPANY_MAP:
        base = COMPANY_MAP[key]
    else:
        # try partial match against the curated company map
        match = None
        for name, sym in COMPANY_MAP.items():
            if key in name or name in key:
                match = sym
                break

        if not match and key in NSE_COMPANY_NAME_MAP:
            match = NSE_COMPANY_NAME_MAP[key]

        if not match:
            # try partial match against the broad ~1,500-company NSE name map
            for name, sym in NSE_COMPANY_NAME_MAP.items():
                if key in name or name in key:
                    match = sym
                    break

        base = match if match else raw.upper().replace(" ", "")

    base = base.replace(".NS", "").replace(".BO", "")
    return base


def safe_get(d, *keys, default=None):
    for k in keys:
        if d is None:
            return default
        d = d.get(k)
    return d if d is not None else default


def fmt_crore(value):
    """Convert a raw rupee number into crore for display."""
    if value is None:
        return None
    try:
        return round(value / 1e7, 2)
    except (TypeError, ZeroDivisionError):
        return None


def fetch_newsapi(query: str, limit: int = 10) -> tuple:
    """Fetch news from NewsAPI.org (primary source, requires NEWS_API_KEY env var).

    Returns (error_or_None, items_list) — same contract as fetch_google_news_rss
    so callers can treat both interchangeably.
    Free tier: 100 requests/day, articles from last 30 days.
    """
    api_key = os.environ.get("NEWS_API_KEY", "")
    if not api_key:
        return {"error": "No NEWS_API_KEY configured"}, []

    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": limit,
                "apiKey": api_key,
            },
            timeout=8,
        )
        data = resp.json()
        if data.get("status") != "ok":
            return {"error": data.get("message", "NewsAPI error")}, []

        items = []
        for article in data.get("articles", []):
            title = article.get("title") or ""
            source = (article.get("source") or {}).get("name") or "NewsAPI"
            link = article.get("url") or ""
            published = article.get("publishedAt") or ""

            # Skip removed articles
            if title == "[Removed]" or not title:
                continue

            items.append({
                "title": title,
                "source": source,
                "link": link,
                "published": published,
                "description": article.get("description") or "",
            })

        return None, items[:limit]
    except Exception as e:
        return {"error": f"NewsAPI request failed: {e}"}, []


def fetch_google_news_rss(query: str, limit: int = 3, recency: str = "when:7d"):
    """Fetch and parse Google News RSS for a query. No API key required.

    Restricts results to the last 7 days (Google News' `when:` search operator)
    and sorts by actual publish date so the freshest stories appear first.
    """
    full_query = f"{query} {recency}" if recency else query
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(full_query)}&hl=en-IN&gl=IN&ceid=IN:en"
    items = []
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        for item in root.findall("./channel/item"):
            title = item.findtext("title") or ""
            link = item.findtext("link") or ""
            pub_date = item.findtext("pubDate") or ""
            source_el = item.find("source")
            source = source_el.text if source_el is not None else ""

            # title is often "Headline - Source"
            display_title = title
            if " - " in title and source:
                display_title = title.rsplit(" - ", 1)[0]

            try:
                sort_key = parsedate_to_datetime(pub_date)
                if sort_key.tzinfo is None:
                    sort_key = sort_key.replace(tzinfo=timezone.utc)
            except Exception:
                sort_key = datetime.min.replace(tzinfo=timezone.utc)

            items.append({
                "title": display_title,
                "source": source or "Google News",
                "link": link,
                "published": pub_date,
                "_sort_key": sort_key,
            })

        # newest first
        items.sort(key=lambda it: it["_sort_key"], reverse=True)
        for it in items:
            del it["_sort_key"]
        items = items[:limit]

        # If the recency filter returned too few/no results, fall back to an
        # unrestricted search so the page isn't empty.
        if not items and recency:
            return fetch_google_news_rss(query, limit=limit, recency=None)

    except Exception as e:
        return {"error": f"Could not fetch news: {e}"}, items
    return None, items


def fetch_news(query: str, limit: int = 10) -> tuple:
    """Smart news fetcher: tries NewsAPI first, falls back to Google News RSS.

    Returns (error_or_None, items_list).
    """
    err, items = fetch_newsapi(query, limit=limit)
    if not err and items:
        return None, items
    # Fallback to Google News RSS
    return fetch_google_news_rss(query, limit=limit)


def get_anthropic_key():
    """API key supplied by the frontend via header, falling back to env var."""
    return request.headers.get("X-Anthropic-Key") or os.environ.get("ANTHROPIC_API_KEY")


def call_claude_haiku(system_prompt: str, user_message: str, api_key: str, max_tokens: int = 1024):
    """Call Claude Haiku via the Anthropic Messages API."""
    if not api_key:
        return None, "No Anthropic API key configured. Add one in Settings."

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
            },
            timeout=30,
        )
        if resp.status_code != 200:
            return None, f"Anthropic API error ({resp.status_code}): {resp.text[:200]}"

        data = resp.json()
        text_parts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        text = "\n".join(text_parts).strip()

        # Strip markdown code fences if present (handles ```json ... ``` and ``` ... ```)
        if text.startswith("```"):
            # Remove opening fence + optional language tag
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            # Remove closing fence and anything after it
            if "```" in text:
                text = text.rsplit("```", 1)[0]
            text = text.strip()

        # Some responses include trailing text/explanations after valid JSON.
        # Use raw_decode to parse just the first complete JSON value and
        # ignore anything that follows.
        try:
            obj, _ = json.JSONDecoder().raw_decode(text)
            return obj, None
        except json.JSONDecodeError:
            # Last resort: try to extract the first {...} or [...] block
            for open_ch, close_ch in (("[", "]"), ("{", "}")):
                start = text.find(open_ch)
                end = text.rfind(close_ch)
                if start != -1 and end != -1 and end > start:
                    try:
                        return json.loads(text[start:end + 1]), None
                    except json.JSONDecodeError:
                        continue
            raise
    except json.JSONDecodeError as e:
        return None, f"Could not parse AI response: {e}"
    except Exception as e:
        return None, f"AI request failed: {e}"


def generate_news_briefs(items, api_key, topic_hint="", word_count=150):
    """Given a list of news items (with 'title' and 'source'), ask Claude
    Haiku to write a short ORIGINAL article for each one, in Claude's own
    words, based only on the headline and source. This avoids reproducing
    copyrighted article text while still giving the user a useful, readable
    summary directly in the app.

    Returns the items list with an added 'article' field on each item
    (or unchanged items if no API key / on error).
    """
    if not items or not api_key:
        return items

    system_prompt = (
        "You are a financial news writer for an Indian retail-investor app, known for "
        "making market news genuinely engaging without sacrificing substance. "
        f"For each headline (and description, if given) below, write an ORIGINAL news "
        f"brief of approximately {word_count} words in your own words. "
        "Structure each brief to cover every angle concisely: (1) what happened - the "
        "core event, key numbers, names, or outcome; (2) the context - why this is "
        "happening now or what led to it; (3) the so-what - what it means for Indian "
        "markets, a sector, or everyday investors. Open with a strong, specific first "
        "sentence (not a generic lead-in like 'In recent news...'). Write in plain, "
        "vivid English for a non-expert reader, in dense sentences with zero filler, "
        "so the reader walks away genuinely informed, not just teased. "
        "Do not quote or closely paraphrase any specific article - write a "
        "general explainer based on the headline and topic. "
        + (f"Context: these headlines relate to {topic_hint}. " if topic_hint else "")
        + "Return ONLY a valid JSON array of strings, one per headline, in "
        "the same order as the input, with no extra text."
    )

    headlines = [
        {"title": it["title"], "source": it.get("source", ""), "description": it.get("description", "")}
        for it in items
    ]
    # Budget enough output tokens for N articles of ~word_count words each
    # (roughly 1.4 tokens/word) plus JSON overhead, capped at a sane max.
    max_tokens = min(8192, max(2048, int(len(items) * word_count * 1.6) + 512))

    result, err = call_claude_haiku(
        system_prompt, json.dumps(headlines), api_key, max_tokens=max_tokens
    )

    if err or not isinstance(result, list):
        return items

    for i, brief in enumerate(result):
        if i < len(items) and isinstance(brief, str):
            items[i]["article"] = brief

    return items


# ---------------------------------------------------------------------------
# Stock endpoints
# ---------------------------------------------------------------------------


@app.route("/api/search/<query>")
@cache.cached(timeout=120)
def stock_autocomplete(query):
    """Live search across ALL NSE and BSE listed stocks using Yahoo Finance's
    public search/autocomplete index (no key required)."""
    try:
        resp = YF_SESSION.get(
            "https://query1.finance.yahoo.com/v1/finance/search",
            params={
                "q": query,
                "quotesCount": 12,
                "newsCount": 0,
                "lang": "en-IN",
                "region": "IN",
            },
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        seen = set()
        for q in data.get("quotes", []):
            exchange = q.get("exchange", "")
            if exchange not in ("NSI", "BSE"):
                continue  # only NSE / BSE listed instruments

            symbol = q.get("symbol", "")
            clean_symbol = symbol.replace(".NS", "").replace(".BO", "")
            if clean_symbol in seen:
                continue
            seen.add(clean_symbol)

            results.append({
                "symbol": clean_symbol,
                "name": q.get("longname") or q.get("shortname") or clean_symbol,
                "exchange": "NSE" if exchange == "NSI" else "BSE",
            })

        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": f"Search failed: {e}"})


@app.route("/api/stock/<symbol>")
@cache.cached(query_string=True)
def stock_data(symbol):
    try:
        nse_symbol = resolve_symbol(symbol)

        # ── Primary: Yahoo Finance ──────────────────────────────────────────
        yf_ok = False
        info = {}
        try:
            ticker = yf_ticker(f"{nse_symbol}.NS")
            info = get_info_with_retry(ticker)
            if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
                ticker = yf_ticker(f"{nse_symbol}.BO")
                info = get_info_with_retry(ticker)
            if info and (info.get("regularMarketPrice") is not None or info.get("currentPrice") is not None):
                yf_ok = True
        except Exception:
            pass

        if yf_ok:
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
            change = round(price - prev_close, 2) if price and prev_close else None
            change_pct = round((change / prev_close) * 100, 2) if change and prev_close else None
            result = {
                "symbol": nse_symbol,
                "exchange_symbol": f"{nse_symbol}.NS",
                "name": info.get("longName") or info.get("shortName") or nse_symbol,
                "sector": info.get("sector", "N/A"),
                "industry": info.get("industry", "N/A"),
                "price": price,
                "change": change,
                "change_pct": change_pct,
                "currency": info.get("currency", "INR"),
                "market_cap": info.get("marketCap"),
                "market_cap_cr": fmt_crore(info.get("marketCap")),
                "week52_high": info.get("fiftyTwoWeekHigh"),
                "week52_low": info.get("fiftyTwoWeekLow"),
                "pe_ratio": info.get("trailingPE"),
                "eps": info.get("trailingEps"),
                "revenue_cr": fmt_crore(info.get("totalRevenue")),
                "net_profit_cr": fmt_crore(info.get("netIncomeToCommon")),
                "debt_to_equity": info.get("debtToEquity"),
                "roce": info.get("returnOnAssets"),
                "roe": info.get("returnOnEquity"),
                "promoter_holding": info.get("heldPercentInsiders"),
                "dividend_yield": info.get("dividendYield"),
                "logo_url": (
                    f"https://logo.clearbit.com/{info.get('website', '').replace('https://', '').replace('http://', '').rstrip('/')}"
                    if info.get("website") else
                    f"https://ui-avatars.com/api/?name={requests.utils.quote(info.get('shortName', nse_symbol))}&background=2563EB&color=fff"
                ),
                "data_source": "Yahoo Finance",
            }
            return jsonify(result)

        # ── Fallback: Finnhub ───────────────────────────────────────────────
        fq = finnhub_quote(nse_symbol)
        if not fq:
            return jsonify({"error": f"Could not find data for '{symbol}'. Try the exact NSE symbol (e.g. RELIANCE, HDFCBANK)."})

        profile = finnhub_stock_profile(nse_symbol) or {}
        metrics = finnhub_basic_financials(nse_symbol) or {}

        market_cap = metrics.get("marketCapitalization")  # Finnhub gives this in millions USD
        market_cap_inr = int(market_cap * 1e6 * 84) if market_cap else None  # rough USD→INR
        market_cap_cr = fmt_crore(market_cap_inr)

        logo = profile.get("logo") or f"https://ui-avatars.com/api/?name={requests.utils.quote(profile.get('name', nse_symbol))}&background=2563EB&color=fff"

        result = {
            "symbol": nse_symbol,
            "exchange_symbol": f"NSE:{nse_symbol}",
            "name": profile.get("name") or nse_symbol,
            "sector": profile.get("finnhubIndustry") or "N/A",
            "industry": profile.get("finnhubIndustry") or "N/A",
            "price": fq["price"],
            "change": fq["change"],
            "change_pct": fq["change_pct"],
            "currency": "INR",
            "market_cap": market_cap_inr,
            "market_cap_cr": market_cap_cr,
            "week52_high": metrics.get("52WeekHigh"),
            "week52_low": metrics.get("52WeekLow"),
            "pe_ratio": metrics.get("peBasicExclExtraTTM") or metrics.get("peTTM"),
            "eps": metrics.get("epsBasicExclExtraItemsTTM") or metrics.get("epsTTM"),
            "revenue_cr": None,
            "net_profit_cr": None,
            "debt_to_equity": metrics.get("totalDebt/totalEquityAnnual"),
            "roce": metrics.get("roaRfy"),
            "roe": metrics.get("roeRfy"),
            "promoter_holding": None,
            "dividend_yield": metrics.get("dividendYieldIndicatedAnnual"),
            "logo_url": logo,
            "data_source": "Finnhub",
        }
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Failed to fetch stock data: {e}"})


@app.route("/api/stock/<symbol>/news")
@cache.cached(query_string=True)
def stock_news(symbol):
    try:
        nse_symbol = resolve_symbol(symbol)
        # try to get a friendlier company name
        try:
            info = get_info_with_retry(yf_ticker(f"{nse_symbol}.NS"), retries=1)
            company_name = info.get("longName") or info.get("shortName") or nse_symbol
        except Exception:
            company_name = nse_symbol

        err, items = fetch_news(f"{company_name} stock India", limit=5)
        if err:
            return jsonify(err)

        items = generate_news_briefs(items, get_anthropic_key(), topic_hint=f"{company_name} (Indian stock)")
        return jsonify({"symbol": nse_symbol, "news": items})
    except Exception as e:
        return jsonify({"error": f"Failed to fetch news: {e}"})


@app.route("/api/stock/<symbol>/corporate-actions")
@cache.cached(query_string=True, timeout=3600)
def corporate_actions(symbol):
    """Real dividend & stock-split history from Yahoo Finance (free, no key)."""
    try:
        nse_symbol = resolve_symbol(symbol)
        ticker = yf_ticker(f"{nse_symbol}.NS")

        dividends = []
        try:
            div_series = ticker.dividends
            if div_series is not None and not div_series.empty:
                for date, amount in div_series.tail(8).items():
                    dividends.append({
                        "date": date.strftime("%Y-%m-%d"),
                        "amount": round(float(amount), 2),
                    })
                dividends.reverse()
        except Exception:
            pass

        splits = []
        try:
            split_series = ticker.splits
            if split_series is not None and not split_series.empty:
                for date, ratio in split_series.tail(5).items():
                    splits.append({
                        "date": date.strftime("%Y-%m-%d"),
                        "ratio": float(ratio),
                    })
                splits.reverse()
        except Exception:
            pass

        return jsonify({"symbol": nse_symbol, "dividends": dividends, "splits": splits})
    except Exception as e:
        return jsonify({"error": f"Failed to fetch corporate actions: {e}"})


def _df_row(df, *names):
    """Find the first matching row (by any of `names`) in a yfinance
    financial-statement DataFrame and return it as a {period_str: value} dict,
    or {} if none of the names are present."""
    if df is None or df.empty:
        return {}
    for name in names:
        if name in df.index:
            row = df.loc[name]
            out = {}
            for col, val in row.items():
                try:
                    out[col.strftime("%b %Y")] = None if val is None or (isinstance(val, float) and val != val) else round(float(val) / 1e7, 2)
                except Exception:
                    continue
            return out
    return {}


@app.route("/api/stock/<symbol>/financials")
@cache.cached(timeout=21600)
def stock_financials(symbol):
    """Quarterly P&L (as many recent quarters as Yahoo provides - typically
    up to ~5) and annual balance sheet (typically up to ~4 years). Yahoo's
    free data doesn't guarantee a fixed history length, so we return
    whatever is available rather than a fixed 3y/5y window, and the
    frontend labels columns by actual period end-dates."""
    try:
        nse_symbol = resolve_symbol(symbol)
        ticker = yf_ticker(f"{nse_symbol}.NS")

        try:
            qf = ticker.quarterly_income_stmt
        except Exception:
            qf = None
        try:
            bs = ticker.balance_sheet
        except Exception:
            bs = None

        revenue = _df_row(qf, "Total Revenue", "Operating Revenue")
        net_profit = _df_row(qf, "Net Income", "Net Income Common Stockholders")
        operating_profit = _df_row(qf, "Operating Income", "EBIT")
        ebitda = _df_row(qf, "EBITDA", "Normalized EBITDA")

        periods = list(revenue.keys()) or list(net_profit.keys())
        quarterly_pnl = []
        for p in periods:
            quarterly_pnl.append({
                "period": p,
                "revenue_cr": revenue.get(p),
                "operating_profit_cr": operating_profit.get(p),
                "ebitda_cr": ebitda.get(p),
                "net_profit_cr": net_profit.get(p),
            })

        total_assets = _df_row(bs, "Total Assets")
        total_liabilities = _df_row(bs, "Total Liabilities Net Minority Interest", "Total Liab")
        total_equity = _df_row(bs, "Stockholders Equity", "Total Equity Gross Minority Interest")
        total_debt = _df_row(bs, "Total Debt")
        cash = _df_row(bs, "Cash And Cash Equivalents", "Cash")

        bs_periods = list(total_assets.keys()) or list(total_equity.keys())
        balance_sheet = []
        for p in bs_periods:
            balance_sheet.append({
                "period": p,
                "total_assets_cr": total_assets.get(p),
                "total_liabilities_cr": total_liabilities.get(p),
                "total_equity_cr": total_equity.get(p),
                "total_debt_cr": total_debt.get(p),
                "cash_cr": cash.get(p),
            })

        if not quarterly_pnl and not balance_sheet:
            return jsonify({"error": f"Financial statements not available for '{nse_symbol}'."})

        return jsonify({
            "symbol": nse_symbol,
            "quarterly_pnl": quarterly_pnl,
            "balance_sheet": balance_sheet,
            "note": (
                "Figures in ₹ crore. Showing all periods available from Yahoo Finance "
                "(typically the most recent 4-5 quarters for P&L and 4 years for the "
                "balance sheet) - exact history length varies by company."
            ),
        })
    except Exception as e:
        return jsonify({"error": f"Failed to fetch financial statements: {e}"})


@app.route("/api/stock/<symbol>/scorecard")
@cache.cached(query_string=True, timeout=900)
def stock_scorecard(symbol):
    try:
        nse_symbol = resolve_symbol(symbol)
        info = get_info_with_retry(yf_ticker(f"{nse_symbol}.NS"))

        if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
            return jsonify({"error": f"Could not find data for '{symbol}'."})

        metrics = {
            "name": info.get("longName") or info.get("shortName") or nse_symbol,
            "sector": info.get("sector"),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "eps": info.get("trailingEps"),
            "revenue_growth_pct": info.get("revenueGrowth"),
            "earnings_growth_pct": info.get("earningsGrowth"),
            "profit_margin_pct": info.get("profitMargins"),
            "debt_to_equity": info.get("debtToEquity"),
            "return_on_equity_pct": info.get("returnOnEquity"),
            "promoter_holding_pct": info.get("heldPercentInsiders"),
            "dividend_yield_pct": info.get("dividendYield"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "52w_change_pct": info.get("52WeekChange"),
            "beta": info.get("beta"),
        }

        api_key = get_anthropic_key()
        system_prompt = (
            "You are a financial analyst specializing in Indian stock markets. "
            "Analyze the provided stock data and return ONLY valid JSON with no "
            "extra text in this exact format: "
            '{"scores": {"valuation": X, "growth": X, "financials": X, "momentum": X, "overall": X}, '
            '"positives": ["one liner 1", "one liner 2", "one liner 3"], '
            '"negatives": ["one liner 1", "one liner 2", "one liner 3"], '
            '"meeting_updates": ["update 1", "update 2", "update 3"], '
            '"summary": "2 sentence plain English summary for a common person"} '
            "Score each metric from 1-10 based on the data provided. "
            "For meeting_updates, since you don't have real corporate-action data, "
            "write plausible *generic but clearly labelled illustrative* recent-update "
            "style lines based on sector and company context, and prefix each with "
            "'Illustrative:' so the user knows to verify on the official exchange filing."
        )
        user_message = json.dumps(metrics, default=str)

        ai_result, ai_err = call_claude_haiku(system_prompt, user_message, api_key)
        if ai_err:
            return jsonify({"error": ai_err, "metrics_used": metrics})

        return jsonify(ai_result)
    except Exception as e:
        return jsonify({"error": f"Failed to generate scorecard: {e}"})


# ---------------------------------------------------------------------------
# Market dashboard endpoints
# ---------------------------------------------------------------------------


@app.route("/api/market/ticker")
@cache.cached(timeout=300)
def market_ticker():
    out = {}
    for label, sym in TICKER_SYMBOLS.items():
        price, change_pct = None, None
        # Try Yahoo first
        try:
            fi = yf_ticker(sym).fast_info
            price = fi.get("lastPrice") or fi.get("last_price")
            prev = fi.get("previousClose") or fi.get("previous_close")
            if price and prev:
                change_pct = round(((price - prev) / prev) * 100, 2)
                price = round(price, 2)
        except Exception:
            pass

        # Finnhub fallback for indices/forex if Yahoo failed
        if price is None and label in FINNHUB_TICKER_MAP:
            try:
                resp = YF_SESSION.get(
                    f"{FINNHUB_BASE}/quote",
                    params={"symbol": FINNHUB_TICKER_MAP[label], "token": FINNHUB_KEY},
                    timeout=8,
                )
                fdata = resp.json()
                fp = fdata.get("c")
                fp_prev = fdata.get("pc")
                if fp:
                    price = round(fp, 2)
                    change_pct = round(((fp - fp_prev) / fp_prev) * 100, 2) if fp_prev else None
            except Exception:
                pass

        out[label] = {"price": price, "change_pct": change_pct}
    return jsonify(out)


@app.route("/api/watchlist/<symbols>")
@cache.cached(timeout=120)
def watchlist(symbols):
    """Live price + change for an arbitrary, user-supplied list of symbols
    (used by the Dashboard's 'My Watchlist' card)."""
    syms = [s.strip() for s in symbols.split(",") if s.strip()][:10]
    if not syms:
        return jsonify({"items": []})

    try:
        resolved = [resolve_symbol(s) for s in syms]
        yf_symbols = [f"{s}.NS" for s in resolved]

        items = []
        if len(yf_symbols) == 1:
            data = yf.download(yf_symbols[0], period="2d", interval="1d",
                                progress=False)
            closes = data["Close"].dropna() if data is not None else None
            if closes is not None and len(closes) >= 1:
                last = closes.iloc[-1]
                prev = closes.iloc[-2] if len(closes) >= 2 else None
                pct = round(((last - prev) / prev) * 100, 2) if prev else None
                items.append({"symbol": resolved[0], "price": round(float(last), 2), "change_pct": pct})
            else:
                items.append({"symbol": resolved[0], "price": None, "change_pct": None})
        else:
            data = yf.download(yf_symbols, period="2d", interval="1d", group_by="ticker",
                                progress=False, threads=True)
            for orig, ysym in zip(resolved, yf_symbols):
                try:
                    df = data[ysym]
                    closes = df["Close"].dropna()
                    if len(closes) >= 1:
                        last = closes.iloc[-1]
                        prev = closes.iloc[-2] if len(closes) >= 2 else None
                        pct = round(((last - prev) / prev) * 100, 2) if prev else None
                        items.append({"symbol": orig, "price": round(float(last), 2), "change_pct": pct})
                    else:
                        items.append({"symbol": orig, "price": None, "change_pct": None})
                except Exception:
                    items.append({"symbol": orig, "price": None, "change_pct": None})

        return jsonify({"items": items})
    except Exception as e:
        return jsonify({"error": f"Failed to fetch watchlist: {e}"})


@app.route("/api/market/overview")
@cache.cached(timeout=600)
def market_overview():
    try:
        # ── Indices ────────────────────────────────────────────────────────
        INDEX_MAP = {
            "NIFTY 50":    ("^NSEI",      "NSE:NIFTY50"),
            "SENSEX":      ("^BSESN",     "BSE:SENSEX"),
            "NIFTY BANK":  ("^NSEBANK",   "NSE:BANKNIFTY"),
            "NIFTY MIDCAP":("^NSEMDCP50", None),
        }
        indices = {}
        for label, (yf_sym, fh_sym) in INDEX_MAP.items():
            price, change_pct = None, None
            try:
                fi = yf_ticker(yf_sym).fast_info
                price = fi.get("lastPrice")
                prev = fi.get("previousClose")
                if price and prev:
                    change_pct = round(((price - prev) / prev) * 100, 2)
                    price = round(price, 2)
            except Exception:
                pass
            # Finnhub fallback
            if price is None and fh_sym:
                fq = finnhub_index_quote(fh_sym)
                if fq:
                    price, change_pct = fq["price"], fq["change_pct"]
            indices[label] = {"price": price, "change_pct": change_pct}

        # ── Gainers / Losers from Nifty 50 basket ──────────────────────────
        movers = []
        yf_failed = False
        try:
            symbols = [f"{s}.NS" for s in NIFTY50_SYMBOLS]
            data = yf.download(symbols, period="2d", interval="1d", group_by="ticker",
                                progress=False, threads=True)
            for s in NIFTY50_SYMBOLS:
                try:
                    df = data[f"{s}.NS"] if len(symbols) > 1 else data
                    closes = df["Close"].dropna()
                    if len(closes) >= 2:
                        last, prev = closes.iloc[-1], closes.iloc[-2]
                        pct = round(((last - prev) / prev) * 100, 2)
                        movers.append({"symbol": s, "price": round(float(last), 2), "change_pct": pct})
                except Exception:
                    continue
        except Exception:
            yf_failed = True

        # Finnhub fallback: fetch a subset of Nifty50 stocks if Yahoo failed
        if yf_failed or len(movers) < 5:
            sample = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
                      "HINDUNILVR", "ITC", "SBIN", "BAJFINANCE", "AXISBANK",
                      "LT", "KOTAKBANK", "TITAN", "WIPRO", "ONGC",
                      "MARUTI", "NTPC", "ULTRACEMCO", "POWERGRID", "NESTLEIND"]
            for s in sample:
                if any(m["symbol"] == s for m in movers):
                    continue
                fq = finnhub_quote(s)
                if fq and fq["price"]:
                    movers.append({"symbol": s, "price": fq["price"], "change_pct": fq["change_pct"] or 0})

        movers_sorted = sorted([m for m in movers if m.get("change_pct") is not None],
                                key=lambda x: x["change_pct"], reverse=True)
        gainers = movers_sorted[:5]
        losers = movers_sorted[-5:][::-1]

        return jsonify({"indices": indices, "gainers": gainers, "losers": losers})
    except Exception as e:
        return jsonify({"error": f"Failed to fetch market overview: {e}"})


def quote_change_pct(nse_symbol: str) -> float | None:
    """Quick helper: today's % change for an NSE symbol via Yahoo fast_info."""
    try:
        fi = yf_ticker(f"{nse_symbol}.NS").fast_info
        price = fi.get("lastPrice")
        prev = fi.get("previousClose")
        if price and prev:
            return round(((price - prev) / prev) * 100, 2)
    except Exception:
        pass
    return None


@app.route("/api/market/heatmap")
@cache.cached(timeout=300)
def market_heatmap():
    out = []

    def fetch_index_sector(sector, sym):
        try:
            fi = yf_ticker(sym).fast_info
            price = fi.get("lastPrice")
            prev = fi.get("previousClose")
            change_pct = round(((price - prev) / prev) * 100, 2) if price and prev else 0
        except Exception:
            change_pct = 0
        return {"sector": sector, "change_pct": change_pct, "key": sector}

    def fetch_defence_sector():
        symbols = SECTOR_STOCKS["Defence"]
        with ThreadPoolExecutor(max_workers=8) as executor:
            changes = [c for c in executor.map(quote_change_pct, symbols) if c is not None]
        avg = round(sum(changes) / len(changes), 2) if changes else 0
        return {"sector": "Defence", "change_pct": avg, "key": "Defence"}

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch_index_sector, sector, sym) for sector, sym in SECTOR_INDICES.items()]
        futures.append(executor.submit(fetch_defence_sector))

        for future in as_completed(futures, timeout=20):
            try:
                out.append(future.result())
            except Exception:
                pass

    # Keep a stable, sensible ordering: original sectors, then Defence
    order = list(SECTOR_INDICES.keys()) + ["Defence"]
    out.sort(key=lambda s: order.index(s["sector"]) if s["sector"] in order else 999)

    return jsonify({"sectors": out})


@app.route("/api/market/sector/<key>/stocks")
@cache.cached(timeout=300)
def sector_stocks(key):
    """Representative stock list with live prices for a heatmap cell."""
    symbols = SECTOR_STOCKS.get(key)
    if not symbols:
        return jsonify({"error": f"Unknown sector '{key}'."})

    def fetch_stock(symbol):
        try:
            fi = yf_ticker(f"{symbol}.NS").fast_info
            price = fi.get("lastPrice")
            prev = fi.get("previousClose")
            change_pct = round(((price - prev) / prev) * 100, 2) if price and prev else None
            return {
                "symbol": symbol,
                "price": round(price, 2) if price is not None else None,
                "change_pct": change_pct,
            }
        except Exception:
            return {"symbol": symbol, "price": None, "change_pct": None}

    with ThreadPoolExecutor(max_workers=8) as executor:
        stocks = list(executor.map(fetch_stock, symbols))

    return jsonify({"sector": key, "stocks": stocks})


GLOBAL_INDICES = {
    "Dow Jones": "^DJI",
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "FTSE 100": "^FTSE",
    "Nikkei 225": "^N225",
    "Hang Seng": "^HSI",
    "Shanghai Composite": "000001.SS",
}


@app.route("/api/market/global")
@cache.cached(timeout=600)
def market_global():
    """Snapshot of major global indices for cross-market context."""
    out = {}

    def fetch_index(label, sym):
        try:
            fi = yf_ticker(sym).fast_info
            price = fi.get("lastPrice")
            prev = fi.get("previousClose")
            change_pct = round(((price - prev) / prev) * 100, 2) if price and prev else None
            return label, {"price": round(price, 2) if price is not None else None, "change_pct": change_pct}
        except Exception:
            return label, {"price": None, "change_pct": None}

    with ThreadPoolExecutor(max_workers=8) as executor:
        for label, val in executor.map(lambda kv: fetch_index(*kv), GLOBAL_INDICES.items()):
            out[label] = val

    return jsonify(out)



@app.route("/api/market/52week")
@cache.cached(timeout=1800)
def market_52week():
    """Scan every stock available on the site and rank by proximity to its
    52-week high and low. Returns the top 5 closest to each extreme, plus
    the full ranked list (for the "show all" view)."""

    def fetch_stock(symbol):
        try:
            fi = yf_ticker(f"{symbol}.NS").fast_info
            price = fi.get("lastPrice")
            year_high = fi.get("yearHigh")
            year_low = fi.get("yearLow")
            if not price or not year_high or not year_low:
                return None
            pct_from_high = round((price - year_high) / year_high * 100, 2)
            pct_from_low = round((price - year_low) / year_low * 100, 2)
            return {
                "symbol": symbol,
                "price": round(price, 2),
                "year_high": round(year_high, 2),
                "year_low": round(year_low, 2),
                "pct_from_high": pct_from_high,
                "pct_from_low": pct_from_low,
            }
        except Exception:
            return None

    results = []
    with ThreadPoolExecutor(max_workers=16) as executor:
        for r in executor.map(fetch_stock, ALL_WEBSITE_STOCKS):
            if r:
                results.append(r)

    near_high = sorted(results, key=lambda r: r["pct_from_high"], reverse=True)[:5]
    near_low = sorted(results, key=lambda r: r["pct_from_low"])[:5]
    all_sorted = sorted(results, key=lambda r: r["pct_from_high"], reverse=True)

    return jsonify({"near_high": near_high, "near_low": near_low, "all": all_sorted})


@app.route("/api/market/active")
@cache.cached(timeout=300)
def most_active():
    out = []
    try:
        symbols = [f"{s}.NS" for s in NIFTY50_SYMBOLS]
        data = yf.download(symbols, period="2d", interval="1d", group_by="ticker",
                            progress=False, threads=True)
        for s in NIFTY50_SYMBOLS:
            try:
                df = data[f"{s}.NS"] if len(symbols) > 1 else data
                vol = df["Volume"].dropna().iloc[-1]
                price = df["Close"].dropna().iloc[-1]
                out.append({"symbol": s, "price": round(price, 2), "volume": int(vol)})
            except Exception:
                continue
        out.sort(key=lambda x: x["volume"], reverse=True)
        return jsonify({"active": out[:10]})
    except Exception as e:
        return jsonify({"error": f"Failed to fetch most active stocks: {e}"})


# ---------------------------------------------------------------------------
# Macro / commodities / news endpoints
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Live macro indicators
#
# There's no free, no-key, real-time API for India's RBI repo rate, CPI/WPI,
# IIP or PMI. To keep these "live" without a paid data subscription, we pull
# recent news about each indicator and ask Claude to extract the latest
# reported figures into structured JSON. Cached for 24h since these figures
# only change monthly (CPI/IIP/PMI) or a few times a year (repo rate, GDP).
# If extraction fails or no Anthropic key is configured, routes fall back to
# the curated baseline values below.
# ---------------------------------------------------------------------------

LIVE_MACRO_SYSTEM_PROMPT = (
    "You are extracting the latest published values of Indian macroeconomic "
    "indicators from recent news snippets. For each field below, return the "
    "MOST RECENTLY reported value mentioned in the snippets, or null if no "
    "snippet clearly states it. Do not estimate or invent numbers - only use "
    "values explicitly present in the text. Return ONLY a JSON object with "
    "exactly these keys, no extra text:\n"
    "{\n"
    '  "repo_rate": number or null (RBI repo rate, percent),\n'
    '  "repo_stance": string or null (e.g. "Neutral", "Accommodative"),\n'
    '  "repo_change_date": string or null (e.g. "Jun 2026", when the repo rate was last changed/announced),\n'
    '  "gdp_growth_pct": number or null (latest reported India real GDP growth rate, percent),\n'
    '  "gdp_period": string or null (e.g. "Q1 FY27" or "FY 2025-26"),\n'
    '  "cpi_pct": number or null (latest India CPI/retail inflation rate, percent),\n'
    '  "cpi_month": string or null (e.g. "May 2026"),\n'
    '  "wpi_pct": number or null (latest India WPI/wholesale inflation rate, percent),\n'
    '  "wpi_month": string or null,\n'
    '  "iip_pct": number or null (latest India Index of Industrial Production growth, percent),\n'
    '  "iip_month": string or null,\n'
    '  "pmi_manufacturing": number or null (latest India Manufacturing PMI value),\n'
    '  "pmi_services": number or null (latest India Services PMI value),\n'
    '  "pmi_month": string or null,\n'
    '  "as_of": string (today\'s approximate context date based on the news, e.g. "Jun 2026")\n'
    "}"
)


@cache.memoize(timeout=86400)
def get_live_macro_indicators() -> dict:
    """Best-effort live macro figures extracted from recent news via Claude.
    Returns {} if unavailable (no key, no news, or extraction failure)."""
    api_key = get_anthropic_key()
    if not api_key:
        return {}

    err1, news1 = fetch_news("RBI repo rate monetary policy India MPC", limit=6)
    err2, news2 = fetch_news("India CPI WPI inflation IIP industrial production GDP growth PMI", limit=8)

    items = (news1 if not err1 else []) + (news2 if not err2 else [])
    if not items:
        return {}

    context = [
        {"title": it.get("title", ""), "description": it.get("description", ""), "published": it.get("published", "")}
        for it in items
    ]

    result, err = call_claude_haiku(LIVE_MACRO_SYSTEM_PROMPT, json.dumps(context, default=str), api_key, max_tokens=1024)
    if err or not isinstance(result, dict):
        return {}
    return result


@app.route("/api/macro/inflation")
@cache.cached(timeout=3600)
def macro_inflation():
    # Curated from RBI / MOSPI published releases. Update periodically.
    base = {
        "cpi": {
            "latest_pct": 4.83,
            "month": "Apr 2026",
            "trend": "down",
            "categories": {
                "Food & Beverages": 5.2,
                "Fuel & Light": 3.1,
                "Core (ex food & fuel)": 3.5,
                "Housing": 3.0,
                "Clothing & Footwear": 2.7,
            },
            "history_12m": [5.1, 5.5, 5.7, 5.9, 6.1, 5.4, 5.0, 4.9, 4.7, 4.6, 4.8, 4.83],
        },
        "wpi": {
            "latest_pct": 2.1,
            "month": "Apr 2026",
            "trend": "up",
            "history_12m": [0.5, 0.7, 1.1, 1.3, 1.6, 1.8, 1.9, 1.7, 1.5, 1.8, 2.0, 2.1],
        },
        "impact_note": (
            "When CPI inflation rises, everyday items like groceries, vegetables and "
            "transport tend to get costlier. A reading near or below 4% is comfortable "
            "for the RBI and usually points to stable EMIs ahead, while readings above "
            "6% raise the chance of higher loan rates."
        ),
        "source": "Curated from RBI / MoSPI public releases - verify on mospi.gov.in for the latest print",
    }

    live = get_live_macro_indicators()
    if live:
        if live.get("cpi_pct") is not None:
            base["cpi"]["latest_pct"] = live["cpi_pct"]
        if live.get("cpi_month"):
            base["cpi"]["month"] = live["cpi_month"]
        if live.get("wpi_pct") is not None:
            base["wpi"]["latest_pct"] = live["wpi_pct"]
        if live.get("wpi_month"):
            base["wpi"]["month"] = live["wpi_month"]
        if live.get("cpi_pct") is not None or live.get("wpi_pct") is not None:
            base["source"] = (
                f"Live figures extracted from recent news (as of {live.get('as_of', 'recent')}); "
                "category breakdown and 12-month history are curated baselines - "
                "verify on mospi.gov.in for exact prints."
            )

    return jsonify(base)


@app.route("/api/macro/rbi")
@cache.cached(timeout=3600)
def macro_rbi():
    base = {
        "repo_rate": 6.00,
        "reverse_repo_rate": 3.35,
        "crr": 4.00,
        "slr": 18.00,
        "last_change_date": "Feb 2026",
        "last_change": "-0.25%",
        "stance": "Neutral",
        "history": [
            {"date": "Apr 2025", "repo_rate": 6.50},
            {"date": "Jun 2025", "repo_rate": 6.25},
            {"date": "Oct 2025", "repo_rate": 6.25},
            {"date": "Feb 2026", "repo_rate": 6.00},
        ],
        "source": "Curated from RBI Monetary Policy Committee releases - verify on rbi.org.in",
    }

    live = get_live_macro_indicators()
    if live and live.get("repo_rate") is not None:
        new_rate = live["repo_rate"]
        if new_rate != base["repo_rate"]:
            base["repo_rate"] = new_rate
            label = live.get("repo_change_date") or live.get("as_of") or "Recent"
            # append to history if it's a new data point
            if not base["history"] or base["history"][-1]["repo_rate"] != new_rate:
                base["history"].append({"date": label, "repo_rate": new_rate})
            base["last_change_date"] = label
        if live.get("repo_stance"):
            base["stance"] = live["repo_stance"]
        base["source"] = (
            f"Repo rate live-checked against recent news (as of {live.get('as_of', 'recent')}); "
            "CRR/SLR and history are curated baselines - verify on rbi.org.in."
        )

    return jsonify(base)


@app.route("/api/macro/growth")
@cache.cached(timeout=3600)
def macro_growth():
    base = {
        "gdp_growth_pct": 6.8,
        "gdp_quarter": "Q4 FY26",
        "iip": {
            "latest_pct": 4.2,
            "month": "Mar 2026",
            "history_12m": [3.1, 3.5, 4.0, 4.4, 3.8, 4.6, 5.0, 4.8, 4.1, 3.9, 4.0, 4.2],
        },
        "pmi": {
            "manufacturing": 58.4,
            "services": 60.1,
            "month": "May 2026",
        },
        "source": "Curated from MoSPI / S&P Global PMI public releases - verify on mospi.gov.in",
    }

    live = get_live_macro_indicators()
    if live:
        updated = False
        if live.get("gdp_growth_pct") is not None:
            base["gdp_growth_pct"] = live["gdp_growth_pct"]
            updated = True
        if live.get("gdp_period"):
            base["gdp_quarter"] = live["gdp_period"]
        if live.get("iip_pct") is not None:
            base["iip"]["latest_pct"] = live["iip_pct"]
            updated = True
        if live.get("iip_month"):
            base["iip"]["month"] = live["iip_month"]
        if live.get("pmi_manufacturing") is not None:
            base["pmi"]["manufacturing"] = live["pmi_manufacturing"]
            updated = True
        if live.get("pmi_services") is not None:
            base["pmi"]["services"] = live["pmi_services"]
            updated = True
        if live.get("pmi_month"):
            base["pmi"]["month"] = live["pmi_month"]

        if updated:
            base["source"] = (
                f"Live figures extracted from recent news (as of {live.get('as_of', 'recent')}); "
                "IIP 12-month history is a curated baseline - verify on mospi.gov.in."
            )

    return jsonify(base)


# ---------------------------------------------------------------------------
# Price history — used for the "tap a ticker / commodity for a chart" feature.
# Covers both index/forex tickers (TICKER_SYMBOLS) and commodities
# (COMMODITY_SYMBOLS), with a 1/2/3/4-year period toggle on the frontend.
# ---------------------------------------------------------------------------

HISTORY_SYMBOLS = {**TICKER_SYMBOLS, **COMMODITY_SYMBOLS}
VALID_HISTORY_PERIODS = {"1d", "1y", "2y", "3y", "4y"}


def convert_commodity_series(label: str, values: list[float]) -> tuple[list[float], str]:
    """Apply unit conversion for commodities quoted in non-obvious units
    (e.g. cents->dollars for Wheat/Sugar) so the history chart matches
    what's shown on the card. All commodities are displayed in USD."""
    if label in COMMODITY_UNIT_INFO:
        divisor, unit_label = COMMODITY_UNIT_INFO[label]
        return [round(v / divisor, 2) for v in values], unit_label
    return values, "USD"


@app.route("/api/history/<label>")
@cache.cached(query_string=True, timeout=3600)
def price_history(label):
    period = request.args.get("period", "1y")
    if period not in VALID_HISTORY_PERIODS:
        period = "1y"

    sym = HISTORY_SYMBOLS.get(label)
    if not sym:
        return jsonify({"error": f"No historical data available for '{label}'."})

    try:
        t = yf_ticker(sym)
        if period == "1d":
            # Intraday candles for today's session.
            hist = t.history(period="1d", interval="5m")
        else:
            # Weekly candles for longer ranges keep the response small and fast.
            interval = "1d" if period == "1y" else "1wk"
            hist = t.history(period=period, interval=interval)

        closes = hist["Close"].dropna()

        if closes.empty:
            return jsonify({"error": f"No historical data available for '{label}'."})

        if period == "1d":
            dates = [d.strftime("%H:%M") for d in closes.index]
        else:
            dates = [d.strftime("%Y-%m-%d") for d in closes.index]
        prices = [round(float(v), 2) for v in closes.tolist()]

        unit = "USD"
        if label in COMMODITY_SYMBOLS:
            prices, unit = convert_commodity_series(label, prices)

        return jsonify({"label": label, "period": period, "dates": dates, "prices": prices, "unit": unit})
    except Exception as e:
        return jsonify({"error": f"Could not fetch history for '{label}': {e}"})


@app.route("/api/commodities")
@cache.cached(timeout=300)
def commodities():
    out = {}

    for label, sym in COMMODITY_SYMBOLS.items():
        try:
            t = yf_ticker(sym)
            hist = t.history(period="7d", interval="1d")
            closes = hist["Close"].dropna().tolist()
            price = closes[-1] if closes else None
            prev = closes[-2] if len(closes) > 1 else None
            change_pct = round(((price - prev) / prev) * 100, 2) if price and prev else None

            # Day high/low from today's intraday candles
            day_high, day_low = None, None
            try:
                intraday = t.history(period="1d", interval="5m")
                hi = intraday["High"].dropna()
                lo = intraday["Low"].dropna()
                if not hi.empty:
                    day_high = float(hi.max())
                if not lo.empty:
                    day_low = float(lo.min())
            except Exception:
                pass

            display_price = price
            unit = "USD"

            if label in COMMODITY_SYMBOLS and price is not None:
                converted_closes, unit = convert_commodity_series(label, closes)
                display_price = converted_closes[-1] if converted_closes else None
                closes = converted_closes

                if day_high is not None:
                    day_high = convert_commodity_series(label, [day_high])[0][0]
                if day_low is not None:
                    day_low = convert_commodity_series(label, [day_low])[0][0]

            out[label] = {
                "price": round(price, 2) if price is not None else None,
                "display_price": display_price,
                "day_high": day_high,
                "day_low": day_low,
                "unit": unit,
                "change_pct": change_pct,
                "sparkline": [round(c, 2) for c in closes],
            }
        except Exception:
            out[label] = {"price": None, "display_price": None, "day_high": None, "day_low": None, "unit": "USD", "change_pct": None, "sparkline": []}

    return jsonify(out)


# Search queries for commodity-specific news (used by the click-to-expand
# popup in the Commodities section).
COMMODITY_NEWS_QUERIES = {
    "Gold": "gold price India MCX gold rate",
    "Silver": "silver price India MCX silver rate",
    "Crude Oil (WTI)": "crude oil price WTI India",
    "Crude Oil (Brent)": "Brent crude oil price India",
    "Natural Gas": "natural gas price India",
    "Wheat": "wheat price India agriculture",
    "Rice": "rice price India agriculture export",
    "Sugar": "sugar price India NCDEX",
}


@app.route("/api/commodities/<name>/news")
@cache.cached(timeout=3600)
def commodity_news(name):
    query = COMMODITY_NEWS_QUERIES.get(name, f"{name} price India")
    err, items = fetch_news(query, limit=5)
    if err:
        return jsonify(err)

    api_key = get_anthropic_key()
    items = generate_news_briefs(
        items, api_key,
        topic_hint=f"{name} prices and what drives them, for an Indian audience",
        word_count=100,
    )
    return jsonify({"commodity": name, "news": items})


@app.route("/api/exchange-rates")
@cache.cached(timeout=3600)
def exchange_rates():
    try:
        resp = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8)
        data = resp.json()
        rates = data.get("rates", {})
        return jsonify({
            "USD_INR": rates.get("INR"),
            "EUR_INR": round(rates.get("INR", 0) / rates.get("EUR", 1), 2) if rates.get("EUR") else None,
            "GBP_INR": round(rates.get("INR", 0) / rates.get("GBP", 1), 2) if rates.get("GBP") else None,
            "updated": data.get("time_last_update_utc"),
        })
    except Exception as e:
        return jsonify({"error": f"Failed to fetch exchange rates: {e}"})


NEWS_CATEGORY_QUERIES = {
    "geo": "India trade tariff war oil China US relations economy",
    "policy": "India government policy announcement budget ministry",
    "business": "India business earnings corporate news",
    "tax": "India income tax GST budget tax news",
    "market": "India stock market Nifty Sensex news",
    "inflation": "India inflation CPI WPI prices food fuel RBI",
    "macro": "India GDP growth economy IIP PMI manufacturing data",
}

NEWS_CATEGORY_TOPIC_HINTS = {
    "geo": "geopolitical events and their impact on Indian markets",
    "policy": "Indian government policy and regulatory announcements",
    "business": "Indian corporate business and earnings news",
    "tax": "Indian income tax, GST and budget-related news",
    "market": "the Indian stock market (Nifty/Sensex)",
    "inflation": "India's inflation trends (CPI/WPI) and cost of living",
    "macro": "India's macroeconomic indicators (GDP, IIP, PMI)",
}

# Per-category: how many stories to fetch, and roughly how many words each
# AI-generated brief should be.
NEWS_CATEGORY_CONFIG = {
    "geo": {"limit": 20, "words": 100},
    "policy": {"limit": 10, "words": 100},
    "business": {"limit": 20, "words": 100},
    "tax": {"limit": 10, "words": 100},
    "market": {"limit": 8, "words": 100},
    "inflation": {"limit": 10, "words": 100},
    "macro": {"limit": 10, "words": 100},
}


@app.route("/api/news/<category>")
@cache.cached(timeout=3600)
def news_by_category(category):
    query = NEWS_CATEGORY_QUERIES.get(category, f"India {category} news")
    config = NEWS_CATEGORY_CONFIG.get(category, {"limit": 8, "words": 150})
    err, items = fetch_news(query, limit=config["limit"])
    if err:
        return jsonify(err)

    api_key = get_anthropic_key()

    # For the geopolitical feed, tag each story with an AI-generated impact label.
    if category == "geo" and api_key:
        system_prompt = (
            "You are a markets analyst. For each news headline given, classify its "
            "likely short-term impact on Indian financial markets as one of "
            "'positive', 'negative', or 'neutral', and give a one-line reason. "
            "Return ONLY valid JSON: a list of objects with keys 'impact' and 'reason', "
            "in the same order as the input headlines."
        )
        headlines = [it["title"] for it in items]
        ai_result, ai_err = call_claude_haiku(
            system_prompt, json.dumps(headlines), api_key,
            max_tokens=min(8192, max(1024, len(items) * 100)),
        )
        if not ai_err and isinstance(ai_result, list):
            for i, tag in enumerate(ai_result):
                if i < len(items):
                    items[i]["impact"] = tag.get("impact", "neutral")
                    items[i]["impact_reason"] = tag.get("reason", "")

    # Generate short, original briefs for every category so the app doesn't
    # just redirect users to (and reproduce) external articles.
    topic_hint = NEWS_CATEGORY_TOPIC_HINTS.get(category, "Indian financial news")
    items = generate_news_briefs(items, api_key, topic_hint=topic_hint, word_count=config["words"])

    return jsonify({"category": category, "news": items})


@app.route("/api/earnings/calendar")
@cache.cached(timeout=3600)
def earnings_calendar():
    out = []
    today = datetime.now()
    for s in NIFTY50_SYMBOLS:
        try:
            cal = yf_ticker(f"{s}.NS").calendar
            earnings_dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
            if not earnings_dates:
                continue
            for d in earnings_dates:
                if isinstance(d, datetime):
                    d_date = d
                else:
                    d_date = datetime.combine(d, datetime.min.time())
                if today <= d_date <= today + timedelta(days=7):
                    out.append({"symbol": s, "date": d_date.strftime("%Y-%m-%d")})
        except Exception:
            continue
    out.sort(key=lambda x: x["date"])
    return jsonify({"calendar": out})


# ---------------------------------------------------------------------------
# IPO showcase
#
# IMPORTANT: there is no free, reliable API for *upcoming* IPOs with verified
# financials, price bands, or lot sizes. To keep this section useful and
# reasonably current without fabricating data, we:
#   1. Pull recent real news articles about open/upcoming Indian IPOs
#      (NewsAPI, falling back to Google News RSS).
#   2. Ask Claude to identify the distinct companies mentioned and extract
#      whatever concrete details (price band, lot size, dates, issue size)
#      are present in those articles.
#   3. Claude fills in an educational company overview plus green/red flags
#      based on its general knowledge, clearly distinguishing "from news"
#      vs "general analysis", and we tell the user to verify on the official
#      RHP/DRHP and exchange websites before investing.
# ---------------------------------------------------------------------------


@app.route("/api/ipo/showcase")
@cache.cached(timeout=10800)
def ipo_showcase():
    api_key = get_anthropic_key()
    note = (
        "Live IPO data (price band, lot size, dates) is extracted from recent "
        "news articles and may be incomplete or out of date. Company overviews "
        "and green/red flags are AI-generated for education only. Always verify "
        "exact details in the official prospectus (RHP/DRHP) and on the NSE/BSE "
        "websites before investing."
    )

    if not api_key:
        return jsonify({"note": note, "ipos": [], "error": "No Anthropic API key configured. Add one in Settings to generate IPO overviews."})

    # Step 1: gather real, recent news about open/upcoming IPOs in India
    err, items = fetch_news(
        "upcoming IPO India price band lot size mainboard", limit=15
    )
    if err or not items:
        err2, items2 = fetch_news("IPO opens India subscription GMP", limit=15)
        if not err2:
            items = items2

    if not items:
        return jsonify({"note": note, "ipos": [], "error": "Could not fetch IPO news right now. Try again later."})

    news_context = [
        {
            "title": it.get("title", ""),
            "description": it.get("description", ""),
            "source": it.get("source", ""),
            "published": it.get("published", ""),
            "link": it.get("link", ""),
        }
        for it in items
    ]

    # Step 2: ask Claude to identify distinct companies and structure the data
    system_prompt = (
        "You are a financial educator writing for an Indian retail-investor app. "
        "You are given a list of recent news headlines/snippets about Indian IPOs "
        "(mainboard, currently open or upcoming in the next few weeks). "
        "Identify up to 5 DISTINCT companies with the most concrete information. "
        "Prefer companies whose price band, lot size, or open/close dates are "
        "mentioned in the snippets. Skip duplicates and SME-only IPOs if better "
        "mainboard options are available. "
        "For each company, return an object with these exact keys: "
        "'name' (company name), "
        "'sector' (one short phrase), "
        "'status' (one of 'Open', 'Upcoming', or 'Recently Listed', based on the news), "
        "'price_band' (string like '₹163 - ₹172 per share', or 'Not yet announced' if unknown), "
        "'lot_size' (number of shares per lot as a string, or 'Not yet announced'), "
        "'min_investment' (approx retail minimum investment in INR as a string, "
        "calculated as price_band upper end x lot_size if both are known, else "
        "'Not yet announced'), "
        "'issue_dates' (string like 'Opens 23 Apr - Closes 27 Apr 2026', or 'TBA'), "
        "'issue_size' (string like '₹74 Cr', or 'Not disclosed'), "
        "'about' (an ORIGINAL ~120 word plain-English description of what the "
        "company does and why it's going public, based on the news and your "
        "general knowledge), "
        "'green_flags' (exactly 5 short bullet points - genuine positives), "
        "'red_flags' (exactly 5 short bullet points - genuine risks or concerns), "
        "'source_note' (1 short sentence noting which details came from the news "
        "vs general context, e.g. 'Price band and dates from recent news; "
        "company overview and flags are general analysis.'). "
        "Be balanced and educational, not promotional. Do not invent specific "
        "price bands or lot sizes not supported by the news snippets - use "
        "'Not yet announced' instead. "
        "Return ONLY a valid JSON array of these objects, with no extra text."
    )

    result, err = call_claude_haiku(
        system_prompt, json.dumps(news_context, default=str), api_key, max_tokens=8192
    )

    if err or not isinstance(result, list):
        return jsonify({"note": note, "ipos": [], "error": err or "Could not generate IPO data."})

    return jsonify({"note": note, "ipos": result})


# ---------------------------------------------------------------------------
# Mutual Funds — top performers
#
# Uses MFAPI.in (https://www.mfapi.in), a free, no-key API for Indian mutual
# fund NAV history sourced from AMFI. We track a curated list of well-known
# Direct-Growth schemes across categories, resolve each to its scheme code via
# the search endpoint, pull NAV history, and compute 1-year and 3-year returns
# ourselves (MFAPI only gives raw NAV history, not pre-computed returns).
# ---------------------------------------------------------------------------

MFAPI_BASE = "https://api.mfapi.in/mf"

MUTUAL_FUND_WATCHLIST = [
    {"query": "Parag Parikh Flexi Cap Fund", "category": "Flexi Cap"},
    {"query": "Quant Small Cap Fund", "category": "Small Cap"},
    {"query": "Nippon India Small Cap Fund", "category": "Small Cap"},
    {"query": "SBI Small Cap Fund", "category": "Small Cap"},
    {"query": "ICICI Prudential Bluechip Fund", "category": "Large Cap"},
    {"query": "Mirae Asset Large Cap Fund", "category": "Large Cap"},
    {"query": "HDFC Mid-Cap Opportunities Fund", "category": "Mid Cap"},
    {"query": "Kotak Emerging Equity Fund", "category": "Mid Cap"},
    {"query": "Axis Small Cap Fund", "category": "Small Cap"},
    {"query": "DSP Midcap Fund", "category": "Mid Cap"},
    {"query": "Motilal Oswal Midcap Fund", "category": "Mid Cap"},
    {"query": "Canara Robeco Small Cap Fund", "category": "Small Cap"},
    {"query": "HDFC Flexi Cap Fund", "category": "Flexi Cap"},
    {"query": "Tata Small Cap Fund", "category": "Small Cap"},
    {"query": "UTI Nifty 50 Index Fund", "category": "Index Fund"},
    {"query": "Quant Mid Cap Fund", "category": "Mid Cap"},
    {"query": "Edelweiss Mid Cap Fund", "category": "Mid Cap"},
    {"query": "Bandhan Small Cap Fund", "category": "Small Cap"},
    {"query": "ICICI Prudential Technology Fund", "category": "Sectoral - Tech"},
    {"query": "Nippon India Pharma Fund", "category": "Sectoral - Pharma"},
    {"query": "SBI Contra Fund", "category": "Contra"},
    {"query": "Invesco India Mid Cap Fund", "category": "Mid Cap"},
    {"query": "ICICI Prudential Flexicap Fund", "category": "Flexi Cap"},
    {"query": "Franklin India Flexi Cap Fund", "category": "Flexi Cap"},
    {"query": "Mirae Asset Midcap Fund", "category": "Mid Cap"},
    {"query": "JM Flexicap Fund", "category": "Flexi Cap"},
    {"query": "Bank of India Small Cap Fund", "category": "Small Cap"},
    {"query": "HSBC Small Cap Fund", "category": "Small Cap"},
]


def mfapi_search(query: str) -> list:
    """Search MFAPI.in for scheme name/code matches."""
    try:
        resp = requests.get(f"{MFAPI_BASE}/search", params={"q": query}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


def pick_direct_growth_scheme(matches: list, base_query: str) -> dict | None:
    """From search results, prefer a Direct Plan / Growth option (not IDCW)."""
    candidates = []
    for m in matches:
        name = (m.get("schemeName") or "").lower()
        if "direct" in name and "growth" in name and "idcw" not in name and "dividend" not in name:
            candidates.append(m)

    if not candidates:
        # fall back to any growth-option scheme, even regular plan
        for m in matches:
            name = (m.get("schemeName") or "").lower()
            if "growth" in name and "idcw" not in name and "dividend" not in name:
                candidates.append(m)

    if not candidates:
        return matches[0] if matches else None

    # Prefer the shortest matching name (tends to be the "plain" plan,
    # avoiding niche variants like "- Series 2" etc.)
    candidates.sort(key=lambda m: len(m.get("schemeName") or ""))
    return candidates[0]


def mfapi_nav_history(scheme_code) -> dict | None:
    """Fetch full NAV history for a scheme code."""
    try:
        resp = requests.get(f"{MFAPI_BASE}/{scheme_code}", timeout=8)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "SUCCESS" and data.get("data"):
            return data
        return None
    except Exception:
        return None


def find_nav_near(nav_data: list, target_date: datetime) -> float | None:
    """nav_data is sorted newest-first; return the first NAV on/before target_date."""
    for entry in nav_data:
        try:
            entry_date = datetime.strptime(entry["date"], "%d-%m-%Y")
        except Exception:
            continue
        if entry_date <= target_date:
            try:
                return float(entry["nav"])
            except (ValueError, TypeError):
                return None
    return None


def fetch_one_fund(fund: dict) -> dict | None:
    """Resolve a curated fund entry to its scheme code, fetch NAV history,
    and compute 1Y / 3Y returns. Returns None if anything is unavailable."""
    matches = mfapi_search(fund["query"])
    if not matches:
        return None

    scheme = pick_direct_growth_scheme(matches, fund["query"])
    if not scheme:
        return None

    history = mfapi_nav_history(scheme.get("schemeCode"))
    if not history:
        return None

    nav_data = history.get("data") or []
    if len(nav_data) < 2:
        return None

    try:
        latest_nav = float(nav_data[0]["nav"])
        latest_date = datetime.strptime(nav_data[0]["date"], "%d-%m-%Y")
    except Exception:
        return None

    nav_1y = find_nav_near(nav_data, latest_date - timedelta(days=365))
    nav_3y = find_nav_near(nav_data, latest_date - timedelta(days=3 * 365))

    return_1y = round((latest_nav - nav_1y) / nav_1y * 100, 2) if nav_1y else None
    return_3y_cagr = round((((latest_nav / nav_3y) ** (1 / 3)) - 1) * 100, 2) if nav_3y and nav_3y > 0 else None

    meta = history.get("meta", {})

    return {
        "scheme_code": scheme.get("schemeCode"),
        "name": meta.get("scheme_name") or scheme.get("schemeName"),
        "fund_house": meta.get("fund_house"),
        "category": fund["category"],
        "nav": latest_nav,
        "nav_date": nav_data[0]["date"],
        "return_1y": return_1y,
        "return_3y_cagr": return_3y_cagr,
    }


@app.route("/api/mutualfunds/top")
@cache.cached(timeout=21600)
def mutual_funds_top():
    """Top performing direct-growth mutual funds by 1-year return.

    Each fund requires 2 external HTTP calls (search + NAV history). Fetched
    in parallel via a thread pool so the whole request stays well under
    gunicorn's worker timeout even with ~28 funds tracked. We track more
    funds than needed (28) since some lookups inevitably fail to resolve on
    MFAPI, ensuring we still end up with 10 valid results.
    """
    results = []

    with ThreadPoolExecutor(max_workers=14) as executor:
        futures = [executor.submit(fetch_one_fund, fund) for fund in MUTUAL_FUND_WATCHLIST]
        try:
            for future in as_completed(futures, timeout=45):
                try:
                    fund_result = future.result()
                except Exception:
                    fund_result = None
                if fund_result:
                    results.append(fund_result)
        except FuturesTimeoutError:
            # Use whatever completed within the time budget; any
            # still-running futures are abandoned (daemon threads).
            for future in futures:
                if future.done() and not future.cancelled():
                    try:
                        fund_result = future.result()
                    except Exception:
                        fund_result = None
                    if fund_result and fund_result not in results:
                        results.append(fund_result)

    # Sort by 1-year return (funds with missing 1Y data go last)
    results.sort(key=lambda r: (r["return_1y"] is None, -(r["return_1y"] or 0)))

    return jsonify({
        "funds": results[:10],
        "note": (
            "NAV and return data sourced from AMFI via MFAPI.in (free, no key required). "
            "Returns shown are point-to-point (1-year absolute change) and 3-year CAGR based "
            "on Direct Growth plan NAVs. Past performance does not guarantee future returns — "
            "verify on the fund house website or AMFI before investing."
        ),
    })


@app.route("/api/mutualfunds/<int:scheme_code>/detail")
@cache.cached(timeout=21600)
def mutual_fund_detail(scheme_code):
    """NAV history (for a chart) plus an AI-generated overview of what this
    type of fund typically holds. There's no free API for a fund's actual
    current portfolio holdings, so the "portfolio" section is general
    educational guidance based on the fund's category/name - clearly
    labelled as such, not real-time holdings data."""
    history = mfapi_nav_history(scheme_code)
    if not history:
        return jsonify({"error": "Could not fetch fund details."})

    nav_data = history.get("data") or []
    meta = history.get("meta", {})

    # nav_data is newest-first; take the last ~365 entries and reverse to
    # chronological order for charting.
    recent = list(reversed(nav_data[:370]))
    dates = [d["date"] for d in recent]
    navs = []
    for d in recent:
        try:
            navs.append(float(d["nav"]))
        except (ValueError, TypeError, KeyError):
            navs.append(None)

    result = {
        "scheme_code": scheme_code,
        "name": meta.get("scheme_name"),
        "fund_house": meta.get("fund_house"),
        "scheme_category": meta.get("scheme_category"),
        "dates": dates,
        "navs": navs,
    }

    api_key = get_anthropic_key()
    if api_key:
        system_prompt = (
            "You are a financial educator writing for an Indian retail-investor app. "
            "Given a mutual fund's name, fund house, and scheme category, write a brief "
            "educational profile. Return ONLY a JSON object with these keys: "
            "'about' (~80 words on what this type of fund typically invests in and its "
            "general strategy, based on its name/category), "
            "'typical_holdings' (a list of 4-6 short strings naming the KINDS of "
            "sectors/companies such a fund typically holds, e.g. 'Large private banks', "
            "'IT services majors' - general patterns for this category, not real-time data), "
            "'risk_level' (one of 'Low', 'Moderate', 'High', 'Very High'), "
            "'suitable_for' (~30 words on what kind of investor/goal this fund category suits). "
            "Be educational and general - do not claim to know the fund's actual current "
            "holdings. Return ONLY the JSON object, no extra text."
        )
        fund_context = {
            "name": meta.get("scheme_name"),
            "fund_house": meta.get("fund_house"),
            "scheme_category": meta.get("scheme_category"),
        }
        ai_result, err = call_claude_haiku(system_prompt, json.dumps(fund_context), api_key, max_tokens=600)
        if not err and isinstance(ai_result, dict):
            result["profile"] = ai_result

    return jsonify(result)




@app.route("/")
def index():
    return render_template("index.html")


@app.route("/robots.txt")
def robots_txt():
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Sitemap: https://financeiq-1sv6.onrender.com/sitemap.xml\n",
        200,
        {"Content-Type": "text/plain"},
    )


@app.route("/sitemap.xml")
def sitemap_xml():
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        '  <url><loc>https://financeiq-1sv6.onrender.com/</loc></url>\n'
        '</urlset>\n'
    )
    return (xml, 200, {"Content-Type": "application/xml"})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
