/* ============================================================
   FinanceIQ — market.js
   Live ticker, dashboard cards, and all research-section pages
   ============================================================ */

/* ============================ LIVE TICKER ============================ */

async function loadTicker() {
  const track = document.getElementById("tickerTrack");
  const data = await Api.getMarketTicker();

  if (data.error) {
    track.innerHTML = `<span class="ticker-item">⚠️ Could not load live market data</span>`;
    return;
  }

  const items = Object.entries(data).map(([label, v]) => {
    const cls = pctClass(v.change_pct);
    const priceStr = label === "USD/INR" ? formatRupee(v.price) : (label === "Gold" || label === "Crude Oil") ? `$${formatIndian(v.price)}` : formatIndian(v.price);
    return `
      <span class="ticker-item ticker-clickable" data-label="${label}">
        <span class="label">${label}</span>
        <span class="value">${priceStr}</span>
        <span class="change ${cls}">${arrow(v.change_pct)} ${formatPct(v.change_pct)}</span>
      </span>`;
  });

  // duplicate for seamless scroll
  track.innerHTML = items.join("") + items.join("");

  track.querySelectorAll(".ticker-clickable").forEach((el) => {
    el.addEventListener("click", () => openHistoryChartModal(el.dataset.label));
  });
}

/* ============================ DASHBOARD ============================ */

async function loadDashboard() {
  loadGainersLosers();
  loadWatchlist();
  loadInflationSnapshot();
  loadRbiSnapshot();
  loadTrendingStocks();
  loadFiiDii();
  loadCurrencyConverter();
}

async function loadWatchlist() {
  const el = document.getElementById("watchlistSection");
  if (!el) return;

  const raw = localStorage.getItem("financeiq_watchlist") || "";
  const symbols = raw.split(",").map((s) => s.trim()).filter(Boolean).slice(0, 10);

  el.classList.remove("skeleton-block");

  if (symbols.length === 0) {
    el.innerHTML = `<p class="card-note">No stocks in your watchlist yet. Add up to 10 NSE symbols (comma separated, e.g. RELIANCE, TCS, INFY, HDFCBANK) under Settings → Default Watchlist.</p>`;
    return;
  }

  el.innerHTML = `<div class="skeleton-row"></div><div class="skeleton-row"></div>`;

  const data = await Api.getWatchlist(symbols.join(","));
  if (data.error) {
    el.innerHTML = errorBlock(data.error, loadWatchlist);
    return;
  }

  if (!data.items || data.items.length === 0) {
    el.innerHTML = `<p class="card-note">Could not load watchlist data.</p>`;
    return;
  }

  el.innerHTML = `
    <div class="mover-list">
      ${data.items.map((item) => `
        <div class="mover-row">
          <span class="symbol stock-link" data-symbol="${item.symbol}">${item.symbol}</span>
          <span class="price">${item.price !== null ? formatRupee(item.price) : "—"}</span>
          <span class="pct ${pctClass(item.change_pct)}">${item.change_pct !== null && item.change_pct !== undefined ? `${arrow(item.change_pct)} ${formatPct(item.change_pct)}` : ""}</span>
        </div>`).join("")}
    </div>`;
}

async function loadGainersLosers() {
  const gainersEl = document.getElementById("gainersList");
  const losersEl = document.getElementById("losersList");

  const data = await Api.getMarketOverview();

  if (data.error) {
    gainersEl.innerHTML = errorBlock(data.error, loadGainersLosers);
    losersEl.innerHTML = errorBlock(data.error, loadGainersLosers);
    return;
  }

  const renderMovers = (list) => list.map((m) => `
    <div class="mover-row">
      <span class="symbol stock-link" data-symbol="${m.symbol}">${m.symbol}</span>
      <span class="price">${formatRupee(m.price)}</span>
      <span class="pct ${pctClass(m.change_pct)}">${arrow(m.change_pct)} ${formatPct(m.change_pct)}</span>
    </div>`).join("");

  gainersEl.innerHTML = renderMovers(data.gainers || []);
  losersEl.innerHTML = renderMovers(data.losers || []);

  // also feed the index overview cards on the market page if present
  renderIndexOverview(data.indices);
}

function renderIndexOverview(indices) {
  const el = document.getElementById("indexOverview");
  if (!el || !indices) return;

  el.innerHTML = Object.entries(indices).map(([label, v]) => `
    <div class="card">
      <h3 class="card-title">${label}</h3>
      <div class="price-now">${formatIndian(v.price)}</div>
      <div class="price-change ${pctClass(v.change_pct)}">${arrow(v.change_pct)} ${formatPct(v.change_pct)}</div>
    </div>`).join("");
}

async function loadInflationSnapshot() {
  const el = document.getElementById("inflationSnapshot");
  const data = await Api.getInflation();

  if (data.error) {
    el.innerHTML = errorBlock(data.error, loadInflationSnapshot);
    return;
  }

  const cpiTrend = data.cpi.trend === "down" ? "▼" : "▲";
  const wpiTrend = data.wpi.trend === "down" ? "▼" : "▲";

  el.innerHTML = `
    <div class="metric-box" style="margin-bottom:8px;">
      <div class="metric-label">CPI Inflation (${data.cpi.month})</div>
      <div class="metric-value">${formatPct(data.cpi.latest_pct)} <span style="font-size:0.9rem;color:var(--text-muted);">${cpiTrend}</span></div>
    </div>
    <div class="metric-box">
      <div class="metric-label">WPI Inflation (${data.wpi.month})</div>
      <div class="metric-value">${formatPct(data.wpi.latest_pct)} <span style="font-size:0.9rem;color:var(--text-muted);">${wpiTrend}</span></div>
    </div>`;

  window._inflationData = data;
}

async function loadRbiSnapshot() {
  const el = document.getElementById("rbiSnapshot");
  const data = await Api.getRbi();

  if (data.error) {
    el.innerHTML = errorBlock(data.error, loadRbiSnapshot);
    return;
  }

  el.innerHTML = `
    <div class="metric-box" style="margin-bottom:8px;">
      <div class="metric-label">Repo Rate</div>
      <div class="metric-value">${formatPct(data.repo_rate)}</div>
    </div>
    <div class="metric-box">
      <div class="metric-label">Last Change</div>
      <div class="metric-value" style="font-size:0.95rem;">${data.last_change} on ${data.last_change_date}</div>
    </div>
    <p class="card-note">Stance: ${data.stance}</p>`;

  window._rbiData = data;
}

async function loadTrendingStocks() {
  const el = document.getElementById("trendingStocks");
  const data = await Api.getMostActive();

  if (data.error) {
    el.innerHTML = errorBlock(data.error, loadTrendingStocks);
    return;
  }

  const top = (data.active || []).slice(0, 5);
  if (!top.length) {
    el.innerHTML = `<p class="card-note">No data available right now.</p>`;
    return;
  }

  el.innerHTML = `
    <div class="mover-list">
      ${top.map((s) => `
        <div class="mover-row">
          <span class="symbol stock-link" data-symbol="${s.symbol}">${s.symbol}</span>
          <span class="price">${formatRupee(s.price)}</span>
          <span class="pct">Vol: ${formatIndian(s.volume, 0)}</span>
        </div>`).join("")}
    </div>`;
}

async function loadFiiDii() {
  const el = document.getElementById("fiiDiiActivity");
  // No reliable free real-time API exists for FII/DII flows — show a clear
  // placeholder pointing the user to the official NSE source instead of
  // fabricating numbers.
  el.innerHTML = `
    <div class="metric-box">
      <div class="metric-label">FII / DII Net Activity</div>
      <div class="metric-value" style="font-size:0.95rem;">Live data not available from a free API</div>
    </div>
    <p class="card-note">
      FII/DII cash market activity is published daily by NSE after market hours.
      Check the official provisional data at
      <a href="https://www.nseindia.com/reports/fii-dii" target="_blank" rel="noopener">nseindia.com/reports/fii-dii</a>.
    </p>`;
}

/* ============================ STOCK MARKET PAGE ============================ */

async function loadMarketPage() {
  // index overview is filled by loadGainersLosers (shares the same API call)
  if (!document.getElementById("indexOverview").dataset.loaded) {
    loadGainersLosers();
    document.getElementById("indexOverview").dataset.loaded = "1";
  }
  loadHeatmap();
  loadMostActiveTable();
  loadIpoSection();
}

/* ============================ IPO SPOTLIGHT ============================ */

async function loadIpoSection() {
  const el = document.getElementById("ipoGrid");
  const data = await Api.getIpoShowcase();

  if (data.error && (!data.ipos || data.ipos.length === 0)) {
    el.innerHTML = errorBlock(data.error, loadIpoSection);
    return;
  }

  if (!data.ipos || data.ipos.length === 0) {
    el.innerHTML = `<p class="card-note">No IPO data available right now.</p>`;
    return;
  }

  el.innerHTML = data.ipos.map((ipo, i) => `
    <div class="card ipo-card" data-ipo-index="${i}">
      <div class="ipo-status-badge ipo-status-${(ipo.status || "").toLowerCase().replace(/\s+/g, "-")}">${ipo.status || ""}</div>
      <div class="ipo-name">${ipo.name}</div>
      <div class="ipo-sector">${ipo.sector || ""}</div>
      <div class="ipo-price-band">${ipo.price_band || "Price band: Not yet announced"}</div>
      <div class="ipo-cta">Tap for full details →</div>
    </div>`).join("");

  el.querySelectorAll(".ipo-card").forEach((card) => {
    card.addEventListener("click", () => openIpoModal(data.ipos[Number(card.dataset.ipoIndex)]));
  });
}

function openIpoModal(ipo) {
  const greenFlags = (ipo.green_flags || []).map((f) => `<li>${f}</li>`).join("");
  const redFlags = (ipo.red_flags || []).map((f) => `<li>${f}</li>`).join("");

  const detailsTable = `
    <div class="table-wrap">
      <table class="data-table">
        <tbody>
          <tr><td>Status</td><td>${ipo.status || "—"}</td></tr>
          <tr><td>Price Band</td><td>${ipo.price_band || "Not yet announced"}</td></tr>
          <tr><td>Lot Size</td><td>${ipo.lot_size || "Not yet announced"}</td></tr>
          <tr><td>Min. Investment (Retail)</td><td>${ipo.min_investment || "Not yet announced"}</td></tr>
          <tr><td>Issue Dates</td><td>${ipo.issue_dates || "TBA"}</td></tr>
          <tr><td>Issue Size</td><td>${ipo.issue_size || "Not disclosed"}</td></tr>
        </tbody>
      </table>
    </div>
  `;

  openModal(`
    <div class="modal-title">${ipo.name}</div>
    <div class="modal-subtitle">${ipo.sector || ""}</div>

    <div class="modal-section-title">IPO Details</div>
    ${detailsTable}

    <div class="modal-section-title">About the Company</div>
    <p>${ipo.about || "No overview available."}</p>

    <div class="modal-section-title">Green &amp; Red Flags</div>
    <div class="flags-grid">
      <div>
        <h4 style="margin:0 0 8px;color:var(--positive);font-family:var(--font-data);">✅ Green Flags</h4>
        <ul class="pros-cons-list positives">${greenFlags || "<li>Not available</li>"}</ul>
      </div>
      <div>
        <h4 style="margin:0 0 8px;color:var(--negative);font-family:var(--font-data);">❌ Red Flags</h4>
        <ul class="pros-cons-list negatives">${redFlags || "<li>Not available</li>"}</ul>
      </div>
    </div>

    <p class="card-note">${ipo.source_note || ""} Always verify exact details in the official prospectus (RHP/DRHP) and on NSE/BSE before investing.</p>
  `);
}

const SECTOR_LABELS = {
  Auto: "Auto", Bank: "Bank", IT: "IT", Pharma: "Pharma", FMCG: "FMCG",
  Metal: "Metal", Realty: "Realty", Energy: "Energy", Infra: "Infra", Media: "Media",
  Defence: "Defence", "Nifty Midcap 150": "Midcap 150", "Nifty Smallcap 250": "Smallcap 250",
};

async function loadHeatmap() {
  const el = document.getElementById("sectorHeatmap");
  const data = await Api.getHeatmap();

  if (data.error) {
    el.innerHTML = errorBlock(data.error, loadHeatmap);
    return;
  }

  el.classList.remove("skeleton-block");
  el.innerHTML = (data.sectors || []).map((s) => {
    const pct = s.change_pct;
    const intensity = Math.min(Math.abs(pct) / 3, 1); // scale: 3% change = full intensity
    const base = pct >= 0 ? "16,185,129" : "239,68,68";
    const bg = `rgba(${base}, ${0.25 + intensity * 0.6})`;
    return `
      <div class="heatmap-cell heatmap-clickable" style="background:${bg}" data-key="${s.key || s.sector}" data-sector="${s.sector}">
        ${SECTOR_LABELS[s.sector] || s.sector}
        <span class="pct">${formatPct(pct)}</span>
      </div>`;
  }).join("");

  el.querySelectorAll(".heatmap-clickable").forEach((cell) => {
    cell.addEventListener("click", () => openSectorStocksModal(cell.dataset.key, cell.dataset.sector));
  });
}

async function openSectorStocksModal(key, sectorLabel) {
  openModal(`
    <div class="modal-title">${SECTOR_LABELS[sectorLabel] || sectorLabel}</div>
    <div class="modal-subtitle">Representative stocks and current prices</div>
    <div id="sectorStocksList" class="skeleton-block" style="min-height:240px;margin-top:14px;"></div>
  `);

  const data = await Api.getSectorStocks(key);
  const listEl = document.getElementById("sectorStocksList");
  if (!listEl) return; // modal closed before response arrived

  if (data.error) {
    listEl.innerHTML = errorBlock(data.error, () => openSectorStocksModal(key, sectorLabel));
    return;
  }

  listEl.classList.remove("skeleton-block");
  listEl.innerHTML = `
    <div class="table-wrap">
      <table class="data-table sector-stocks-table">
        <thead><tr><th>Stock</th><th>Price</th><th>Change</th></tr></thead>
        <tbody>
          ${(data.stocks || []).map((s) => `
            <tr class="stock-row-clickable" data-symbol="${s.symbol}">
              <td>${s.symbol}</td>
              <td>${s.price !== null ? formatRupee(s.price) : "—"}</td>
              <td class="${pctClass(s.change_pct)}">${s.change_pct !== null ? `${arrow(s.change_pct)} ${formatPct(s.change_pct)}` : "—"}</td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>
  `;

  listEl.querySelectorAll(".stock-row-clickable").forEach((row) => {
    row.addEventListener("click", () => {
      closeModal();
      searchStock(row.dataset.symbol);
    });
  });
}

async function loadMostActiveTable() {
  const el = document.getElementById("mostActive");
  const data = await Api.getMostActive();

  if (data.error) {
    el.innerHTML = errorBlock(data.error, loadMostActiveTable);
    return;
  }

  el.classList.remove("skeleton-block");
  el.innerHTML = `
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>Symbol</th><th>Price</th><th>Volume</th></tr></thead>
        <tbody>
          ${(data.active || []).map((s) => `
            <tr><td class="stock-link" data-symbol="${s.symbol}">${s.symbol}</td><td>${formatRupee(s.price)}</td><td>${formatIndian(s.volume, 0)}</td></tr>
          `).join("")}
        </tbody>
      </table>
    </div>`;
}

/* ============================ MACRO ECONOMY PAGE ============================ */

async function loadMacroPage() {
  const el = document.getElementById("macroSummary");
  const [growth, rbi] = await Promise.all([Api.getGrowth(), Api.getRbi()]);

  if (growth.error || rbi.error) {
    el.innerHTML = errorBlock(growth.error || rbi.error, loadMacroPage);
    return;
  }

  el.classList.remove("skeleton-block");
  el.innerHTML = `
    <div class="card">
      <h3 class="card-title">GDP Growth</h3>
      <div class="price-now">${formatPct(growth.gdp_growth_pct)}</div>
      <p class="card-note">${growth.gdp_quarter}</p>
    </div>
    <div class="card">
      <h3 class="card-title">PMI (${growth.pmi.month})</h3>
      <div class="price-now">${formatIndian(growth.pmi.manufacturing)} <span style="font-size:0.9rem;color:var(--text-muted);">Mfg</span></div>
      <div class="price-now">${formatIndian(growth.pmi.services)} <span style="font-size:0.9rem;color:var(--text-muted);">Services</span></div>
      <p class="card-note">Above 50 = expansion</p>
    </div>
    <div class="card">
      <h3 class="card-title">RBI Repo Rate</h3>
      <div class="price-now">${formatPct(rbi.repo_rate)}</div>
      <p class="card-note">CRR: ${formatPct(rbi.crr)} · SLR: ${formatPct(rbi.slr)} · Stance: ${rbi.stance}</p>
    </div>`;

  const dataSourceEl = document.getElementById("macroDataSource");
  if (dataSourceEl) dataSourceEl.textContent = growth.source || "";

  const months = ["Jun","Jul","Aug","Sep","Oct","Nov","Dec","Jan","Feb","Mar","Apr","May"];
  buildLineChart("iipChart", months, [
    { label: "IIP Growth %", data: growth.iip.history_12m, color: CHART_COLORS.primary },
  ]);

  buildLineChart("repoChart", rbi.history.map((h) => h.date), [
    { label: "Repo Rate %", data: rbi.history.map((h) => h.repo_rate), color: CHART_COLORS.accent },
  ]);

  loadMacroNews();
}

async function loadMacroNews() {
  const el = document.getElementById("macroNews");
  const data = await Api.getNewsByCategory("macro");

  if (data.error) {
    el.innerHTML = errorBlock(data.error, loadMacroNews);
    return;
  }

  el.classList.remove("skeleton-block");
  el.innerHTML = renderNewsList(data.news, { limit: 10 });
}

/* ============================ INFLATION TRACKER PAGE ============================ */

async function loadInflationPage() {
  const data = await Api.getInflation();
  const noteEl = document.getElementById("inflationImpactNote");

  if (data.error) {
    noteEl.innerHTML = errorBlock(data.error, loadInflationPage);
    return;
  }

  const cats = data.cpi.categories;
  buildBarChart("cpiCategoryChart", Object.keys(cats), Object.values(cats), {
    label: "CPI %", color: CHART_COLORS.primary,
  });

  const months = ["Jun","Jul","Aug","Sep","Oct","Nov","Dec","Jan","Feb","Mar","Apr","May"];
  buildLineChart("cpiWpiChart", months, [
    { label: "CPI %", data: data.cpi.history_12m, color: CHART_COLORS.primary },
    { label: "WPI %", data: data.wpi.history_12m, color: CHART_COLORS.accent, fill: false },
  ]);

  noteEl.textContent = data.impact_note;

  const sourceEl = document.getElementById("inflationDataSource");
  if (sourceEl) {
    sourceEl.textContent = `CPI: ${formatPct(data.cpi.latest_pct)} (${data.cpi.month}) · WPI: ${formatPct(data.wpi.latest_pct)} (${data.wpi.month}) · ${data.source || ""}`;
  }

  loadInflationNews();
}

async function loadInflationNews() {
  const el = document.getElementById("inflationNews");
  const data = await Api.getNewsByCategory("inflation");

  if (data.error) {
    el.innerHTML = errorBlock(data.error, loadInflationNews);
    return;
  }

  el.classList.remove("skeleton-block");
  el.innerHTML = renderNewsList(data.news, { limit: 10 });
}

/* ============================ TAX UPDATES PAGE ============================ */

async function loadTaxPage() {
  const el = document.getElementById("taxNews");
  const data = await Api.getNewsByCategory("tax");

  if (data.error) {
    el.innerHTML = errorBlock(data.error, loadTaxPage);
    return;
  }

  el.classList.remove("skeleton-block");
  el.innerHTML = renderNewsList(data.news, { limit: 10 });
}

/* ---- Tax computation & savings calculator (FY 2025-26 slabs) ---- */

const NEW_REGIME_SLABS = [
  [400000, 0],
  [800000, 0.05],
  [1200000, 0.10],
  [1600000, 0.15],
  [2000000, 0.20],
  [2400000, 0.25],
  [Infinity, 0.30],
];

const OLD_REGIME_SLABS = [
  [250000, 0],
  [500000, 0.05],
  [1000000, 0.20],
  [Infinity, 0.30],
];

const CESS_RATE = 0.04;

/** Compute tax for a taxable income against a slab table. Returns {tax, marginalRate}. */
function slabTax(taxableIncome, slabs) {
  let tax = 0;
  let prevLimit = 0;
  let marginalRate = 0;
  for (const [limit, rate] of slabs) {
    if (taxableIncome > prevLimit) {
      const slice = Math.min(taxableIncome, limit) - prevLimit;
      tax += slice * rate;
      marginalRate = rate;
    }
    prevLimit = limit;
    if (taxableIncome <= limit) break;
  }
  return { tax, marginalRate };
}

function computeRegimeTax(taxableIncome, slabs, rebateThreshold, rebateMax) {
  taxableIncome = Math.max(0, taxableIncome);
  const { tax: baseTax, marginalRate } = slabTax(taxableIncome, slabs);
  let rebate = 0;
  if (taxableIncome <= rebateThreshold) {
    rebate = Math.min(baseTax, rebateMax);
  }
  const afterRebate = Math.max(0, baseTax - rebate);
  const cess = afterRebate * CESS_RATE;
  return { taxableIncome, baseTax, rebate, afterRebate, cess, total: afterRebate + cess, marginalRate };
}

function setupTaxCalculator() {
  const salaryInput = document.getElementById("taxSalaryInput");
  const c80c = document.getElementById("tax80cInput");
  const nps = document.getElementById("taxNpsInput");
  const c80d = document.getElementById("tax80dInput");
  const homeLoan = document.getElementById("taxHomeLoanInput");

  if (!salaryInput) return; // page not on this build

  [salaryInput, c80c, nps, c80d, homeLoan].forEach((el) => el.addEventListener("input", updateTaxCalc));
  updateTaxCalc();
}

function updateTaxCalc() {
  const resultEl = document.getElementById("taxCalcResult");
  if (!resultEl) return;

  const gross = parseFloat(document.getElementById("taxSalaryInput").value) || 0;
  const c80c = Math.min(parseFloat(document.getElementById("tax80cInput").value) || 0, 150000);
  const nps = Math.min(parseFloat(document.getElementById("taxNpsInput").value) || 0, 50000);
  const c80d = Math.min(parseFloat(document.getElementById("tax80dInput").value) || 0, 50000);
  const homeLoan = Math.min(parseFloat(document.getElementById("taxHomeLoanInput").value) || 0, 200000);

  const STD_DEDUCTION_NEW = 75000;
  const STD_DEDUCTION_OLD = 50000;

  // New regime: only the standard deduction applies
  const newTaxable = gross - STD_DEDUCTION_NEW;
  const newResult = computeRegimeTax(newTaxable, NEW_REGIME_SLABS, 1200000, 60000);

  // Old regime: standard deduction + all entered deductions
  const totalDeductions = c80c + nps + c80d + homeLoan;
  const oldTaxableWithDeductions = gross - STD_DEDUCTION_OLD - totalDeductions;
  const oldResultWithDeductions = computeRegimeTax(oldTaxableWithDeductions, OLD_REGIME_SLABS, 500000, 12500);

  // Old regime without the optional deductions, for comparison (how much they save)
  const oldTaxableNoDeductions = gross - STD_DEDUCTION_OLD;
  const oldResultNoDeductions = computeRegimeTax(oldTaxableNoDeductions, OLD_REGIME_SLABS, 500000, 12500);
  const deductionSavings = oldResultNoDeductions.total - oldResultWithDeductions.total;

  const better = newResult.total <= oldResultWithDeductions.total ? "new" : "old";
  const betterLabel = better === "new" ? "New Regime" : "Old Regime (with your deductions)";
  const difference = Math.abs(newResult.total - oldResultWithDeductions.total);

  // Per-section savings breakdown (using old regime marginal rate incl. cess)
  const rate = oldResultNoDeductions.marginalRate * (1 + CESS_RATE);
  const breakdown = [
    { label: "Section 80C (PPF/ELSS/EPF/insurance)", amount: c80c },
    { label: "NPS — 80CCD(1B)", amount: nps },
    { label: "Health insurance — 80D", amount: c80d },
    { label: "Home loan interest — 24(b)", amount: homeLoan },
  ].filter((d) => d.amount > 0).map((d) => ({ ...d, saving: d.amount * rate }));

  resultEl.innerHTML = `
    <div class="grid grid-2" style="margin-bottom:0;">
      <div class="metric-box">
        <div class="metric-label">New Regime — Estimated Tax</div>
        <div class="metric-value">${formatRupee(newResult.total, 0)}</div>
        <div class="card-note">Taxable income: ${formatRupee(newResult.taxableIncome, 0)} ${newResult.rebate > 0 ? "(zero tax — covered by Section 87A rebate)" : ""}</div>
      </div>
      <div class="metric-box">
        <div class="metric-label">Old Regime — Estimated Tax (with your deductions)</div>
        <div class="metric-value">${formatRupee(oldResultWithDeductions.total, 0)}</div>
        <div class="card-note">Taxable income: ${formatRupee(oldResultWithDeductions.taxableIncome, 0)} ${oldResultWithDeductions.rebate > 0 ? "(zero tax — covered by Section 87A rebate)" : ""}</div>
      </div>
    </div>
    <p style="margin-top:14px;">
      Based on these numbers, the <strong>${betterLabel}</strong> looks better for you —
      it saves you about <strong>${formatRupee(difference, 0)}</strong> compared to the other option.
    </p>
    ${breakdown.length ? `
      <div class="modal-section-title" style="margin-top:14px;">Where your deductions help (Old Regime)</div>
      <ul class="bullet-list">
        ${breakdown.map((d) => `<li><strong>${d.label}</strong>: ₹${formatIndian(d.amount, 0)} deducted ≈ <strong>${formatRupee(d.saving, 0)}</strong> less tax at your ~${formatPct(rate * 100, 0)} marginal rate (incl. cess)</li>`).join("")}
        <li>Total estimated tax saved by these deductions in the Old Regime: <strong>${formatRupee(deductionSavings, 0)}</strong> (vs. claiming none)</li>
      </ul>
    ` : `<p class="card-note">Add 80C/80D/NPS/home-loan amounts above to see exactly how much tax each one saves you under the Old Regime.</p>`}
    <p class="card-note">
      Estimates only — based on FY 2025-26 slabs, standard deduction, Section 87A rebate and 4% health &amp; education cess.
      Excludes employer NPS (80CCD(2)), HRA, and other allowances. Confirm your exact liability on the official income tax portal.
    </p>
  `;
}

/* ============================ BUSINESS & EARNINGS PAGE ============================ */

async function loadEarningsPage() {
  const calEl = document.getElementById("earningsCalendar");
  const newsEl = document.getElementById("businessNews");

  const [cal, news] = await Promise.all([Api.getEarningsCalendar(), Api.getNewsByCategory("business")]);

  if (cal.error) {
    calEl.innerHTML = errorBlock(cal.error, loadEarningsPage);
  } else {
    calEl.classList.remove("skeleton-block");
    if (!cal.calendar || !cal.calendar.length) {
      calEl.innerHTML = `<p class="card-note">No confirmed earnings dates from Nifty 50 companies in the next 7 days. Companies often announce dates with short notice — check back soon.</p>`;
    } else {
      calEl.innerHTML = `
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>Company</th><th>Expected Date</th></tr></thead>
            <tbody>
              ${cal.calendar.map((c) => `<tr><td class="stock-link" data-symbol="${c.symbol}">${c.symbol}</td><td>${c.date}</td></tr>`).join("")}
            </tbody>
          </table>
        </div>`;
    }
  }

  if (news.error) {
    newsEl.innerHTML = errorBlock(news.error, loadEarningsPage);
  } else {
    newsEl.classList.remove("skeleton-block");
    newsEl.innerHTML = renderNewsList(news.news, { limit: 8 });
  }
}

/* ============================ GEOPOLITICAL IMPACT PAGE ============================ */

async function loadGeoPage() {
  const el = document.getElementById("geoNews");
  const data = await Api.getNewsByCategory("geo");

  if (data.error) {
    el.innerHTML = errorBlock(data.error, loadGeoPage);
    return;
  }

  el.classList.remove("skeleton-block");
  el.innerHTML = renderNewsList(data.news, { showImpact: true, limit: 10 });
}

/* ============================ COMMODITIES PAGE ============================ */

async function loadCommoditiesPage() {
  const el = document.getElementById("commoditiesGrid");
  const data = await Api.getCommodities();

  if (data.error) {
    el.innerHTML = errorBlock(data.error, loadCommoditiesPage);
    return;
  }

  el.innerHTML = Object.entries(data).map(([name, v], i) => {
    const canvasId = `spark-${i}`;
    const priceDisplay = v.display_price !== null && v.display_price !== undefined
      ? (v.unit === "INR/10g" ? formatRupee(v.display_price, 0) : `$${formatIndian(v.display_price)}`)
      : "—";
    return `
      <div class="card commodity-card commodity-clickable" data-commodity="${name}" style="cursor:pointer;">
        <div class="commodity-name">${name}</div>
        <div class="commodity-price">${priceDisplay} <span style="font-size:0.7rem;color:var(--text-muted);">${v.unit !== "USD" ? "" : "/unit"}</span></div>
        <div class="commodity-change ${pctClass(v.change_pct)}">${arrow(v.change_pct)} ${formatPct(v.change_pct)}</div>
        <div class="spark-wrap"><canvas id="${canvasId}"></canvas></div>
        <div class="ipo-cta">Tap for latest news →</div>
      </div>`;
  }).join("");

  // build sparklines after DOM update
  Object.entries(data).forEach(([name, v], i) => {
    if (v.sparkline && v.sparkline.length) {
      const color = (v.change_pct ?? 0) >= 0 ? CHART_COLORS.positive : CHART_COLORS.negative;
      buildSparkline(`spark-${i}`, v.sparkline, color);
    }
  });

  // wire up click -> news popup
  el.querySelectorAll(".commodity-clickable").forEach((card) => {
    card.addEventListener("click", () => openCommodityNewsModal(card.dataset.commodity, data[card.dataset.commodity]));
  });
}

async function openCommodityNewsModal(name, commodityData) {
  const priceDisplay = commodityData && commodityData.display_price !== null && commodityData.display_price !== undefined
    ? (commodityData.unit === "INR/10g" ? formatRupee(commodityData.display_price, 0) : `$${formatIndian(commodityData.display_price)}`)
    : "—";
  const changeClass = pctClass(commodityData?.change_pct);

  const subtitle = `
    Current: <strong>${priceDisplay}</strong>
    <span class="${changeClass}">${arrow(commodityData?.change_pct)} ${formatPct(commodityData?.change_pct)}</span>
  `;

  const extraHtml = `
    <div class="modal-section-title">Latest News</div>
    <div id="commodityModalNews"><div class="skeleton-block" style="min-height:200px"></div></div>
  `;

  await openHistoryChartModal(name, { subtitle, extraHtml });

  const data = await Api.getCommodityNews(name);
  const newsEl = document.getElementById("commodityModalNews");
  if (!newsEl) return; // modal closed before response arrived

  if (data.error) {
    newsEl.innerHTML = errorBlock(data.error, () => openCommodityNewsModal(name, commodityData));
    return;
  }

  newsEl.innerHTML = renderNewsList(data.news, { limit: 5 });
}

/* ============================ MUTUAL FUNDS PAGE ============================ */

async function loadMutualFundsPage() {
  const el = document.getElementById("mutualFundsTable");
  if (!el) return;

  const data = await Api.getTopMutualFunds();

  if (data.error) {
    el.classList.remove("skeleton-block");
    el.innerHTML = errorBlock(data.error, loadMutualFundsPage);
    return;
  }

  if (!data.funds || data.funds.length === 0) {
    el.classList.remove("skeleton-block");
    el.innerHTML = `<p class="card-note">No mutual fund data available right now.</p>`;
    return;
  }

  el.classList.remove("skeleton-block");
  el.innerHTML = `
    <div class="table-wrap">
      <table class="data-table mf-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Fund Name</th>
            <th>Category</th>
            <th>NAV</th>
            <th>1Y Return</th>
            <th>3Y CAGR</th>
          </tr>
        </thead>
        <tbody>
          ${data.funds.map((f, i) => `
            <tr>
              <td>${i + 1}</td>
              <td>
                <div class="mf-name">${f.name || "—"}</div>
                <div class="mf-house">${f.fund_house || ""}</div>
              </td>
              <td>${f.category || "—"}</td>
              <td>${f.nav ? formatRupee(f.nav, 2) : "—"}</td>
              <td class="${pctClass(f.return_1y)}">${f.return_1y !== null && f.return_1y !== undefined ? formatPct(f.return_1y) : "—"}</td>
              <td class="${pctClass(f.return_3y_cagr)}">${f.return_3y_cagr !== null && f.return_3y_cagr !== undefined ? formatPct(f.return_3y_cagr) : "—"}</td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>
  `;
}

/* ============================ POLITICAL & POLICY PAGE ============================ */

async function loadPolicyPage() {
  const el = document.getElementById("policyNews");
  const data = await Api.getNewsByCategory("policy");

  if (data.error) {
    el.innerHTML = errorBlock(data.error, loadPolicyPage);
    return;
  }

  el.classList.remove("skeleton-block");
  el.innerHTML = renderNewsList(data.news, { limit: 10 });
}

/* ============================ SHARED: NEWS LIST RENDERER ============================ */

const IMPACT_EMOJI = { positive: "🟢", negative: "🔴", neutral: "🟡" };

function renderNewsList(news, opts = {}) {
  if (!news || !news.length) {
    return `<p class="card-note">No recent news found.</p>`;
  }
  const items = opts.limit ? news.slice(0, opts.limit) : news;

  return `
    <div class="news-list">
      ${items.map((item) => `
        <div class="news-list-item">
          ${opts.showImpact ? `<span class="impact-tag">${IMPACT_EMOJI[item.impact] || ""}</span>` : ""}
          <div class="news-body">
            <div class="news-headline">${item.title}</div>
            ${opts.showImpact && item.impact_reason ? `<div class="news-impact-reason">${item.impact_reason}</div>` : ""}
            ${item.article ? `<p class="news-article">${item.article}</p>` : ""}
            <div class="news-meta">
              Inspired by reporting from ${item.source} · ${timeAgo(item.published)}
              ${item.link ? `· <a href="${item.link}" target="_blank" rel="noopener">original source</a>` : ""}
            </div>
          </div>
        </div>`).join("")}
    </div>`;
}

/* ============================ PERSONAL IMPACT CALCULATOR ============================ */

function setupCalculator() {
  const incomeInput = document.getElementById("incomeInput");
  const loanInput = document.getElementById("loanInput");
  const tenureInput = document.getElementById("tenureInput");
  const rateChangeInput = document.getElementById("rateChangeInput");

  [incomeInput].forEach((i) => i.addEventListener("input", updateInflationCalc));
  [loanInput, tenureInput, rateChangeInput].forEach((i) => i.addEventListener("input", updateEmiCalc));

  updateInflationCalc();
  updateEmiCalc();
  updatePetrolCalc();
}

async function updateInflationCalc() {
  const el = document.getElementById("inflationCalcResult");
  const spend = parseFloat(document.getElementById("incomeInput").value) || 0;

  const data = window._inflationData || (await Api.getInflation());
  if (data.error) {
    el.innerHTML = errorBlock(data.error, updateInflationCalc);
    return;
  }
  window._inflationData = data;

  const rate = data.cpi.latest_pct / 100;
  const extraPerMonth = spend * rate;
  const extraPerYear = extraPerMonth * 12;

  el.innerHTML = `
    At the current CPI inflation of <strong>${formatPct(data.cpi.latest_pct)}</strong>, your monthly
    expenses of ${formatRupee(spend, 0)} could effectively cost about
    <strong>${formatRupee(extraPerMonth, 0)} more per month</strong> a year from now —
    roughly <strong>${formatRupee(extraPerYear, 0)} more per year</strong> for the same basket of goods,
    if your income doesn't rise to match.`;
}

async function updateEmiCalc() {
  const el = document.getElementById("emiCalcResult");
  const principal = parseFloat(document.getElementById("loanInput").value) || 0;
  const years = parseFloat(document.getElementById("tenureInput").value) || 0;
  const rateChange = parseFloat(document.getElementById("rateChangeInput").value) || 0;

  const data = window._rbiData || (await Api.getRbi());
  if (data.error) {
    el.innerHTML = errorBlock(data.error, updateEmiCalc);
    return;
  }
  window._rbiData = data;

  // Assume a typical home-loan spread over the repo rate
  const baseRate = data.repo_rate + 2.5; // illustrative lending rate
  const newRate = baseRate + rateChange;

  const emi = calcEmi(principal, baseRate, years);
  const newEmi = calcEmi(principal, newRate, years);
  const diff = newEmi - emi;

  el.innerHTML = `
    At an illustrative lending rate of <strong>${formatPct(baseRate)}</strong>
    (repo rate + 2.5% spread), your EMI on a ${formatRupee(principal, 0)} loan
    over ${years} years would be about <strong>${formatRupee(emi, 0)}/month</strong>.<br><br>
    If the rate changes by <strong>${formatPct(rateChange)}</strong> to
    <strong>${formatPct(newRate)}</strong>, your new EMI would be about
    <strong>${formatRupee(newEmi, 0)}/month</strong> —
    a difference of <strong>${diff >= 0 ? "+" : ""}${formatRupee(diff, 0)}/month</strong>.`;
}

function calcEmi(principal, annualRatePct, years) {
  if (!principal || !years) return 0;
  const r = annualRatePct / 12 / 100;
  const n = years * 12;
  if (r === 0) return principal / n;
  return (principal * r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1);
}

async function updatePetrolCalc() {
  const el = document.getElementById("petrolCalcResult");
  const [rates, commodities] = await Promise.all([Api.getExchangeRates(), Api.getCommodities()]);

  if (rates.error || commodities.error) {
    el.innerHTML = errorBlock(rates.error || commodities.error, updatePetrolCalc);
    return;
  }

  const usdInr = rates.USD_INR;
  const crudeUsdPerBarrel = commodities["Crude Oil (Brent)"]?.price;

  if (!usdInr || !crudeUsdPerBarrel) {
    el.innerHTML = `<p class="card-note">Live data unavailable right now.</p>`;
    return;
  }

  // 1 barrel = 159 litres. Very rough illustration of the crude cost component only —
  // actual pump price also includes excise duty, VAT, dealer commission & refining cost.
  const crudeCostPerLitreInr = (crudeUsdPerBarrel / 159) * usdInr;

  el.innerHTML = `
    Right now, <strong>1 USD = ${formatRupee(usdInr)}</strong> and Brent crude trades at
    <strong>$${formatIndian(crudeUsdPerBarrel)}/barrel</strong>.<br><br>
    That works out to a raw crude cost of roughly
    <strong>${formatRupee(crudeCostPerLitreInr)} per litre</strong> before refining,
    transport, excise duty, VAT and dealer margin are added — which together typically
    make up over half of the price you pay at the pump.<br><br>
    A weaker rupee (higher USD/INR) or rising crude prices both push this raw cost up,
    increasing pressure on retail petrol &amp; diesel prices.`;
}
