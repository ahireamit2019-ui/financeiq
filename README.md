# FinanceIQ

An India-focused financial intelligence and research platform for everyday investors —
live stock report cards, market dashboard, macro/inflation trackers, commodities,
geopolitical & policy news, and a personal impact calculator. Built with a vanilla
HTML/CSS/JS frontend and a lightweight Flask backend, designed to run at **near-zero cost**.

---

## 1. Run it locally

```bash
# 1. Clone / unzip the project, then enter the folder
cd financeiq

# 2. (Recommended) create a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
python app.py
```

Open **http://localhost:5000** in your browser. Search for a stock (e.g. "Reliance",
"TCS", "HDFC Bank") to see the full report card.

> ⚠️ AI features (the scorecard, pros/cons, geopolitical impact tags) need an
> **Anthropic API key**. Add yours in the **Settings** panel (gear icon, top right) —
> it's stored only in your browser's localStorage and sent with each request.

---

## 2. Deploy for free on Render.com

1. Push this folder to a new GitHub repository.
2. On [render.com](https://render.com), click **New → Web Service**, connect your repo.
   Render will detect `render.yaml` automatically and configure:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
   - Plan: Free
3. Click **Create Web Service**. Once deployed, open the live URL — your FinanceIQ
   instance is live. Each visitor adds their own Anthropic key via Settings, so you
   don't need to pay for AI usage yourself.

(Railway.app works the same way — it will also pick up the `Procfile`.)

---

## 3. Where to get each free API key

| Service | Used for | Free tier | Get a key |
|---|---|---|---|
| **Yahoo Finance (via `yfinance`)** | Stock prices, financials, indices, commodities | No key needed | — |
| **Google News RSS** | Stock news, geopolitical/policy/business news | No key needed | — |
| **open.er-api.com** | USD/INR and other exchange rates | No key needed | — |
| **Anthropic Claude (Haiku)** | AI scorecards, pros/cons, summaries, news impact tags | Pay-as-you-go, ~$0.001/search with Haiku | https://console.anthropic.com/ |
| **NewsAPI.org** (optional, not required) | Reserved for future enhanced news quality | 100 req/day free | https://newsapi.org/ |

The app is fully functional without NewsAPI — Google News RSS is used by default and
needs no key.

---

## 4. Adding your Anthropic API key

1. Click the **gear icon** (⚙️) in the top-right corner of the app.
2. Paste your key (starts with `sk-ant-...`) into **Anthropic API Key**.
3. Click **Save Settings**.

The key is stored in your browser's `localStorage` only — it is sent to the backend
with each AI-related request via a custom header and is never logged or stored on
the server. If you're self-hosting for your own personal use, you can alternatively
set `ANTHROPIC_API_KEY` as a server environment variable (see `.env.example`) as a
fallback for all visitors.

---

## 5. Notes on data sources

- **Stock data, indices, sector heatmap, commodities** — live via `yfinance`
  (Yahoo Finance), cached for 1–5 minutes to respect rate limits.
- **News** — live via Google News RSS, no key required.
- **CPI/WPI, RBI repo rate, GDP/IIP/PMI** — curated from the latest published RBI /
  MoSPI releases. These change only periodically; update the values in
  `app.py` (`/api/macro/*` endpoints) when new official releases come out.
- **FII/DII activity** — no reliable free real-time API exists, so the dashboard
  links directly to NSE's official daily report instead of showing estimated numbers.

---

## 6. Project structure

```
financeiq/
├── app.py                  # Flask backend — all API endpoints
├── requirements.txt
├── .env.example
├── Procfile                 # for Render/Railway
├── render.yaml              # one-click Render deployment config
├── static/
│   ├── css/style.css        # full dark/light theme
│   └── js/
│       ├── api.js           # fetch helpers + formatting
│       ├── charts.js         # Chart.js builders
│       ├── stock.js          # stock search + report card
│       ├── market.js         # dashboard + research sections
│       └── main.js           # routing, nav, settings
└── templates/
    └── index.html           # single-page app shell
```
