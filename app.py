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
from flask_compress import Compress

import yfinance as yf

import threading

try:
    import pyotp
    from SmartApi import SmartConnect
    SMARTAPI_AVAILABLE = True
except Exception:
    SMARTAPI_AVAILABLE = False

app = Flask(__name__)
CORS(app)
Compress(app)

cache = Cache(app, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300})

# ---------------------------------------------------------------------------
# Angel One SmartAPI — primary real-time data source for NSE quotes.
# Falls back to yfinance/Finnhub automatically if unavailable or unconfigured.
# ---------------------------------------------------------------------------


class AngelOneSession:
    def __init__(self):
        self.api = None
        self.auth_token = None
        self.feed_token = None
        self.last_login = None
        self._lock = threading.Lock()
        self.enabled = SMARTAPI_AVAILABLE and all([
            os.environ.get("ANGEL_API_KEY"),
            os.environ.get("ANGEL_CLIENT_ID"),
            os.environ.get("ANGEL_PASSWORD"),
            os.environ.get("ANGEL_TOTP_SECRET"),
        ])

    def login(self):
        if not self.enabled:
            print("Angel One: credentials not configured")
            return False
        try:
            totp = pyotp.TOTP(os.environ["ANGEL_TOTP_SECRET"]).now()
            self.api = SmartConnect(api_key=os.environ["ANGEL_API_KEY"])
            data = self.api.generateSession(
                os.environ["ANGEL_CLIENT_ID"],
                os.environ["ANGEL_PASSWORD"],
                totp
            )
            if data and data.get("status"):
                self.auth_token = data["data"]["jwtToken"]
                self.feed_token = self.api.getfeedToken()
                self.last_login = datetime.now()
                print("Angel One: login successful")
                return True
            print(f"Angel One: login failed: {data}")
            return False
        except Exception as e:
            print(f"Angel One: login error: {e}")
            return False

    def ensure_session(self):
        with self._lock:
            if not self.enabled:
                return False
            if not self.last_login:
                return self.login()
            if (datetime.now() - self.last_login).total_seconds() > 82800:
                return self.login()
            return self.api is not None

    def get_quote(self, exchange_tokens: dict) -> list:
        if not self.ensure_session():
            return []
        try:
            data = self.api.getMarketData("QUOTE", exchange_tokens)
            if data and data.get("status") and data.get("data"):
                return data["data"].get("fetched", [])
        except Exception as e:
            print(f"Angel getMarketData error: {e}")
            self.last_login = None
        return []

    def get_ltp(self, exchange: str, token: str):
        if not self.ensure_session():
            return None
        try:
            data = self.api.ltpData(exchange, "", token)
            if data and data.get("status"):
                return data["data"].get("ltp")
        except Exception as e:
            print(f"Angel LTP error: {e}")
            self.last_login = None
        return None

    def get_historical(self, token, exchange, interval, from_date, to_date):
        if not self.ensure_session():
            return []
        try:
            params = {
                "exchange": exchange,
                "symboltoken": token,
                "interval": interval,
                "fromdate": from_date,
                "todate": to_date,
            }
            data = self.api.getCandleData(params)
            if data and data.get("status") and data.get("data"):
                return data["data"]
        except Exception as e:
            print(f"Angel historical error: {e}")
        return []

    def search_scrip(self, query: str, exchange: str = "NSE") -> list:
        if not self.ensure_session():
            return []
        try:
            data = self.api.searchScrip(exchange, query)
            if data and data.get("status"):
                return data.get("data") or []
        except Exception as e:
            print(f"Angel searchScrip error: {e}")
        return []


angel = AngelOneSession()


def _angel_init():
    time.sleep(5)
    angel.login()


threading.Thread(target=_angel_init, daemon=True).start()

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


from functools import lru_cache

@lru_cache(maxsize=512)
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
    "Auto": ["MARUTI", "M&M", "BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO", "ASHOKLEY", "TVSMOTOR", "TIINDIA"],
    "Bank": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK", "BANKBARODA", "PNB"],
    "IT": ["TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "MPHASIS", "PERSISTENT", "COFORGE"],
    "Pharma": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "LUPIN", "AUROPHARMA", "TORNTPHARM", "ZYDUSLIFE"],
    "FMCG": ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "DABUR", "TATACONSUM", "GODREJCP", "MARICO"],
    "Metal": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "JINDALSTEL", "SAIL", "NMDC", "COALINDIA"],
    "Realty": ["DLF", "GODREJPROP", "OBEROIRLTY", "PHOENIXLTD", "PRESTIGE", "BRIGADE", "SOBHA", "LODHA"],
    "Energy": ["RELIANCE", "ONGC", "NTPC", "POWERGRID", "ADANIGREEN", "TATAPOWER", "BPCL", "IOC"],
    "Infra": ["LT", "ADANIPORTS", "IRB", "NBCC", "NCC", "KEC", "RVNL", "PFC"],
    "Media": ["ZEEL", "SUNTV", "PVRINOX", "NETWORK18", "DISHTV", "SAREGAMA", "NAZARA", "TIPSINDLTD"],
    "Defence": ["HAL", "BEL", "BDL", "MAZDOCK", "COCHINSHIP", "SOLARINDS", "BEML", "DATAPATTNS"],
    "Water": ["WABAG", "CLEAN", "ELGIEQUIP", "THERMAX", "KIRLOSBROS", "JASH", "EPIGRAL", "IONEXCHANG"],
    "Oil & Gas": ["RELIANCE", "ONGC", "BPCL", "IOC", "GAIL", "PETRONET", "OIL", "MRPL"],
    "Consumer Durables": ["VOLTAS", "HAVELLS", "BLUESTARCO", "CROMPTON", "VGUARD", "ORIENTELEC", "SYMPHONY", "AMBER"],
    "Semiconductor": ["DIXON", "KAYNES", "SYRMA", "PGEL", "MOSCHIP", "ASTRA", "ZENTEC", "GRAVITA"],
    "Telecom": ["BHARTIARTL", "IDEA", "TATACOMM", "RAILTEL", "HFCL", "STLTECH", "TTML", "GTLINFRA"],
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
    "USD/INR": "USDINR=X",
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
# Angel One instrument tokens — NSE symbol -> (symboltoken, exchange).
# Covers Nifty 50 + commonly viewed mid/small-caps on this site. Symbols not
# in this map are resolved on demand via Angel's searchScrip API.
# ---------------------------------------------------------------------------
ANGEL_TOKENS = {
    "RELIANCE": ("2885", "NSE"),
    "TCS": ("11536", "NSE"),
    "HDFCBANK": ("1333", "NSE"),
    "ICICIBANK": ("4963", "NSE"),
    "INFY": ("1594", "NSE"),
    "SBIN": ("3045", "NSE"),
    "BHARTIARTL": ("10604", "NSE"),
    "ITC": ("1660", "NSE"),
    "LT": ("11483", "NSE"),
    "KOTAKBANK": ("1922", "NSE"),
    "AXISBANK": ("5900", "NSE"),
    "HINDUNILVR": ("1394", "NSE"),
    "BAJFINANCE": ("317", "NSE"),
    "MARUTI": ("10999", "NSE"),
    "TITAN": ("3506", "NSE"),
    "SUNPHARMA": ("3351", "NSE"),
    "WIPRO": ("3787", "NSE"),
    "HCLTECH": ("7229", "NSE"),
    "TATAMOTORS": ("3456", "NSE"),
    "ONGC": ("2475", "NSE"),
    "NTPC": ("11630", "NSE"),
    "POWERGRID": ("14977", "NSE"),
    "COALINDIA": ("20374", "NSE"),
    "TATASTEEL": ("3499", "NSE"),
    "ADANIPORTS": ("15083", "NSE"),
    "M&M": ("2031", "NSE"),
    "NESTLEIND": ("17963", "NSE"),
    "BAJAJ-AUTO": ("16669", "NSE"),
    "EICHERMOT": ("910", "NSE"),
    "HEROMOTOCO": ("1348", "NSE"),
    "ULTRACEMCO": ("11532", "NSE"),
    "TECHM": ("13538", "NSE"),
    "ASIANPAINT": ("236", "NSE"),
    "INDUSINDBK": ("5258", "NSE"),
    "GRASIM": ("1232", "NSE"),
    "BAJAJFINSV": ("16675", "NSE"),
    "ADANIENT": ("25", "NSE"),
    "DIVISLAB": ("10940", "NSE"),
    "CIPLA": ("694", "NSE"),
    "DRREDDY": ("881", "NSE"),
    "JSWSTEEL": ("11723", "NSE"),
    "HINDALCO": ("1363", "NSE"),
    "TATACONSUM": ("3432", "NSE"),
    "APOLLOHOSP": ("157", "NSE"),
    "BRITANNIA": ("547", "NSE"),
    "BPCL": ("526", "NSE"),
    "BANKBARODA": ("4668", "NSE"),
    "PNB": ("10666", "NSE"),
    "FEDERALBNK": ("1023", "NSE"),
    "AUBANK": ("21238", "NSE"),
    "YESBANK": ("11915", "NSE"),
    "IDFCFIRSTB": ("11652", "NSE"),
    "LTIM": ("17818", "NSE"),
    "MPHASIS": ("4503", "NSE"),
    "PERSISTENT": ("4338", "NSE"),
    "COFORGE": ("10626", "NSE"),
    "TATAELXSI": ("3505", "NSE"),
    "OFSS": ("10738", "NSE"),
    "LUPIN": ("10440", "NSE"),
    "AUROPHARMA": ("275", "NSE"),
    "TORNTPHARM": ("3526", "NSE"),
    "ZYDUSLIFE": ("7929", "NSE"),
    "BIOCON": ("11373", "NSE"),
    "TVSMOTOR": ("3986", "NSE"),
    "ASHOKLEY": ("212", "NSE"),
    "BALKRISIND": ("335", "NSE"),
    "BOSCHLTD": ("2181", "NSE"),
    "DABUR": ("772", "NSE"),
    "GODREJCP": ("10099", "NSE"),
    "MARICO": ("4067", "NSE"),
    "COLPAL": ("742", "NSE"),
    "DLF": ("14732", "NSE"),
    "GODREJPROP": ("17875", "NSE"),
    "OBEROIRLTY": ("20141", "NSE"),
    "PHOENIXLTD": ("3911", "NSE"),
    "IOC": ("1624", "NSE"),
    "GAIL": ("1209", "NSE"),
    "PETRONET": ("11351", "NSE"),
    "ADANIGREEN": ("21866", "NSE"),
    "TATAPOWER": ("3426", "NSE"),
    "VEDL": ("3063", "NSE"),
    "JINDALSTEL": ("15355", "NSE"),
    "SAIL": ("2963", "NSE"),
    "NMDC": ("15332", "NSE"),
    "IRB": ("14995", "NSE"),
    "NBCC": ("20263", "NSE"),
    "NCC": ("14978", "NSE"),
    "PFC": ("14299", "NSE"),
    "RECLTD": ("20286", "NSE"),
    "HAL": ("2303", "NSE"),
    "BEL": ("383", "NSE"),
    "MAZDOCK": ("21757", "NSE"),
    "COCHINSHIP": ("11259", "NSE"),
    "SOLARINDS": ("14149", "NSE"),
    "BEML": ("384", "NSE"),
    "ZEEL": ("3812", "NSE"),
    "SUNTV": ("3366", "NSE"),
    "SAREGAMA": ("2975", "NSE"),
    "IDEA": ("14366", "NSE"),
    "HFCL": ("1358", "NSE"),
    "DIXON": ("13538", "NSE"),
    "KAYNES": ("21866", "NSE"),
    "VOLTAS": ("3575", "NSE"),
    "HAVELLS": ("13913", "NSE"),
    "WABAG": ("3689", "NSE"),
    "ELGIEQUIP": ("914", "NSE"),
    "THERMAX": ("3484", "NSE"),
    "NIFTY50IDX": ("99926000", "NSE"),
    "BANKNIFTY": ("99926009", "NSE"),
}

ANGEL_TOKEN_TO_SYMBOL = {v[0]: k for k, v in ANGEL_TOKENS.items()}


def get_angel_token(symbol: str):
    symbol = symbol.upper().strip()
    if symbol in ANGEL_TOKENS:
        return ANGEL_TOKENS[symbol]
    if angel.enabled and angel.ensure_session():
        try:
            results = angel.search_scrip(symbol)
            for r in results:
                if r.get("tradingsymbol", "").upper() == symbol:
                    token = r.get("symboltoken")
                    exchange = r.get("exch_seg", "NSE")
                    if token:
                        ANGEL_TOKENS[symbol] = (token, exchange)
                        ANGEL_TOKEN_TO_SYMBOL[token] = symbol
                        return (token, exchange)
        except Exception:
            pass
    return None


def get_live_quote(symbol: str):
    """Tiered live-quote lookup: Angel One (real-time) -> yfinance fast_info
    -> yfinance history. Returns a dict or None if all tiers fail."""
    symbol = symbol.upper().strip()

    # Tier 1: Angel One real-time
    if angel.enabled:
        token_info = get_angel_token(symbol)
        if token_info:
            token, exchange = token_info
            try:
                fetched = angel.get_quote({exchange: [token]})
                for item in fetched:
                    if item.get("symbolToken") == token:
                        ltp = item.get("ltp") or item.get("close")
                        close = item.get("close") or ltp
                        if ltp:
                            change_pct = round((float(ltp)-float(close))/float(close)*100, 2) if close and float(close) != 0 and float(ltp) != float(close) else 0
                            return {
                                "symbol": symbol,
                                "price": float(ltp),
                                "change": round(float(ltp)-float(close), 2) if close else 0,
                                "change_pct": change_pct,
                                "open": item.get("open"),
                                "high": item.get("high"),
                                "low": item.get("low"),
                                "prev_close": close,
                                "volume": item.get("tradeVolume"),
                                "upper_circuit": item.get("upperCircuit"),
                                "lower_circuit": item.get("lowerCircuit"),
                                "week_52_high": item.get("52WeekHigh"),
                                "week_52_low": item.get("52WeekLow"),
                                "source": "Angel One",
                                "real_time": True,
                            }
            except Exception as e:
                print(f"Angel quote failed for {symbol}: {e}")

    # Tier 2: yfinance fast_info
    try:
        fi = yf_ticker(f"{symbol}.NS").fast_info
        price = fi.get("lastPrice")
        prev = fi.get("previousClose")
        if price:
            return {
                "symbol": symbol,
                "price": round(float(price), 2),
                "change": round(float(price)-float(prev), 2) if prev else None,
                "change_pct": round((float(price)-float(prev))/float(prev)*100, 2) if prev else None,
                "high": fi.get("dayHigh"),
                "low": fi.get("dayLow"),
                "prev_close": prev,
                "week_52_high": fi.get("yearHigh"),
                "week_52_low": fi.get("yearLow"),
                "source": "yfinance",
                "real_time": False,
            }
    except Exception:
        pass

    # Tier 3: yfinance history
    try:
        hist = yf_ticker(f"{symbol}.NS").history(period="5d")
        if hist is not None and not hist.empty:
            closes = hist["Close"].dropna()
            if len(closes) >= 1:
                price = float(closes.iloc[-1])
                prev = float(closes.iloc[-2]) if len(closes) >= 2 else None
                return {
                    "symbol": symbol,
                    "price": round(price, 2),
                    "change_pct": round((price-prev)/prev*100, 2) if prev else None,
                    "source": "yfinance-history",
                    "real_time": False,
                }
    except Exception:
        pass
    return None


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


def parse_news_date(date_str: str) -> datetime:
    """Best-effort parse of a news item's published date into a tz-aware
    datetime, handling both RFC822 (Google News RSS) and ISO 8601
    (NewsAPI / Yahoo Finance) formats. Falls back to the epoch start so
    unparseable dates sort last rather than crashing the sort."""
    if not date_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    return datetime.min.replace(tzinfo=timezone.utc)


def fetch_yahoo_finance_news(yf_symbol: str, limit: int = 5) -> list:
    """Free, no-key stock news straight from Yahoo Finance via yfinance.
    Often fresher than NewsAPI/Google News for individual stocks since it
    reflects Yahoo's own news feed for that ticker."""
    try:
        raw = yf_ticker(yf_symbol).get_news(count=limit)
    except Exception:
        return []

    items = []
    for article in raw or []:
        # Newer yfinance versions nest fields under "content"; older
        # versions return them at the top level. Support both.
        content = article.get("content") if isinstance(article.get("content"), dict) else article

        title = content.get("title") or ""
        if not title:
            continue

        provider = content.get("provider") or {}
        source = (
            provider.get("displayName")
            if isinstance(provider, dict) else None
        ) or content.get("publisher") or "Yahoo Finance"

        canonical = content.get("canonicalUrl")
        link = (
            canonical.get("url") if isinstance(canonical, dict) else None
        ) or content.get("link") or ""

        published = content.get("pubDate") or content.get("displayTime") or ""
        if not published and content.get("providerPublishTime"):
            try:
                published = datetime.fromtimestamp(
                    content["providerPublishTime"], tz=timezone.utc
                ).isoformat()
            except Exception:
                published = ""

        items.append({
            "title": title,
            "source": source,
            "link": link,
            "published": published,
            "description": content.get("summary") or content.get("description") or "",
        })

    return items[:limit]


def fetch_google_news_rss(query: str, limit: int = 3, recency: str = "7d"):
    """Fetch and parse Google News RSS for a query. No API key required.

    Uses the `after:YYYY-MM-DD` operator (more reliable than `when:Nd`) to
    force Google to return results published after a specific date.
    `recency` accepts "7d", "14d", "30d", or None (no date filter).
    Sorts by actual publish date so the freshest stories appear first.
    """
    from datetime import date as _date
    recency_filter = ""
    if recency:
        try:
            days = int(recency.rstrip("d"))
            cutoff = (_date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
            recency_filter = f" after:{cutoff}"
        except Exception:
            recency_filter = ""
    full_query = query + recency_filter
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

            sort_key = parse_news_date(pub_date)
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

        # If the recency filter returned too few/no results, progressively
        # widen the window (7d -> 14d -> 30d) before giving up entirely.
        if not items and recency:
            next_recency = {"7d": "14d", "14d": "30d", "30d": None}.get(recency)
            return fetch_google_news_rss(query, limit=limit, recency=next_recency)

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

    Also performs relevance filtering: if a headline is not genuinely
    relevant to `topic_hint` / Indian financial markets, or isn't a real
    news story (forum posts, exam-prep listicles, generic global content
    with no India angle, etc.), the AI returns `null` for that entry and
    the item is DROPPED from the returned list entirely - rather than
    showing the user a meta-commentary about why it couldn't write about it.

    Returns the filtered items list with an added 'article' field on each
    item (or the original items unchanged if no API key / on error).
    """
    if not items or not api_key:
        return items

    system_prompt = (
        "You are a financial news editor and writer for an Indian retail-investor app, "
        "known for making market news genuinely engaging without sacrificing substance. "
        f"For each headline (and description, if given) below, first decide if it is "
        f"GENUINELY relevant: it must be real financial/business/economic/policy news "
        + (f"specifically connected to {topic_hint}, " if topic_hint else "specifically connected to India, ")
        + "with a clear angle for an Indian retail investor. "
        "Reject (return null for) ONLY content that is clearly unrelated: forum/aggregator posts "
        "(e.g. 'Show HN', 'Ask HN'), exam-prep or listicle-style roundups (e.g. 'UPSC Key'), "
        "or news entirely about another country with zero India connection. "
        "When in doubt, include the story if it has any relevance to India's economy, markets, "
        "businesses, or policies — even indirect relevance is fine. "
        f"For every headline you ACCEPT, write an ORIGINAL news brief of approximately "
        f"{word_count} words in your own words. Structure each brief to cover every angle "
        "concisely: (1) what happened - the core event, key numbers, names, or outcome; "
        "(2) the context - why this is happening now or what led to it; (3) the so-what - "
        "what it means for Indian markets, a sector, or everyday investors. Open with a "
        "strong, specific first sentence (not a generic lead-in like 'In recent news...'). "
        "Write in plain, vivid English for a non-expert reader, in dense sentences with "
        "zero filler, so the reader walks away genuinely informed, not just teased. "
        "Do not quote or closely paraphrase any specific article - write a "
        "general explainer based on the headline and topic. "
        "Return ONLY a valid JSON array, one entry per input headline IN THE SAME ORDER: "
        "either a string (the brief, for accepted headlines) or the JSON value null "
        "(for rejected headlines). No extra text."
    )

    headlines = [
        {"title": it["title"], "source": it.get("source", ""), "description": it.get("description", "")}
        for it in items
    ]
    # Budget enough output tokens for N articles of ~word_count words each
    # (roughly 1.4 tokens/word) plus JSON overhead, capped at a sane max.
    max_tokens = min(4096, max(2048, int(len(items) * word_count * 1.6) + 512))

    result, err = call_claude_haiku(
        system_prompt, json.dumps(headlines), api_key, max_tokens=max_tokens
    )

    if err or not isinstance(result, list):
        return items

    accepted = []
    for i, brief in enumerate(result):
        if i < len(items) and isinstance(brief, str) and brief.strip():
            items[i]["article"] = brief
            accepted.append(items[i])

    return accepted


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


def _overlay_angel_quote(result: dict, nse_symbol: str) -> None:
    """Overlay Angel One's real-time price/change onto a stock_data result
    built from yfinance/Finnhub. Fundamentals (sector, PE, market cap, etc.)
    stay from the original source since Angel One's quote API doesn't carry
    them — only price/change/source are replaced when Angel One succeeds."""
    if not angel.enabled:
        return
    q = get_live_quote(nse_symbol)
    if q and q.get("source") == "Angel One" and q.get("price"):
        result["price"] = q["price"]
        result["change"] = q.get("change")
        result["change_pct"] = q.get("change_pct")
        result["source"] = "Angel One"


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
                "source": "yfinance",
            }
            _overlay_angel_quote(result, nse_symbol)
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
            "source": "Finnhub",
        }
        _overlay_angel_quote(result, nse_symbol)
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

        # Combine three free sources for maximum freshness:
        #  1. Yahoo Finance's own news feed for this ticker (often the freshest)
        #  2. NewsAPI (if a key is configured)
        #  3. Google News RSS (no key needed)
        yahoo_items = fetch_yahoo_finance_news(f"{nse_symbol}.NS", limit=12)
        err, search_items = fetch_news(f"{company_name} stock India", limit=12)
        if err and not yahoo_items:
            return jsonify(err)

        combined = yahoo_items + (search_items or [])

        # Dedupe by normalized title prefix (different sources often carry
        # the same wire-service headline with slightly different suffixes).
        seen = set()
        deduped = []
        for it in combined:
            key = (it.get("title") or "").strip().lower()[:60]
            if key and key not in seen:
                seen.add(key)
                deduped.append(it)

        # Freshest first - keep extra headroom since relevance filtering
        # below may drop a few before we trim to the final display count.
        deduped.sort(key=lambda it: parse_news_date(it.get("published", "")), reverse=True)
        items = deduped[:15]

        items = generate_news_briefs(items, get_anthropic_key(), topic_hint=f"{company_name} (Indian stock)")
        items = items[:6]
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
                    if hasattr(col, 'strftime'):
                        period_str = col.strftime("%b %Y")
                    else:
                        period_str = str(col)[:8]
                    if val is None or (hasattr(val, '__float__') and val != val):
                        out[period_str] = None
                        continue
                    out[period_str] = round(float(val) / 1e7, 2)
                except Exception:
                    continue
            return out
    return {}



@app.route("/api/global-stock/<path:symbol>")
@cache.cached(timeout=300)
def global_stock_data(symbol):
    """Full research snapshot for a global (non-NSE) stock.
    Returns price in the stock's native currency, key fundamentals.
    Uses fast_info first, falls back to history download for exchanges
    (like TWO, TSE, LSE) where fast_info may fail."""
    import traceback
    try:
        import yfinance as _yf

        t = yf_ticker(symbol)
        info = {}
        try:
            raw_info = t.info
            if isinstance(raw_info, dict):
                info = raw_info
        except Exception:
            pass

        # --- Price: try fast_info first (each field individually), then history fallback ---
        price, prev, day_high, day_low, year_high, year_low = None, None, None, None, None, None
        try:
            fi = t.fast_info
            try: price     = fi.get("lastPrice")
            except Exception: pass
            try: prev      = fi.get("previousClose")
            except Exception: pass
            try: day_high  = fi.get("dayHigh")
            except Exception: pass
            try: day_low   = fi.get("dayLow")
            except Exception: pass
            try: year_high = fi.get("yearHigh") or fi.get("fiftyTwoWeekHigh")
            except Exception: pass
            try: year_low  = fi.get("yearLow") or fi.get("fiftyTwoWeekLow")
            except Exception: pass
        except Exception:
            pass

        # History fallback for day price + change (ticker.history — handles non-US exchanges)
        if not price:
            try:
                hist5 = t.history(period="5d", interval="1d")
                closes5 = hist5["Close"].dropna()
                if not closes5.empty:
                    price = float(closes5.iloc[-1])
                    if len(closes5) >= 2:
                        prev = float(closes5.iloc[-2])
                    try: day_high = float(hist5["High"].dropna().iloc[-1])
                    except Exception: pass
                    try: day_low  = float(hist5["Low"].dropna().iloc[-1])
                    except Exception: pass
            except Exception:
                pass

        # Final fallback for day price via yf.download
        if not price:
            try:
                df5 = _yf.download(symbol, period="5d", interval="1d",
                                   progress=False, auto_adjust=True)
                closes = df5["Close"].dropna()
                if not closes.empty:
                    price = float(closes.iloc[-1])
                    if len(closes) >= 2:
                        prev = float(closes.iloc[-2])
                    day_high = float(df5["High"].dropna().iloc[-1])
                    day_low  = float(df5["Low"].dropna().iloc[-1])
            except Exception:
                pass

        # 52-week high/low from info or 1y history
        if not year_high:
            year_high = info.get("fiftyTwoWeekHigh")
        if not year_low:
            year_low = info.get("fiftyTwoWeekLow")
        if not year_high:
            try:
                df1y = _yf.download(symbol, period="1y", interval="1d",
                                    progress=False, auto_adjust=True)
                if not df1y.empty:
                    year_high = float(df1y["High"].dropna().max())
                    year_low  = float(df1y["Low"].dropna().min())
            except Exception:
                pass

        change_pct = round(((price - prev) / prev) * 100, 2) if price and prev else None

        # Currency detection
        currency = (info.get("currency") or "").upper()
        if not currency:
            # Infer from symbol suffix
            suffix_currency = {".L": "GBP", ".T": "JPY", ".HK": "HKD",
                               ".SS": "CNY", ".SZ": "CNY", ".TW": "TWD",
                               ".TO": "CAD", ".AX": "AUD", ".ME": "RUB"}
            for sfx, cur in suffix_currency.items():
                if symbol.upper().endswith(sfx):
                    currency = cur
                    break
            if not currency:
                currency = "USD"

        currency_symbols = {"USD": "$", "GBP": "£", "JPY": "¥", "HKD": "HK$",
                            "CNY": "¥", "CNH": "¥", "EUR": "€", "RUB": "₽",
                            "TWD": "NT$", "CAD": "CA$", "AUD": "A$", "KRW": "₩"}
        cur_sym = currency_symbols.get(currency, currency + " ")

        def safe(v, digits=2):
            try:
                return round(float(v), digits) if v is not None else None
            except Exception:
                return None

        market_cap = safe(info.get("marketCap"))
        mc_display = None
        if market_cap:
            if market_cap >= 1e12:
                mc_display = f"{cur_sym}{market_cap/1e12:.2f}T"
            elif market_cap >= 1e9:
                mc_display = f"{cur_sym}{market_cap/1e9:.2f}B"
            elif market_cap >= 1e6:
                mc_display = f"{cur_sym}{market_cap/1e6:.2f}M"

        if not price:
            return jsonify({"error": f"Could not fetch price for '{symbol}'. The stock may be delisted or temporarily unavailable."})

        return jsonify({
            "symbol":          symbol,
            "name":            info.get("longName") or info.get("shortName") or symbol,
            "exchange":        info.get("exchange") or "",
            "currency":        currency,
            "currency_symbol": cur_sym,
            "price":           safe(price),
            "change_pct":      change_pct,
            "prev_close":      safe(prev),
            "day_high":        safe(day_high),
            "day_low":         safe(day_low),
            "year_high":       safe(year_high),
            "year_low":        safe(year_low),
            "market_cap":      market_cap,
            "market_cap_display": mc_display,
            "pe_ratio":        safe(info.get("trailingPE")),
            "eps":             safe(info.get("trailingEps")),
            "dividend_yield":  safe(info.get("dividendYield"), 4),
            "sector":          info.get("sector") or "",
            "industry":        info.get("industry") or "",
            "description":     (info.get("longBusinessSummary") or "")[:500],
            "country":         info.get("country") or "",
            "website":         info.get("website") or "",
            "is_global":       True,
        })
    except Exception as e:
        tb = traceback.format_exc()
        print(f"global_stock_data ERROR for {symbol}: {e}\n{tb}")
        return jsonify({"error": f"Data unavailable for {symbol}: {str(e)}"})



@app.route("/api/stock/<symbol>/financials")
@cache.cached(timeout=43200)
def stock_financials(symbol):
    """Quarterly P&L and annual balance sheet. Uses broad row-name aliases
    and collects periods from all metrics so no quarter is silently dropped."""
    try:
        nse_symbol = resolve_symbol(symbol)
        ticker = yf_ticker(f"{nse_symbol}.NS")

        try:
            qf = ticker.quarterly_income_stmt
            if qf is None or qf.empty:
                qf = ticker.quarterly_financials
        except Exception:
            qf = None

        try:
            bs = ticker.balance_sheet
            if bs is None or bs.empty:
                bs = ticker.quarterly_balance_sheet
        except Exception:
            bs = None

        revenue = _df_row(qf,
            "Total Revenue",
            "Operating Revenue",
            "Revenue",
            "Net Revenue",
            "Total Net Revenue",
            "Sales",
        )
        operating_profit = _df_row(qf,
            "Operating Income",
            "EBIT",
            "Operating Profit",
            "Total Operating Income As Reported",
            "Gross Profit",
            "Operating Income Or Loss",
            "Income From Operations",
        )
        ebitda = _df_row(qf,
            "EBITDA",
            "Normalized EBITDA",
            "Reconciled Depreciation",
            "EBIT",
        )
        net_profit = _df_row(qf,
            "Net Income",
            "Net Income Common Stockholders",
            "Net Income Including Noncontrolling Interests",
            "Net Income Continuous Operations",
            "Pretax Income",
            "Net Profit",
            "Profit After Tax",
        )

        all_periods = set()
        for d in [revenue, operating_profit, ebitda, net_profit]:
            all_periods.update(d.keys())

        def parse_period(p):
            try:
                return datetime.strptime(p, "%b %Y")
            except Exception:
                return datetime.min

        periods = sorted(all_periods, key=parse_period, reverse=True)
        quarterly_pnl = []
        for p in periods:
            quarterly_pnl.append({
                "period": p,
                "revenue_cr": revenue.get(p),
                "operating_profit_cr": operating_profit.get(p),
                "ebitda_cr": ebitda.get(p),
                "net_profit_cr": net_profit.get(p),
            })

        total_assets = _df_row(bs,
            "Total Assets",
            "Assets",
            "Total Assets Net Minority Interest",
        )
        total_liabilities = _df_row(bs,
            "Total Liabilities Net Minority Interest",
            "Total Liab",
            "Total Liabilities",
            "Liabilities",
            "Total Liabilities And Stockholders Equity",
        )
        total_equity = _df_row(bs,
            "Stockholders Equity",
            "Total Equity Gross Minority Interest",
            "Common Stock Equity",
            "Total Stockholder Equity",
            "Shareholders Equity",
            "Net Tangible Assets",
        )
        total_debt = _df_row(bs,
            "Total Debt",
            "Long Term Debt",
            "Total Long Term Debt",
            "Net Debt",
            "Short Long Term Debt Total",
        )
        cash = _df_row(bs,
            "Cash And Cash Equivalents",
            "Cash",
            "Cash Cash Equivalents And Short Term Investments",
            "Cash And Short Term Investments",
            "Cash Equivalents",
        )

        bs_all_periods = set()
        for d in [total_assets, total_liabilities, total_equity, total_debt, cash]:
            bs_all_periods.update(d.keys())

        bs_periods = sorted(bs_all_periods, key=parse_period, reverse=True)
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
                f"Figures in ₹ crore (1 Cr = ₹1,00,00,000). L Cr = Lakh Crore (₹1,00,000 Cr). "
                f"Showing {len(quarterly_pnl)} quarters of P&L and {len(balance_sheet)} years of "
                f"balance sheet data available from Yahoo Finance. "
                f"Some cells show — where data is not reported or not available from the source."
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

        # Sanity check: INR=X returns ~0.012 (inverted); USDINR=X should give ~83.
        # Guard against any residual inversion (e.g. if yfinance internally aliases).
        if label == "USD/INR" and price is not None and price < 10:
            try:
                price = round(1.0 / price, 2) if price else None
            except Exception:
                price = None

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
def market_overview():
    cached = cache.get("market_overview_response")
    if cached is not None:
        return jsonify(cached)

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
        # Per-symbol fast_info via a thread pool — yf.download()'s batch
        # endpoint is frequently rate-limited/unreliable on Yahoo's side,
        # whereas fast_info (used successfully for the ticker bar and
        # heatmap) works reliably per-symbol.
        movers = []

        def fetch_mover(s):
            try:
                q = get_live_quote(s)
                if q and q.get("price"):
                    return {"symbol": s, "price": round(float(q["price"]), 2),
                            "change_pct": q.get("change_pct")}
            except Exception:
                pass
            return None

        with ThreadPoolExecutor(max_workers=8) as executor:
            for r in executor.map(fetch_mover, NIFTY50_SYMBOLS):
                if r:
                    movers.append(r)

        # Finnhub fallback: fetch a subset of Nifty50 stocks if Yahoo failed
        if len(movers) < 5:
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

        response_data = {"indices": indices, "gainers": gainers, "losers": losers}
        cache.set("market_overview_response", response_data, timeout=600 if movers else 60)
        return jsonify(response_data)
    except Exception as e:
        return jsonify({"error": f"Failed to fetch market overview: {e}"})


def quote_change_pct(nse_symbol: str) -> float | None:
    """Quick helper: today's % change for an NSE symbol."""
    q = get_live_quote(nse_symbol)
    if q and q.get("change_pct") is not None:
        return q["change_pct"]
    return None


@app.route("/api/market/heatmap")
@cache.cached(timeout=600)
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

    def fetch_constituent_sector(sector):
        symbols = SECTOR_STOCKS.get(sector, [])
        with ThreadPoolExecutor(max_workers=8) as executor:
            changes = [c for c in executor.map(quote_change_pct, symbols) if c is not None]
        avg = round(sum(changes) / len(changes), 2) if changes else 0
        return {"sector": sector, "change_pct": avg, "key": sector}

    constituent_sectors = ["Defence", "Water", "Oil & Gas", "Consumer Durables", "Semiconductor", "Telecom"]

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(fetch_index_sector, s, sym) for s, sym in SECTOR_INDICES.items()]
        for cs in constituent_sectors:
            futures.append(executor.submit(fetch_constituent_sector, cs))

        for future in as_completed(futures, timeout=25):
            try:
                out.append(future.result())
            except Exception:
                pass

    order = list(SECTOR_INDICES.keys()) + constituent_sectors
    out.sort(key=lambda s: order.index(s["sector"]) if s["sector"] in order else 999)

    return jsonify({"sectors": out})


@app.route("/api/market/sector/<key>/stocks")
@cache.cached(timeout=600)
def sector_stocks(key):
    """Representative stock list with live prices for a heatmap cell."""
    symbols = SECTOR_STOCKS.get(key)
    if not symbols:
        return jsonify({"error": f"Unknown sector '{key}'."})

    def fetch_stock(symbol):
        q = get_live_quote(symbol)
        if q and q.get("price"):
            return {"symbol": symbol, "price": round(float(q["price"]), 2),
                    "change_pct": q.get("change_pct")}
        return {"symbol": symbol, "price": None, "change_pct": None}

    with ThreadPoolExecutor(max_workers=6) as executor:
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
    "Taiwan (TWII)": "^TWII",
}

# Top 10 blue-chip stocks for each global index, by yfinance symbol.
# These are the most liquid, largest-cap constituents that yfinance can
# reliably price. Non-US stocks need their exchange suffix.
GLOBAL_INDEX_STOCKS = {
    "Dow Jones": [
        {"symbol": "AAPL",  "name": "Apple"},
        {"symbol": "MSFT",  "name": "Microsoft"},
        {"symbol": "UNH",   "name": "UnitedHealth"},
        {"symbol": "GS",    "name": "Goldman Sachs"},
        {"symbol": "HD",    "name": "Home Depot"},
        {"symbol": "CAT",   "name": "Caterpillar"},
        {"symbol": "MCD",   "name": "McDonald's"},
        {"symbol": "V",     "name": "Visa"},
        {"symbol": "AMGN",  "name": "Amgen"},
        {"symbol": "JPM",   "name": "JPMorgan"},
    ],
    "S&P 500": [
        {"symbol": "AAPL",  "name": "Apple"},
        {"symbol": "NVDA",  "name": "Nvidia"},
        {"symbol": "MSFT",  "name": "Microsoft"},
        {"symbol": "AMZN",  "name": "Amazon"},
        {"symbol": "META",  "name": "Meta"},
        {"symbol": "GOOGL", "name": "Alphabet"},
        {"symbol": "BRK-B", "name": "Berkshire Hathaway"},
        {"symbol": "TSLA",  "name": "Tesla"},
        {"symbol": "JPM",   "name": "JPMorgan"},
        {"symbol": "XOM",   "name": "ExxonMobil"},
    ],
    "Nasdaq": [
        {"symbol": "AAPL",  "name": "Apple"},
        {"symbol": "NVDA",  "name": "Nvidia"},
        {"symbol": "MSFT",  "name": "Microsoft"},
        {"symbol": "AMZN",  "name": "Amazon"},
        {"symbol": "META",  "name": "Meta"},
        {"symbol": "GOOGL", "name": "Alphabet"},
        {"symbol": "TSLA",  "name": "Tesla"},
        {"symbol": "AVGO",  "name": "Broadcom"},
        {"symbol": "COST",  "name": "Costco"},
        {"symbol": "NFLX",  "name": "Netflix"},
    ],
    "FTSE 100": [
        {"symbol": "SHEL.L",  "name": "Shell"},
        {"symbol": "AZN.L",   "name": "AstraZeneca"},
        {"symbol": "HSBA.L",  "name": "HSBC"},
        {"symbol": "ULVR.L",  "name": "Unilever"},
        {"symbol": "BP.L",    "name": "BP"},
        {"symbol": "GSK.L",   "name": "GSK"},
        {"symbol": "RIO.L",   "name": "Rio Tinto"},
        {"symbol": "BATS.L",  "name": "BAT"},
        {"symbol": "DGE.L",   "name": "Diageo"},
        {"symbol": "VOD.L",   "name": "Vodafone"},
    ],
    "Nikkei 225": [
        {"symbol": "7203.T",  "name": "Toyota"},
        {"symbol": "6758.T",  "name": "Sony"},
        {"symbol": "6861.T",  "name": "Keyence"},
        {"symbol": "8306.T",  "name": "Mitsubishi UFJ"},
        {"symbol": "9432.T",  "name": "NTT"},
        {"symbol": "6501.T",  "name": "Hitachi"},
        {"symbol": "7974.T",  "name": "Nintendo"},
        {"symbol": "4519.T",  "name": "Chugai Pharma"},
        {"symbol": "6954.T",  "name": "Fanuc"},
        {"symbol": "9984.T",  "name": "SoftBank"},
    ],
    "Hang Seng": [
        {"symbol": "0700.HK", "name": "Tencent"},
        {"symbol": "9988.HK", "name": "Alibaba"},
        {"symbol": "0005.HK", "name": "HSBC HK"},
        {"symbol": "0941.HK", "name": "China Mobile"},
        {"symbol": "3690.HK", "name": "Meituan"},
        {"symbol": "0388.HK", "name": "HK Exchanges"},
        {"symbol": "2318.HK", "name": "Ping An"},
        {"symbol": "1299.HK", "name": "AIA Group"},
        {"symbol": "0016.HK", "name": "Sun Hung Kai"},
        {"symbol": "9618.HK", "name": "JD.com"},
    ],
    "Shanghai Composite": [
        {"symbol": "601398.SS", "name": "ICBC"},
        {"symbol": "600519.SS", "name": "Kweichow Moutai"},
        {"symbol": "601857.SS", "name": "PetroChina"},
        {"symbol": "601988.SS", "name": "Bank of China"},
        {"symbol": "600036.SS", "name": "China Merchants Bank"},
        {"symbol": "601628.SS", "name": "China Life"},
        {"symbol": "600900.SS", "name": "Yangtze Power"},
        {"symbol": "601939.SS", "name": "CCB"},
        {"symbol": "600276.SS", "name": "Hengrui Medicine"},
        {"symbol": "601088.SS", "name": "China Shenhua"},
    ],
    "Taiwan (TWII)": [
        {"symbol": "2330.TW",  "name": "TSMC"},
        {"symbol": "2317.TW",  "name": "Hon Hai (Foxconn)"},
        {"symbol": "2454.TW",  "name": "MediaTek"},
        {"symbol": "2382.TW",  "name": "Quanta Computer"},
        {"symbol": "2308.TW",  "name": "Delta Electronics"},
        {"symbol": "2881.TW",  "name": "Fubon Financial"},
        {"symbol": "2882.TW",  "name": "Cathay Financial"},
        {"symbol": "3711.TW",  "name": "ASE Technology"},
        {"symbol": "2303.TW",  "name": "United Microelectronics"},
        {"symbol": "2412.TW",  "name": "Chunghwa Telecom"},
    ],
}


@app.route("/api/market/global")
@cache.cached(timeout=900)
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


@app.route("/api/market/global/<path:index_name>/stocks")
@cache.cached(timeout=1200)
def global_index_stocks(index_name):
    """Live price snapshot for the top blue-chip stocks in a given global
    index, sorted by day-change percentage (best performers first) so users
    see the index's current momentum leaders."""
    stocks = GLOBAL_INDEX_STOCKS.get(index_name)
    if not stocks:
        return jsonify({"error": f"No blue-chip list defined for '{index_name}'."}), 404

    def fetch_stock(entry):
        # Method 1: fast_info (fastest path)
        try:
            fi = yf_ticker(entry["symbol"]).fast_info
            price = fi.get("lastPrice")
            prev  = fi.get("previousClose")
            if price:
                change_pct = round(((price - prev) / prev) * 100, 2) if price and prev else None
                return {
                    "symbol":     entry["symbol"],
                    "name":       entry["name"],
                    "price":      round(float(price), 2),
                    "change_pct": change_pct,
                }
        except Exception:
            pass
        # Method 2: ticker.history() — uses yfinance session, more reliable for non-US exchanges
        try:
            t = yf_ticker(entry["symbol"])
            hist = t.history(period="5d", interval="1d")
            closes = hist["Close"].dropna()
            if len(closes) >= 1:
                last = float(closes.iloc[-1])
                change_pct = None
                if len(closes) >= 2:
                    prev = float(closes.iloc[-2])
                    change_pct = round((last - prev) / prev * 100, 2)
                return {
                    "symbol":     entry["symbol"],
                    "name":       entry["name"],
                    "price":      round(last, 2),
                    "change_pct": change_pct,
                }
        except Exception:
            pass
        # Method 3: yf.download bulk endpoint
        try:
            import yfinance as yf
            df = yf.download(entry["symbol"], period="5d", interval="1d",
                             progress=False, auto_adjust=True)
            closes = df["Close"].dropna()
            if len(closes) >= 1:
                last = float(closes.iloc[-1])
                change_pct = None
                if len(closes) >= 2:
                    prev = float(closes.iloc[-2])
                    change_pct = round((last - prev) / prev * 100, 2)
                return {
                    "symbol":     entry["symbol"],
                    "name":       entry["name"],
                    "price":      round(last, 2),
                    "change_pct": change_pct,
                }
        except Exception:
            pass
        return None

    results = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        for r in executor.map(fetch_stock, stocks):
            if r:
                results.append(r)

    # Sort best performers first so the "hottest" names are visible at a glance
    results.sort(key=lambda r: (r["change_pct"] is None, -(r["change_pct"] or 0)))

    return jsonify({"index": index_name, "stocks": results})



@app.route("/api/market/52week")
@cache.cached(timeout=3600)
def market_52week():
    """Scan every stock available on the site and rank by proximity to its
    52-week high and low. Returns the top 5 closest to each extreme, plus
    the full ranked list (for the "show all" view)."""

    def fetch_stock(symbol):
        q = get_live_quote(symbol)
        if not q or not q.get("price"):
            return None
        price = float(q["price"])
        year_high = q.get("week_52_high") or q.get("year_high")
        year_low = q.get("week_52_low") or q.get("year_low")
        if not year_high or not year_low:
            # Fallback: use 1-year history to compute high/low manually
            try:
                import yfinance as yf
                df = yf.download(f"{symbol}.NS", period="1y", interval="1d",
                                 progress=False, auto_adjust=True)
                if not df.empty:
                    year_high = float(df["High"].dropna().max())
                    year_low = float(df["Low"].dropna().min())
            except Exception:
                pass
        if not year_high or not year_low:
            return None
        return {
            "symbol": symbol,
            "price": round(price, 2),
            "year_high": round(float(year_high), 2),
            "year_low": round(float(year_low), 2),
            "pct_from_high": round((price-float(year_high))/float(year_high)*100, 2),
            "pct_from_low": round((price-float(year_low))/float(year_low)*100, 2),
        }

    results = []
    with ThreadPoolExecutor(max_workers=8) as executor:
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
@cache.cached(timeout=600)
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


_NEWS_YEAR = datetime.now().year
NEWS_CATEGORY_QUERIES = {
    "geo":       f"India trade exports imports geopolitics economy {_NEWS_YEAR}",
    "policy":    f"India government policy RBI SEBI budget regulatory {_NEWS_YEAR}",
    "business":  f"India company earnings results corporate NSE BSE {_NEWS_YEAR}",
    "tax":       f"India income tax ITR GST CBDT budget Nirmala Sitharaman {_NEWS_YEAR}",
    "market":    f"India stock market Nifty Sensex BSE NSE rally {_NEWS_YEAR}",
    "inflation": f"India CPI WPI inflation RBI food prices {_NEWS_YEAR}",
    "macro":     f"India GDP economy growth RBI IIP PMI {_NEWS_YEAR}",
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
    "geo": {"limit": 28, "display_limit": 8, "words": 100},
    "policy": {"limit": 16, "display_limit": 6, "words": 100},
    "business": {"limit": 28, "display_limit": 8, "words": 100},
    "tax": {"limit": 16, "display_limit": 6, "words": 100},
    "market": {"limit": 14, "display_limit": 6, "words": 100},
    "inflation": {"limit": 16, "display_limit": 6, "words": 100},
    "macro": {"limit": 16, "display_limit": 6, "words": 100},
}


@app.route("/api/news/<category>")
def news_by_category(category):
    cache_key = f"news_cat_{category}"
    cached = cache.get(cache_key)
    if cached is not None:
        return jsonify(cached)

    query = NEWS_CATEGORY_QUERIES.get(category, f"India {category} news")
    config = NEWS_CATEGORY_CONFIG.get(category, {"limit": 8, "words": 150})
    err, items = fetch_news(query, limit=config["limit"])
    if err and not items:
        items = []

    # Supplement market/business news with Yahoo Finance's own feed for the
    # major indices - often same-day fresh. Yahoo items go FIRST so they
    # surface before the search-based results.
    if category in ("market", "business"):
        yahoo_fresh = fetch_yahoo_finance_news("^NSEI", limit=5)
        yahoo_fresh += fetch_yahoo_finance_news("^BSESN", limit=3)
        items = yahoo_fresh + items  # Yahoo first (freshest)

        seen = set()
        deduped = []
        for it in items:
            key = (it.get("title") or "").strip().lower()[:60]
            if key and key not in seen:
                seen.add(key)
                deduped.append(it)
        deduped.sort(key=lambda it: parse_news_date(it.get("published", "")), reverse=True)
        items = deduped[:config["limit"]]

    if not items:
        err_resp = {"error": "Could not fetch news right now. Please try again shortly."}
        cache.set(cache_key, err_resp, timeout=120)
        return jsonify(err_resp)

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
    # just redirect users to (and reproduce) external articles. Items that
    # the AI determines aren't genuinely relevant are dropped here.
    topic_hint = NEWS_CATEGORY_TOPIC_HINTS.get(category, "Indian financial news")
    items = generate_news_briefs(items, api_key, topic_hint=topic_hint, word_count=config["words"])
    items = items[:config.get("display_limit", config["limit"])]

    if not items:
        err_resp = {"error": "No relevant news found right now. Please try again shortly."}
        cache.set(cache_key, err_resp, timeout=120)
        return jsonify(err_resp)

    response = {"category": category, "news": items}
    cache.set(cache_key, response, timeout=1800)
    return jsonify(response)


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


def _fetch_nse_ipo_news() -> list:
    """Try to pull IPO data from NSE India's public API (requires session cookies)."""
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.nseindia.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-IN,en;q=0.9",
        })
        # Warm up cookies
        session.get("https://www.nseindia.com/market-data/all-upcoming-issues-ipo", timeout=8)
        resp = session.get("https://www.nseindia.com/api/ipos?category=ipo", timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            rows = data if isinstance(data, list) else data.get("data", [])
            # Convert NSE rows to our news-item format so the rest of the pipeline works
            items = []
            for row in rows[:10]:
                title = (row.get("issueOpenDate") or "") + " " + (row.get("companyName") or "")
                desc = (
                    f"Price Band: {row.get('issuePrice', 'N/A')} | "
                    f"Issue Size: {row.get('issueSize', 'N/A')} | "
                    f"Open: {row.get('issueOpenDate', 'N/A')} - Close: {row.get('issueCloseDate', 'N/A')}"
                )
                items.append({
                    "title": (row.get("companyName") or "IPO") + " IPO",
                    "description": desc,
                    "source": "NSE India",
                    "link": "https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
                    "published": row.get("issueOpenDate") or "",
                })
            if items:
                return items
    except Exception:
        pass
    return []


@app.route("/api/ipo/showcase")
def ipo_showcase():
    cache_key = "ipo_showcase_response"
    cached = cache.get(cache_key)
    if cached is not None:
        return jsonify(cached)

    api_key = get_anthropic_key()
    note = (
        "Live IPO data (price band, lot size, dates) is extracted from recent "
        "news articles and may be incomplete or out of date. Company overviews "
        "and green/red flags are AI-generated for education only. Always verify "
        "exact details in the official prospectus (RHP/DRHP) and on the NSE/BSE "
        "websites before investing."
    )

    if not api_key:
        err_resp = {"note": note, "ipos": [], "error": "No Anthropic API key configured. Add one in Settings to generate IPO overviews."}
        cache.set(cache_key, err_resp, timeout=120)
        return jsonify(err_resp)

    # Step 1: gather real, recent news about open/upcoming IPOs in India.
    # Try NSE API first, then multiple Google News queries.
    items = _fetch_nse_ipo_news()

    if not items:
        err, items = fetch_news("upcoming IPO India price band lot size mainboard", limit=15)
        if err or not items:
            _, items2 = fetch_news("IPO opens India subscription GMP allotment 2025 2026", limit=15)
            items = items2 or []
        if not items:
            _, items3 = fetch_google_news_rss("India IPO open upcoming 2026", limit=10, recency="when:30d")
            items = items3 or []

    if not items:
        err_resp = {"note": note, "ipos": [], "error": "Could not fetch IPO news right now. Try again later."}
        cache.set(cache_key, err_resp, timeout=120)
        return jsonify(err_resp)

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
        err_resp = {"note": note, "ipos": [], "error": err or "Could not generate IPO data."}
        cache.set(cache_key, err_resp, timeout=120)
        return jsonify(err_resp)

    response = {"note": note, "ipos": result}
    cache.set(cache_key, response, timeout=3600)
    return jsonify(response)


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
    """Search MFAPI.in for scheme name/code matches. Retries once on
    rate-limit responses (mfapi.in can 429 under burst traffic)."""
    for attempt in range(2):
        try:
            resp = requests.get(f"{MFAPI_BASE}/search", params={"q": query}, timeout=8)
            if resp.status_code == 429 and attempt == 0:
                time.sleep(1.5)
                continue
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception:
            if attempt == 0:
                time.sleep(1.0)
                continue
            return []
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
    """Fetch full NAV history for a scheme code. Retries once on
    rate-limit responses (mfapi.in can 429 under burst traffic)."""
    for attempt in range(2):
        try:
            resp = requests.get(f"{MFAPI_BASE}/{scheme_code}", timeout=10)
            if resp.status_code == 429 and attempt == 0:
                time.sleep(1.5)
                continue
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "SUCCESS" and data.get("data"):
                return data
            return None
        except Exception:
            if attempt == 0:
                time.sleep(1.0)
                continue
            return None
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
def mutual_funds_top():
    """Top performing direct-growth mutual funds by 1-year return.

    Each fund requires 2 external HTTP calls (search + NAV history). Fetched
    in parallel via a thread pool so the whole request stays well under
    gunicorn's worker timeout even with ~28 funds tracked. We track more
    funds than needed (28) since some lookups inevitably fail to resolve on
    MFAPI, ensuring we still end up with 10 valid results.

    Cached manually (rather than via @cache.cached) so a transient MFAPI
    outage that returns zero results doesn't get stuck in cache for 6 hours -
    empty results are retried again after 2 minutes, good results are kept
    for 6 hours.
    """
    cached = cache.get("mutualfunds_top_response")
    if cached is not None:
        return jsonify(cached)

    results = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_one_fund, fund) for fund in MUTUAL_FUND_WATCHLIST]
        try:
            for future in as_completed(futures, timeout=50):
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

    response_data = {
        "funds": results[:10],
        "note": (
            "NAV and return data sourced from AMFI via MFAPI.in (free, no key required). "
            "Returns shown are point-to-point (1-year absolute change) and 3-year CAGR based "
            "on Direct Growth plan NAVs. Past performance does not guarantee future returns — "
            "verify on the fund house website or AMFI before investing."
        ),
    }

    # Cache good results for 6h; cache empty results only briefly so a
    # transient MFAPI hiccup self-heals on the next request.
    cache.set("mutualfunds_top_response", response_data, timeout=21600 if results else 120)

    return jsonify(response_data)


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


@app.route("/api/tax/govt-schemes")
def govt_schemes():
    """Top 5 highest-return Indian government investment schemes with
    AI-generated 50-word briefs covering all key aspects. Cached 24h
    since scheme rates change quarterly not daily."""
    cached = cache.get("govt_schemes_response")
    if cached:
        return jsonify(cached)

    SCHEMES = [
        {
            "name": "Senior Citizen Savings Scheme (SCSS)",
            "rate": "8.2%",
            "category": "Post Office / Bank",
            "lock_in": "5 years",
            "max_invest": "₹30 lakh",
            "tax_benefit": "80C eligible",
            "who_for": "Age 60+",
            "payout": "Quarterly",
            "safety": "Government Guaranteed",
            "key_facts": "Highest safe rate. Max ₹30L. Quarterly interest payout. 5-yr lock-in, extendable by 3 yrs. Premature closure allowed with penalty. Section 80C eligible. Interest is taxable."
        },
        {
            "name": "Sukanya Samriddhi Yojana (SSY)",
            "rate": "8.2%",
            "category": "Post Office",
            "lock_in": "Until girl turns 21",
            "max_invest": "₹1.5 lakh/yr",
            "tax_benefit": "80C + EEE (fully tax-free)",
            "who_for": "Parents of girl child under 10",
            "payout": "At maturity",
            "safety": "Government Guaranteed",
            "key_facts": "EEE status — investment, growth, and maturity all tax-free. Only 2 accounts per family. Partial withdrawal at 18 for education. Highest rate with full tax exemption."
        },
        {
            "name": "RBI Floating Rate Savings Bonds 2020",
            "rate": "8.05%",
            "category": "RBI / Banks",
            "lock_in": "7 years",
            "max_invest": "No limit",
            "tax_benefit": "None",
            "who_for": "All residents",
            "payout": "Semi-annual",
            "safety": "Sovereign (RBI)",
            "key_facts": "No investment limit. Rate resets every 6 months — linked to NSC rate plus 0.35%. Semi-annual interest payout. Sovereign guarantee. Not tradeable on exchange. Interest taxable."
        },
        {
            "name": "National Savings Certificate (NSC)",
            "rate": "7.7%",
            "category": "Post Office",
            "lock_in": "5 years",
            "max_invest": "No limit",
            "tax_benefit": "80C eligible",
            "who_for": "All residents",
            "payout": "At maturity (compounded annually)",
            "safety": "Government Guaranteed",
            "key_facts": "No max limit. Interest compounded annually and reinvestment qualifies for 80C each year. Accepted as collateral for loans. Available at all post offices. Simple and reliable."
        },
        {
            "name": "Kisan Vikas Patra (KVP)",
            "rate": "7.5%",
            "category": "Post Office",
            "lock_in": "115 months (~9.6 yrs) to double",
            "max_invest": "No limit",
            "tax_benefit": "None",
            "who_for": "All residents",
            "payout": "Lump sum at maturity",
            "safety": "Government Guaranteed",
            "key_facts": "Money doubles in ~115 months. No max limit. No 80C benefit. Can be encashed after 2.5 years. Transferable between post offices. KYC required above ₹50,000. Interest is taxable."
        },
    ]

    api_key = get_anthropic_key()
    if api_key:
        system_prompt = (
            "You are a financial advisor writing for Indian retail investors. "
            "For each government investment scheme below, write a brief of "
            "EXACTLY 50 words that covers ALL of these aspects in order: "
            "(1) current interest rate, (2) who should invest, (3) lock-in period, "
            "(4) maximum investment limit, (5) tax treatment, (6) one key advantage "
            "or unique feature that makes it stand out. "
            "Be specific with numbers. No fluff. Dense, useful, plain English. "
            "Return ONLY a valid JSON array of 5 strings, one per scheme, same order as input."
        )
        scheme_data = [
            {
                "name": s["name"],
                "rate": s["rate"],
                "lock_in": s["lock_in"],
                "max_invest": s["max_invest"],
                "tax_benefit": s["tax_benefit"],
                "who_for": s["who_for"],
                "key_facts": s["key_facts"]
            }
            for s in SCHEMES
        ]
        result, err = call_claude_haiku(
            system_prompt,
            json.dumps(scheme_data),
            api_key,
            max_tokens=1000
        )
        if not err and isinstance(result, list) and len(result) == 5:
            for i, brief in enumerate(result):
                if isinstance(brief, str):
                    SCHEMES[i]["brief"] = brief

    # Fallback briefs if AI fails
    fallbacks = [
        "SCSS offers 8.2% — India's highest guaranteed rate. For age 60+. ₹30 lakh maximum. 5-year lock-in with quarterly interest payouts. Section 80C eligible. Premature exit allowed with penalty. Interest is taxable but rate security makes it the top choice for retirees.",
        "SSY pays 8.2% for girl child accounts — fully tax-free under EEE status. Open for daughters under 10. Maximum ₹1.5 lakh/year. Matures when girl turns 21. Partial withdrawal at 18 for education. No tax on investment, growth, or withdrawal.",
        "RBI Floating Rate Bonds pay 8.05% — sovereign guarantee, no investment cap. 7-year lock-in. Rate resets every 6 months tied to NSC + 0.35%. Semi-annual interest payouts. No 80C benefit but unlimited investment and maximum safety make it ideal for large surplus funds.",
        "NSC pays 7.7% compounded annually at all post offices. No maximum limit. 5-year lock-in. 80C deduction eligible each year as reinvested interest qualifies. Accepted as loan collateral. Interest is taxable at maturity but annual compounding boosts effective returns significantly.",
        "KVP doubles your money in 115 months at 7.5%. No investment limit. Available at all post offices. Can be encashed after 2.5 years. No 80C benefit. KYC mandatory above ₹50,000. Interest is taxable. Best for those wanting a simple lump-sum doubling instrument.",
    ]
    for i, s in enumerate(SCHEMES):
        if not s.get("brief"):
            s["brief"] = fallbacks[i]

    response = {
        "schemes": [
            {
                "name": s["name"],
                "rate": s["rate"],
                "category": s["category"],
                "lock_in": s["lock_in"],
                "max_invest": s["max_invest"],
                "tax_benefit": s["tax_benefit"],
                "who_for": s["who_for"],
                "payout": s["payout"],
                "safety": s["safety"],
                "brief": s.get("brief", ""),
            }
            for s in SCHEMES
        ],
        "note": "Interest rates as of Q1 2026. Rates are revised quarterly by Government of India. Verify current rates at indiapost.gov.in or rbi.org.in before investing.",
        "updated": datetime.now().strftime("%d %b %Y"),
    }

    cache.set("govt_schemes_response", response, timeout=86400)
    return jsonify(response)


@app.after_request
def add_cache_headers(response):
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})


@app.route("/api/angel/status")
def angel_status():
    return jsonify({
        "enabled": angel.enabled,
        "connected": angel.api is not None,
        "last_login": angel.last_login.isoformat() if angel.last_login else None,
        "tokens_mapped": len(ANGEL_TOKENS),
        "message": "Real-time NSE data active" if angel.api else (
            "Credentials not configured" if not angel.enabled else "Login failed - using yfinance fallback"
        ),
    })


@app.route("/api/stock/<symbol>/live")
@cache.cached(timeout=15)
def stock_live(symbol):
    nse_sym = resolve_symbol(symbol)
    q = get_live_quote(nse_sym)
    if not q:
        return jsonify({"error": f"No data for {nse_sym}"})
    return jsonify(q)


def _warmup():
    import time
    time.sleep(8)
    with app.app_context():
        for path in ["/api/market/ticker", "/api/market/overview",
                     "/api/market/heatmap", "/api/commodities"]:
            try:
                with app.test_client() as c:
                    c.get(path)
            except Exception:
                pass

threading.Thread(target=_warmup, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
