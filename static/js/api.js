/* ============================================================
   FinanceIQ — api.js
   All fetch calls to the Flask backend live here.
   ============================================================ */

const API_BASE = "";

/** Build common headers, including the user's Anthropic key if set. */
function buildHeaders() {
  const headers = {};
  const key = localStorage.getItem("financeiq_anthropic_key");
  if (key) headers["X-Anthropic-Key"] = key;
  return headers;
}

/** Generic GET helper with error handling. Always resolves (never throws). */
async function apiGet(path) {
  try {
    const res = await fetch(`${API_BASE}${path}`, { headers: buildHeaders() });
    if (!res.ok) {
      return { error: `Server returned ${res.status}` };
    }
    return await res.json();
  } catch (err) {
    return { error: `Network error: ${err.message}` };
  }
}

const Api = {
  searchStocks: (query) => apiGet(`/api/search/${encodeURIComponent(query)}`),

  getStock: (symbol) => apiGet(`/api/stock/${encodeURIComponent(symbol)}`),
  getStockNews: (symbol) => apiGet(`/api/stock/${encodeURIComponent(symbol)}/news`),
  getStockScorecard: (symbol) => apiGet(`/api/stock/${encodeURIComponent(symbol)}/scorecard`),
  getStockFinancials: (symbol) => apiGet(`/api/stock/${encodeURIComponent(symbol)}/financials`),
  getCorporateActions: (symbol) => apiGet(`/api/stock/${encodeURIComponent(symbol)}/corporate-actions`),

  getMarketTicker: () => apiGet(`/api/market/ticker`),
  getMarketOverview: () => apiGet(`/api/market/overview`),
  getWatchlist: (symbols) => apiGet(`/api/watchlist/${encodeURIComponent(symbols)}`),
  getHeatmap: () => apiGet(`/api/market/heatmap`),
  getSectorStocks: (key) => apiGet(`/api/market/sector/${encodeURIComponent(key)}/stocks`),
  getGlobalIndices: () => apiGet(`/api/market/global`),
  getGlobalIndexStocks: (indexName) => apiGet(`/api/market/global/${encodeURIComponent(indexName)}/stocks`),
  getGlobalStock: (symbol) => apiGet(`/api/global-stock/${encodeURIComponent(symbol)}`),
  get52WeekData: () => apiGet(`/api/market/52week`),
  getMostActive: () => apiGet(`/api/market/active`),

  getInflation: () => apiGet(`/api/macro/inflation`),
  getRbi: () => apiGet(`/api/macro/rbi`),
  getGrowth: () => apiGet(`/api/macro/growth`),
  getCommodities: () => apiGet(`/api/commodities`),
  getExchangeRates: () => apiGet(`/api/exchange-rates`),

  getNewsByCategory: (category) => apiGet(`/api/news/${encodeURIComponent(category)}`),
  getEarningsCalendar: () => apiGet(`/api/earnings/calendar`),
  getCommodityNews: (name) => apiGet(`/api/commodities/${encodeURIComponent(name)}/news`),
  getIpoShowcase: () => apiGet(`/api/ipo/showcase`),
  getTopMutualFunds: () => apiGet(`/api/mutualfunds/top`),
  getMutualFundDetail: (schemeCode) => apiGet(`/api/mutualfunds/${encodeURIComponent(schemeCode)}/detail`),
  getPriceHistory: (label, period) => apiGet(`/api/history/${encodeURIComponent(label)}?period=${encodeURIComponent(period || "1y")}`),
};

/* ============================================================
   Formatting helpers (used across the app)
   ============================================================ */

function formatIndian(num, decimals = 2) {
  if (num === null || num === undefined || isNaN(num)) return "—";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: decimals }).format(num);
}

function formatRupee(num, decimals = 2) {
  if (num === null || num === undefined || isNaN(num)) return "—";
  return `₹${formatIndian(num, decimals)}`;
}

function formatCrore(num) {
  if (num === null || num === undefined || isNaN(num)) return "—";
  if (Math.abs(num) >= 100000) {
    return `₹${formatIndian(num / 100000, 2)} L Cr`; // lakh crore (≥1 lakh crore)
  }
  return `₹${formatIndian(num, 2)} Cr`;
}

function formatPct(num, decimals = 2) {
  if (num === null || num === undefined || isNaN(num)) return "—";
  const sign = num > 0 ? "+" : "";
  return `${sign}${formatIndian(num, decimals)}%`;
}

function pctClass(num) {
  if (num === null || num === undefined || isNaN(num)) return "";
  return num >= 0 ? "up" : "down";
}

function arrow(num) {
  if (num === null || num === undefined || isNaN(num)) return "";
  return num >= 0 ? "▲" : "▼";
}

/** Render a friendly error block with a retry button. */
function errorBlock(message, retryFn) {
  const id = `retry-${Math.random().toString(36).slice(2)}`;
  setTimeout(() => {
    const btn = document.getElementById(id);
    if (btn) btn.addEventListener("click", retryFn);
  }, 0);
  return `
    <div class="error-state">
      <p>⚠️ ${message || "Something went wrong while fetching data."}</p>
      <button class="retry-btn" id="${id}">Retry</button>
    </div>`;
}
