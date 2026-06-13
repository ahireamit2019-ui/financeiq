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
from datetime import datetime, timedelta
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
        # try partial match against company map
        match = None
        for name, sym in COMPANY_MAP.items():
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
            except Exception:
                sort_key = datetime.min

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

        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        return json.loads(text), None
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
        "You are a financial news writer for an Indian retail-investor app. "
        f"For each headline below, write a short ORIGINAL news brief of "
        f"approximately {word_count} words in your own words, explaining what the "
        "story is likely about and why it matters for Indian markets or "
        "everyday investors, in plain English for a non-expert reader. "
        "Do not quote or closely paraphrase any specific article - write a "
        "general explainer based on the headline and topic. "
        + (f"Context: these headlines relate to {topic_hint}. " if topic_hint else "")
        + "Return ONLY a valid JSON array of strings, one per headline, in "
        "the same order as the input, with no extra text."
    )

    headlines = [{"title": it["title"], "source": it.get("source", "")} for it in items]
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

        err, items = fetch_google_news_rss(f"{company_name} stock India")
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


@app.route("/api/market/heatmap")
@cache.cached(timeout=300)
def market_heatmap():
    out = []
    for sector, sym in SECTOR_INDICES.items():
        try:
            fi = yf_ticker(sym).fast_info
            price = fi.get("lastPrice")
            prev = fi.get("previousClose")
            change_pct = round(((price - prev) / prev) * 100, 2) if price and prev else 0
            out.append({"sector": sector, "change_pct": change_pct})
        except Exception:
            out.append({"sector": sector, "change_pct": 0})
    return jsonify({"sectors": out})


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


@app.route("/api/macro/inflation")
@cache.cached(timeout=3600)
def macro_inflation():
    # Curated from RBI / MOSPI published releases. Update periodically.
    return jsonify({
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
    })


@app.route("/api/macro/rbi")
@cache.cached(timeout=3600)
def macro_rbi():
    return jsonify({
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
    })


@app.route("/api/macro/growth")
@cache.cached(timeout=3600)
def macro_growth():
    return jsonify({
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
    })


@app.route("/api/commodities")
@cache.cached(timeout=300)
def commodities():
    out = {}
    inr_rate = None
    try:
        inr_rate = yf_ticker("INR=X").fast_info.get("lastPrice")
    except Exception:
        pass

    for label, sym in COMMODITY_SYMBOLS.items():
        try:
            t = yf_ticker(sym)
            hist = t.history(period="7d", interval="1d")
            closes = hist["Close"].dropna().tolist()
            price = closes[-1] if closes else None
            prev = closes[-2] if len(closes) > 1 else None
            change_pct = round(((price - prev) / prev) * 100, 2) if price and prev else None

            display_price = price
            unit = "USD"
            if label == "Gold" and price and inr_rate:
                # USD/oz -> INR per 10g  (1 troy oz = 31.1035 g)
                display_price = round((price / 31.1035) * 10 * inr_rate, 0)
                unit = "INR/10g"
            elif label == "Silver" and price and inr_rate:
                display_price = round((price / 31.1035) * 10 * inr_rate, 0)
                unit = "INR/10g"

            out[label] = {
                "price": round(price, 2) if price is not None else None,
                "display_price": display_price,
                "unit": unit,
                "change_pct": change_pct,
                "sparkline": [round(c, 2) for c in closes],
            }
        except Exception:
            out[label] = {"price": None, "display_price": None, "unit": "USD", "change_pct": None, "sparkline": []}

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
    err, items = fetch_google_news_rss(query, limit=5)
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
    "geo": {"limit": 20, "words": 150},
    "policy": {"limit": 10, "words": 150},
    "business": {"limit": 20, "words": 150},
    "tax": {"limit": 10, "words": 150},
    "market": {"limit": 8, "words": 150},
    "inflation": {"limit": 10, "words": 150},
    "macro": {"limit": 10, "words": 150},
}


@app.route("/api/news/<category>")
@cache.cached(timeout=3600)
def news_by_category(category):
    query = NEWS_CATEGORY_QUERIES.get(category, f"India {category} news")
    config = NEWS_CATEGORY_CONFIG.get(category, {"limit": 8, "words": 150})
    err, items = fetch_google_news_rss(query, limit=config["limit"])
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
# 3-year financials. Fabricating specific profit/debt/revenue figures for
# real, currently-fundraising companies would risk misleading retail
# investors, so we don't do that. Instead this endpoint showcases a small set
# of recent, well-documented IPOs as an educational reference, with the AI
# clearly instructed to mark figures as approximate and to recommend checking
# the official prospectus (RHP/DRHP) for exact numbers.
# ---------------------------------------------------------------------------

IPO_SHOWCASE_COMPANIES = [
    {"name": "Swiggy", "symbol": "SWIGGY", "sector": "Food delivery & quick commerce"},
    {"name": "Hyundai Motor India", "symbol": "HYUNDAI", "sector": "Passenger vehicles"},
    {"name": "NTPC Green Energy", "symbol": "NTPCGREEN", "sector": "Renewable power generation"},
    {"name": "Vishal Mega Mart", "symbol": "VMM", "sector": "Retail (value fashion & FMCG)"},
    {"name": "Ola Electric Mobility", "symbol": "OLAELEC", "sector": "Electric two-wheelers"},
]


@app.route("/api/ipo/showcase")
@cache.cached(timeout=86400)
def ipo_showcase():
    api_key = get_anthropic_key()
    note = (
        "Live data on upcoming IPOs with audited financials isn't available "
        "from free APIs. The companies below are recent, well-documented IPOs "
        "shown for reference on how this section works. All figures are "
        "AI-generated approximations for education only - always verify exact "
        "numbers in the company's official prospectus (RHP/DRHP) before investing."
    )

    if not api_key:
        return jsonify({"note": note, "ipos": [], "error": "No Anthropic API key configured. Add one in Settings to generate IPO overviews."})

    system_prompt = (
        "You are a financial educator writing for an Indian retail-investor app. "
        "For each company listed, return an object with: "
        "'overview' (an ORIGINAL ~150 word plain-English description of the "
        "business and its IPO), "
        "'financials' (an object with 'years': a list of 3 recent fiscal year "
        "labels like 'FY22','FY23','FY24', and 'revenue_cr', 'profit_cr', "
        "'assets_cr', 'debt_cr': each a list of 3 APPROXIMATE numbers in INR "
        "crore, rounded, based on your general knowledge - these are "
        "illustrative estimates, not exact figures), "
        "'green_flags' (5 short bullet points - genuine positives an investor "
        "might note), and "
        "'red_flags' (5 short bullet points - genuine risks or concerns an "
        "investor might note). "
        "Be balanced and educational, not promotional. "
        "Return ONLY a valid JSON array of these objects, one per company, in "
        "the same order as the input, with no extra text."
    )

    result, err = call_claude_haiku(
        system_prompt, json.dumps(IPO_SHOWCASE_COMPANIES), api_key, max_tokens=8192
    )

    if err or not isinstance(result, list):
        return jsonify({"note": note, "ipos": [], "error": err or "Could not generate IPO data."})

    ipos = []
    for i, company in enumerate(IPO_SHOWCASE_COMPANIES):
        entry = dict(company)
        if i < len(result) and isinstance(result[i], dict):
            entry.update(result[i])
        ipos.append(entry)

    return jsonify({"note": note, "ipos": ipos})


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------


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
