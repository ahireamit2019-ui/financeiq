/* ============================================================
   FinanceIQ — stock.js
   Smart stock search + the full company report card (Feature 1)
   ============================================================ */

/** Company list for the search autocomplete dropdown.
 *  Mirrors the COMPANY_MAP in app.py so suggestions match what
 *  the backend can actually resolve. */
const STOCK_SUGGESTIONS = [
  { name: "Reliance Industries", symbol: "RELIANCE" },
  { name: "Tata Consultancy Services", symbol: "TCS" },
  { name: "Infosys", symbol: "INFY" },
  { name: "HDFC Bank", symbol: "HDFCBANK" },
  { name: "ICICI Bank", symbol: "ICICIBANK" },
  { name: "State Bank of India", symbol: "SBIN" },
  { name: "Axis Bank", symbol: "AXISBANK" },
  { name: "Kotak Mahindra Bank", symbol: "KOTAKBANK" },
  { name: "Bharti Airtel", symbol: "BHARTIARTL" },
  { name: "ITC", symbol: "ITC" },
  { name: "Larsen & Toubro", symbol: "LT" },
  { name: "Wipro", symbol: "WIPRO" },
  { name: "HCL Technologies", symbol: "HCLTECH" },
  { name: "Asian Paints", symbol: "ASIANPAINT" },
  { name: "Maruti Suzuki", symbol: "MARUTI" },
  { name: "Bajaj Finance", symbol: "BAJFINANCE" },
  { name: "Bajaj Finserv", symbol: "BAJAJFINSV" },
  { name: "Titan Company", symbol: "TITAN" },
  { name: "Sun Pharmaceutical", symbol: "SUNPHARMA" },
  { name: "UltraTech Cement", symbol: "ULTRACEMCO" },
  { name: "NTPC", symbol: "NTPC" },
  { name: "ONGC", symbol: "ONGC" },
  { name: "Tata Motors", symbol: "TATAMOTORS" },
  { name: "Tata Steel", symbol: "TATASTEEL" },
  { name: "Adani Enterprises", symbol: "ADANIENT" },
  { name: "Adani Ports", symbol: "ADANIPORTS" },
  { name: "Power Grid Corporation", symbol: "POWERGRID" },
  { name: "Coal India", symbol: "COALINDIA" },
  { name: "Nestle India", symbol: "NESTLEIND" },
  { name: "Hindustan Unilever", symbol: "HINDUNILVR" },
  { name: "Mahindra & Mahindra", symbol: "M&M" },
  { name: "NMDC", symbol: "NMDC" },
  { name: "Zomato (Eternal)", symbol: "ETERNAL" },
  { name: "Paytm", symbol: "PAYTM" },
  { name: "JSW Steel", symbol: "JSWSTEEL" },
  { name: "Grasim Industries", symbol: "GRASIM" },
  { name: "Dr. Reddy's Laboratories", symbol: "DRREDDY" },
  { name: "Cipla", symbol: "CIPLA" },
  { name: "IndusInd Bank", symbol: "INDUSINDBK" },
  { name: "Tech Mahindra", symbol: "TECHM" },
  { name: "Britannia Industries", symbol: "BRITANNIA" },
  { name: "Divi's Laboratories", symbol: "DIVISLAB" },
  { name: "Eicher Motors", symbol: "EICHERMOT" },
  { name: "Shriram Finance", symbol: "SHRIRAMFIN" },
  { name: "Trent", symbol: "TRENT" },
  { name: "Hero MotoCorp", symbol: "HEROMOTOCO" },
  { name: "Bajaj Auto", symbol: "BAJAJ-AUTO" },
  // --- Banks & NBFCs ---
  { name: "Canara Bank", symbol: "CANBK" },
  { name: "Bank of Baroda", symbol: "BANKBARODA" },
  { name: "Punjab National Bank", symbol: "PNB" },
  { name: "Bank of India", symbol: "BANKINDIA" },
  { name: "Union Bank of India", symbol: "UNIONBANK" },
  { name: "Indian Bank", symbol: "INDIANB" },
  { name: "Muthoot Finance", symbol: "MUTHOOTFIN" },
  { name: "Federal Bank", symbol: "FEDERALBNK" },
  { name: "IDFC First Bank", symbol: "IDFCFIRSTB" },
  { name: "Yes Bank", symbol: "YESBANK" },
  { name: "AU Small Finance Bank", symbol: "AUBANK" },
  { name: "Bandhan Bank", symbol: "BANDHANBNK" },
  { name: "Cholamandalam Investment & Finance", symbol: "CHOLAFIN" },
  { name: "L&T Finance", symbol: "LTF" },
  { name: "Power Finance Corporation", symbol: "PFC" },
  { name: "REC Limited", symbol: "RECLTD" },
  { name: "LIC Housing Finance", symbol: "LICHSGFIN" },
  { name: "SBI Cards & Payment Services", symbol: "SBICARD" },
  { name: "HDFC Life Insurance", symbol: "HDFCLIFE" },
  { name: "SBI Life Insurance", symbol: "SBILIFE" },
  { name: "ICICI Prudential Life Insurance", symbol: "ICICIPRULI" },
  { name: "ICICI Lombard General Insurance", symbol: "ICICIGI" },
  { name: "Bajaj Holdings & Investment", symbol: "BAJAJHLDNG" },
  { name: "Life Insurance Corporation of India (LIC)", symbol: "LICI" },
  // --- Oil, gas & energy ---
  { name: "Indian Oil Corporation", symbol: "IOC" },
  { name: "Bharat Petroleum (BPCL)", symbol: "BPCL" },
  { name: "Hindustan Petroleum (HPCL)", symbol: "HINDPETRO" },
  { name: "GAIL India", symbol: "GAIL" },
  { name: "Vedanta", symbol: "VEDL" },
  { name: "Hindalco Industries", symbol: "HINDALCO" },
  // --- Telecom ---
  { name: "Vodafone Idea", symbol: "IDEA" },
  // --- Pharma & healthcare ---
  { name: "Lupin", symbol: "LUPIN" },
  { name: "Aurobindo Pharma", symbol: "AUROPHARMA" },
  { name: "Apollo Hospitals", symbol: "APOLLOHOSP" },
  { name: "Zydus Lifesciences", symbol: "ZYDUSLIFE" },
  // --- Consumer / FMCG ---
  { name: "Dabur India", symbol: "DABUR" },
  { name: "Godrej Consumer Products", symbol: "GODREJCP" },
  { name: "Marico", symbol: "MARICO" },
  { name: "Colgate-Palmolive India", symbol: "COLPAL" },
  { name: "Pidilite Industries", symbol: "PIDILITIND" },
  { name: "Varun Beverages", symbol: "VBL" },
  { name: "United Spirits", symbol: "MCDOWELL-N" },
  // --- Capital goods / industrials ---
  { name: "Siemens India", symbol: "SIEMENS" },
  { name: "ABB India", symbol: "ABB" },
  { name: "Havells India", symbol: "HAVELLS" },
  { name: "Voltas", symbol: "VOLTAS" },
  { name: "Bharat Electronics (BEL)", symbol: "BEL" },
  { name: "Bharat Forge", symbol: "BHARATFORG" },
  { name: "Cummins India", symbol: "CUMMINSIND" },
  { name: "CG Power & Industrial Solutions", symbol: "CGPOWER" },
  // --- Real estate ---
  { name: "DLF", symbol: "DLF" },
  { name: "Godrej Properties", symbol: "GODREJPROP" },
  { name: "Oberoi Realty", symbol: "OBEROIRLTY" },
  // --- Adani group & cement ---
  { name: "Adani Green Energy", symbol: "ADANIGREEN" },
  { name: "Adani Power", symbol: "ADANIPOWER" },
  { name: "Adani Total Gas", symbol: "ATGL" },
  { name: "Adani Energy Solutions", symbol: "ADANIENSOL" },
  { name: "Ambuja Cements", symbol: "AMBUJACEM" },
  { name: "ACC Limited", symbol: "ACC" },
  // --- Autos ---
  { name: "TVS Motor Company", symbol: "TVSMOTOR" },
  { name: "Ashok Leyland", symbol: "ASHOKLEY" },
  { name: "Samvardhana Motherson International", symbol: "MOTHERSON" },
  // --- IT ---
  { name: "Persistent Systems", symbol: "PERSISTENT" },
  { name: "LTIMindtree", symbol: "LTIM" },
  { name: "Mphasis", symbol: "MPHASIS" },
  { name: "Coforge", symbol: "COFORGE" },
  // --- Other large caps ---
  { name: "Info Edge (Naukri)", symbol: "NAUKRI" },
  { name: "Indian Railway Finance Corporation (IRFC)", symbol: "IRFC" },
  { name: "IRCTC", symbol: "IRCTC" },
  { name: "PB Fintech (Policybazaar)", symbol: "POLICYBZR" },
  { name: "Indian Hotels Company (Taj)", symbol: "INDHOTEL" },
  { name: "InterGlobe Aviation (IndiGo)", symbol: "INDIGO" },
  // --- Rest of Nifty 100 / popular F&O & midcaps ---
  { name: "Avenue Supermarts (DMart)", symbol: "DMART" },
  { name: "Bharat Heavy Electricals (BHEL)", symbol: "BHEL" },
  { name: "Bosch Limited", symbol: "BOSCHLTD" },
  { name: "HDFC Asset Management", symbol: "HDFCAMC" },
  { name: "Indus Towers", symbol: "INDUSTOWER" },
  { name: "Jindal Steel & Power", symbol: "JINDALSTEL" },
  { name: "Max Healthcare Institute", symbol: "MAXHEALTH" },
  { name: "NHPC", symbol: "NHPC" },
  { name: "Oil India", symbol: "OIL" },
  { name: "Page Industries", symbol: "PAGEIND" },
  { name: "Polycab India", symbol: "POLYCAB" },
  { name: "Shree Cement", symbol: "SHREECEM" },
  { name: "SRF Limited", symbol: "SRF" },
  { name: "Suzlon Energy", symbol: "SUZLON" },
  { name: "Torrent Pharmaceuticals", symbol: "TORNTPHARM" },
  { name: "Zee Entertainment Enterprises", symbol: "ZEEL" },
  { name: "Tata Power", symbol: "TATAPOWER" },
  { name: "Tata Communications", symbol: "TATACOMM" },
  { name: "Tata Elxsi", symbol: "TATAELXSI" },
  { name: "Tata Chemicals", symbol: "TATACHEM" },
  { name: "GMR Airports", symbol: "GMRAIRPORT" },
  { name: "Jubilant FoodWorks", symbol: "JUBLFOOD" },
  { name: "PVR Inox", symbol: "PVRINOX" },
  { name: "Aditya Birla Capital", symbol: "ABCAPITAL" },
  { name: "Aditya Birla Fashion & Retail", symbol: "ABFRL" },
  { name: "Piramal Enterprises", symbol: "PEL" },
  { name: "Indraprastha Gas", symbol: "IGL" },
  { name: "Mahanagar Gas", symbol: "MGL" },
  { name: "Petronet LNG", symbol: "PETRONET" },
  { name: "Container Corporation of India", symbol: "CONCOR" },
  { name: "National Aluminium Company (NALCO)", symbol: "NATIONALUM" },
  { name: "Steel Authority of India (SAIL)", symbol: "SAIL" },
  { name: "MRF", symbol: "MRF" },
  { name: "Apollo Tyres", symbol: "APOLLOTYRE" },
  { name: "Balkrishna Industries", symbol: "BALKRISIND" },
  { name: "Escorts Kubota", symbol: "ESCORTS" },
  { name: "Bata India", symbol: "BATAINDIA" },
  { name: "Berger Paints India", symbol: "BERGEPAINT" },
  { name: "Kansai Nerolac Paints", symbol: "KANSAINER" },
  { name: "United Breweries", symbol: "UBL" },
  { name: "ITC Hotels", symbol: "ITCHOTELS" },
  { name: "Macrotech Developers (Lodha)", symbol: "LODHA" },
  { name: "Phoenix Mills", symbol: "PHOENIXLTD" },
  { name: "Prestige Estates Projects", symbol: "PRESTIGE" },
  { name: "Sun TV Network", symbol: "SUNTV" },
  { name: "Biocon", symbol: "BIOCON" },
  { name: "Alkem Laboratories", symbol: "ALKEM" },
  { name: "Mankind Pharma", symbol: "MANKIND" },
  { name: "Laurus Labs", symbol: "LAURUSLABS" },
  { name: "Gland Pharma", symbol: "GLAND" },
  { name: "Syngene International", symbol: "SYNGENE" },
  { name: "Abbott India", symbol: "ABBOTINDIA" },
  { name: "Glenmark Pharmaceuticals", symbol: "GLENMARK" },
  { name: "Torrent Power", symbol: "TORNTPOWER" },
  { name: "JSW Energy", symbol: "JSWENERGY" },
  { name: "NTPC Green Energy", symbol: "NTPCGREEN" },
  { name: "Tata Investment Corporation", symbol: "TATAINVEST" },
  { name: "Multi Commodity Exchange (MCX)", symbol: "MCX" },
  { name: "BSE Limited", symbol: "BSE" },
  { name: "Central Depository Services (CDSL)", symbol: "CDSL" },
  { name: "Angel One", symbol: "ANGELONE" },
  { name: "360 ONE WAM", symbol: "360ONE" },
  { name: "KPIT Technologies", symbol: "KPITTECH" },
  { name: "Tata Technologies", symbol: "TATATECH" },
  { name: "Honasa Consumer (Mamaearth)", symbol: "HONASA" },
  { name: "Nykaa (FSN E-Commerce)", symbol: "NYKAA" },
  { name: "Delhivery", symbol: "DELHIVERY" },
  { name: "CarTrade Tech", symbol: "CARTRADE" },
  { name: "Go Digit General Insurance", symbol: "GODIGIT" },
];

const STOCK_SKELETON = `
  <div class="card report-card">
    <div class="skeleton-row" style="width:60%"></div>
    <div class="skeleton-row" style="width:40%"></div>
    <div class="skeleton-block" style="min-height:120px"></div>
    <div class="skeleton-block" style="min-height:160px"></div>
    <div class="skeleton-block" style="min-height:140px"></div>
  </div>`;

function scoreFillClass(score) {
  if (score >= 7) return "score-fill-good";
  if (score >= 4) return "score-fill-mid";
  return "score-fill-bad";
}

function buildScoreRow(label, score) {
  const safe = Math.max(0, Math.min(10, Number(score) || 0));
  return `
    <div class="score-row">
      <div class="score-label">${label}</div>
      <div class="score-bar-track">
        <div class="score-bar-fill ${scoreFillClass(safe)}" data-target="${(safe / 10) * 100}"></div>
      </div>
      <div class="score-value">${safe.toFixed(1)}/10</div>
    </div>`;
}

function animateScoreBars(container) {
  const bars = container.querySelectorAll(".score-bar-fill");
  requestAnimationFrame(() => {
    bars.forEach((bar) => {
      const target = bar.getAttribute("data-target");
      requestAnimationFrame(() => { bar.style.width = `${target}%`; });
    });
  });
}

function timeAgo(dateStr) {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return dateStr;
  const diffMs = Date.now() - date.getTime();
  const diffH = Math.floor(diffMs / 3600000);
  if (diffH < 1) return "just now";
  if (diffH < 24) return `${diffH}h ago`;
  const diffD = Math.floor(diffH / 24);
  return `${diffD}d ago`;
}

/** Main entry point — called when the user searches for a stock. */
async function searchStock(rawQuery) {
  const query = (rawQuery || "").trim();
  if (!query) return;

  goToPage("stock");
  const container = document.getElementById("stockResult");
  container.innerHTML = STOCK_SKELETON;

  const data = await Api.getStock(query);

  if (data.error) {
    container.innerHTML = `<div class="card">${errorBlock(data.error, () => searchStock(query))}</div>`;
    return;
  }

  renderReportCard(container, data);

  // Fetch news, scorecard in parallel — render as they arrive
  loadStockNews(data.symbol);
  loadStockScorecard(data.symbol);
}

function renderReportCard(container, data) {
  const changeClass = pctClass(data.change_pct);
  const marketCap = data.market_cap_cr ? formatCrore(data.market_cap_cr) : "—";

  container.innerHTML = `
    <div class="card report-card">
      <div class="company-header">
        <img class="company-logo" src="${data.logo_url}" alt="${data.name} logo"
             onerror="this.src='https://ui-avatars.com/api/?name=${encodeURIComponent(data.name)}&background=2563EB&color=fff'">
        <div class="company-meta">
          <h2 class="company-name">${data.name}</h2>
          <div class="company-sub">
            <span>NSE: <strong>${data.symbol}</strong></span>
            <span>${data.sector || "N/A"}</span>
            <span>Market Cap: ${marketCap}</span>
          </div>
        </div>
        <div class="price-block">
          <div class="price-now">${formatRupee(data.price)}</div>
          <div class="price-change ${changeClass}">
            ${arrow(data.change_pct)} ${formatRupee(Math.abs(data.change || 0))} (${formatPct(data.change_pct)}) today
          </div>
          <div class="price-52w">52W High: ${formatRupee(data.week52_high)} &nbsp;|&nbsp; 52W Low: ${formatRupee(data.week52_low)}</div>
        </div>
      </div>
    </div>

    <div class="card">
      <h3 class="card-title">Scorecard</h3>
      <div id="scorecardSection">
        <div class="skeleton-block" style="min-height:150px"></div>
      </div>
    </div>

    <div class="card">
      <h3 class="card-title">Key Metrics</h3>
      <div class="metrics-grid">
        <div class="metric-box"><div class="metric-label">P/E Ratio</div><div class="metric-value">${data.pe_ratio ? formatIndian(data.pe_ratio) : "—"}</div></div>
        <div class="metric-box"><div class="metric-label">EPS</div><div class="metric-value">${data.eps ? formatRupee(data.eps) : "—"}</div></div>
        <div class="metric-box"><div class="metric-label">Revenue</div><div class="metric-value">${data.revenue_cr ? formatCrore(data.revenue_cr) : "—"}</div></div>
        <div class="metric-box"><div class="metric-label">Net Profit</div><div class="metric-value">${data.net_profit_cr ? formatCrore(data.net_profit_cr) : "—"}</div></div>
        <div class="metric-box"><div class="metric-label">Debt/Equity</div><div class="metric-value">${data.debt_to_equity ? formatIndian(data.debt_to_equity) : "—"}</div></div>
        <div class="metric-box"><div class="metric-label">ROE</div><div class="metric-value">${data.roe ? formatPct(data.roe * 100) : "—"}</div></div>
        <div class="metric-box"><div class="metric-label">Promoter Holding</div><div class="metric-value">${data.promoter_holding ? formatPct(data.promoter_holding * 100) : "—"}</div></div>
        <div class="metric-box"><div class="metric-label">Dividend Yield</div><div class="metric-value">${data.dividend_yield ? formatPct(data.dividend_yield) : "—"}</div></div>
      </div>
    </div>

    <div class="card">
      <h3 class="card-title">Latest News</h3>
      <div id="stockNewsSection" class="news-grid">
        <div class="skeleton-block"></div>
        <div class="skeleton-block"></div>
        <div class="skeleton-block"></div>
      </div>
    </div>

    <div class="card">
      <h3 class="card-title">Company Meetings &amp; Updates</h3>
      <div id="updatesSection">
        <div class="skeleton-row"></div>
        <div class="skeleton-row"></div>
        <div class="skeleton-row"></div>
      </div>
    </div>

    <div class="card">
      <h3 class="card-title">AI Analysis</h3>
      <div id="aiAnalysisSection">
        <div class="skeleton-block" style="min-height:160px"></div>
      </div>
    </div>
  `;
}

async function loadStockNews(symbol) {
  const section = document.getElementById("stockNewsSection");
  if (!section) return;

  const data = await Api.getStockNews(symbol);
  if (data.error) {
    section.innerHTML = errorBlock(data.error, () => loadStockNews(symbol));
    return;
  }

  if (!data.news || data.news.length === 0) {
    section.innerHTML = `<p class="card-note">No recent news found.</p>`;
    return;
  }

  section.innerHTML = data.news.map((item) => `
    <div class="news-card">
      <div class="news-title">${item.title}</div>
      ${item.article ? `<p class="news-article">${item.article}</p>` : ""}
      <div class="news-meta">
        Inspired by reporting from ${item.source} · ${timeAgo(item.published)}
        ${item.link ? `<br><a href="${item.link}" target="_blank" rel="noopener">original source</a>` : ""}
      </div>
    </div>
  `).join("");
}

async function loadStockScorecard(symbol) {
  const scoreSection = document.getElementById("scorecardSection");
  const updatesSection = document.getElementById("updatesSection");
  const aiSection = document.getElementById("aiAnalysisSection");

  const data = await Api.getStockScorecard(symbol);

  if (data.error) {
    const msg = data.error;
    const retry = () => loadStockScorecard(symbol);
    if (scoreSection) scoreSection.innerHTML = errorBlock(msg, retry);
    if (updatesSection) updatesSection.innerHTML = "";
    if (aiSection) aiSection.innerHTML = errorBlock(msg, retry);
    return;
  }

  // Scorecard bars
  if (scoreSection && data.scores) {
    const s = data.scores;
    scoreSection.innerHTML = `
      <div class="scorecard-grid">
        ${buildScoreRow("Overall Score", s.overall)}
        ${buildScoreRow("Valuation", s.valuation)}
        ${buildScoreRow("Growth", s.growth)}
        ${buildScoreRow("Financials", s.financials)}
        ${buildScoreRow("Momentum", s.momentum)}
      </div>`;
    animateScoreBars(scoreSection);
  }

  // Company updates
  if (updatesSection) {
    if (data.meeting_updates && data.meeting_updates.length) {
      updatesSection.innerHTML = `
        <ul class="update-list">
          ${data.meeting_updates.map((u) => `<li>${u}</li>`).join("")}
        </ul>`;
    } else {
      updatesSection.innerHTML = `<p class="card-note">No recent updates available.</p>`;
    }
  }

  // AI positives / negatives / summary
  if (aiSection) {
    const positives = (data.positives || []).map((p) => `<li>${p}</li>`).join("");
    const negatives = (data.negatives || []).map((n) => `<li>${n}</li>`).join("");
    aiSection.innerHTML = `
      ${data.summary ? `<div class="ai-summary" style="margin-bottom:14px;">${data.summary}</div>` : ""}
      <div class="pros-cons-grid">
        <div>
          <h4 style="margin:0 0 8px;color:var(--positive);font-family:var(--font-data);">✅ Positives</h4>
          <ul class="pros-cons-list positives">${positives}</ul>
        </div>
        <div>
          <h4 style="margin:0 0 8px;color:var(--negative);font-family:var(--font-data);">❌ Negatives</h4>
          <ul class="pros-cons-list negatives">${negatives}</ul>
        </div>
      </div>`;
  }
}
