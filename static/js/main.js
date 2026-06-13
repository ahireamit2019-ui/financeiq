/* ============================================================
   FinanceIQ — main.js
   App bootstrap, page routing, sidebar/mobile nav, settings panel
   ============================================================ */

const PAGE_LOADERS = {
  dashboard: loadDashboard,
  market: loadMarketPage,
  macro: loadMacroPage,
  inflation: loadInflationPage,
  tax: loadTaxPage,
  earnings: loadEarningsPage,
  geo: loadGeoPage,
  commodities: loadCommoditiesPage,
  policy: loadPolicyPage,
  calculator: () => {}, // set up once on init
  stock: () => {}, // populated by search
};

const loadedPages = new Set();

function goToPage(pageId) {
  // sections
  document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
  const target = document.getElementById(`page-${pageId}`);
  if (target) target.classList.add("active");

  // sidebar nav state
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.page === pageId);
  });
  document.querySelectorAll(".bottom-nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.page === pageId);
  });

  // close mobile sidebar if open
  document.getElementById("sidebar").classList.remove("open");

  // lazy-load page data once
  if (!loadedPages.has(pageId) && PAGE_LOADERS[pageId]) {
    loadedPages.add(pageId);
    PAGE_LOADERS[pageId]();
  }

  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* ============================ NAVIGATION WIRING ============================ */

function setupNavigation() {
  document.querySelectorAll(".nav-item, .bottom-nav-item").forEach((item) => {
    item.addEventListener("click", () => goToPage(item.dataset.page));
  });

  document.getElementById("hamburgerBtn").addEventListener("click", () => {
    document.getElementById("sidebar").classList.toggle("open");
  });
}

/* ============================================================
   SEARCH WIRING
   ============================================================ */

function setupSearch() {
  const input = document.getElementById("stockSearchInput");
  const btn = document.getElementById("stockSearchBtn");
  const suggestionsBox = document.getElementById("searchSuggestions");
  const searchContainer = document.getElementById("topbarSearch");

  let highlightedIndex = -1;
  let currentMatches = [];
  let debounceTimer = null;
  let requestSeq = 0;

  const triggerSearch = (query) => {
    hideSuggestions();
    searchStock(query !== undefined ? query : input.value);
  };

  const hideSuggestions = () => {
    suggestionsBox.classList.remove("visible");
    suggestionsBox.innerHTML = "";
    highlightedIndex = -1;
    currentMatches = [];
  };

  const renderMatches = (matches) => {
    currentMatches = matches.slice(0, 10);
    if (currentMatches.length === 0) {
      suggestionsBox.innerHTML = `<div class="suggestion-empty">No matching companies — press Search to try this symbol directly.</div>`;
    } else {
      suggestionsBox.innerHTML = currentMatches.map((s, i) => `
        <div class="suggestion-item" data-index="${i}" data-name="${s.symbol}">
          <span>${s.name}</span>
          <span class="suggestion-symbol">${s.symbol}${s.exchange ? ` · ${s.exchange}` : ""}</span>
        </div>`).join("");
    }
    highlightedIndex = -1;
    suggestionsBox.classList.add("visible");
  };

  const localMatches = (q) => STOCK_SUGGESTIONS
    .filter((s) => s.name.toLowerCase().includes(q) || s.symbol.toLowerCase().includes(q))
    .map((s) => ({ symbol: s.symbol, name: s.name, exchange: "" }));

  const showSuggestions = (query) => {
    const q = query.trim().toLowerCase();
    if (!q) { hideSuggestions(); return; }

    // Show instant local matches immediately for responsiveness
    renderMatches(localMatches(q));

    // Then fetch live results across all NSE/BSE stocks (debounced)
    clearTimeout(debounceTimer);
    if (q.length < 2) return;

    debounceTimer = setTimeout(async () => {
      const mySeq = ++requestSeq;
      const data = await Api.searchStocks(q);
      if (mySeq !== requestSeq) return; // a newer request superseded this one
      if (input.value.trim().toLowerCase() !== q) return; // input changed since request started

      if (data.error || !data.results) {
        renderMatches(localMatches(q));
        return;
      }

      // Merge: live results first, then any local matches not already present
      const seen = new Set(data.results.map((r) => r.symbol));
      const merged = [...data.results, ...localMatches(q).filter((m) => !seen.has(m.symbol))];
      renderMatches(merged);
    }, 300);
  };

  const updateHighlight = () => {
    suggestionsBox.querySelectorAll(".suggestion-item").forEach((el, i) => {
      el.classList.toggle("highlighted", i === highlightedIndex);
    });
  };

  input.addEventListener("input", () => showSuggestions(input.value));

  input.addEventListener("focus", () => {
    if (input.value.trim()) showSuggestions(input.value);
  });

  input.addEventListener("keydown", (e) => {
    const items = suggestionsBox.querySelectorAll(".suggestion-item");
    if (e.key === "ArrowDown" && items.length) {
      e.preventDefault();
      highlightedIndex = Math.min(highlightedIndex + 1, items.length - 1);
      updateHighlight();
    } else if (e.key === "ArrowUp" && items.length) {
      e.preventDefault();
      highlightedIndex = Math.max(highlightedIndex - 1, 0);
      updateHighlight();
    } else if (e.key === "Enter") {
      if (highlightedIndex >= 0 && currentMatches[highlightedIndex]) {
        const choice = currentMatches[highlightedIndex];
        input.value = choice.symbol;
        triggerSearch(choice.symbol);
      } else {
        triggerSearch();
      }
    } else if (e.key === "Escape") {
      hideSuggestions();
    }
  });

  suggestionsBox.addEventListener("click", (e) => {
    const item = e.target.closest(".suggestion-item");
    if (!item) return;
    const symbol = item.dataset.name;
    input.value = symbol;
    triggerSearch(symbol);
  });

  btn.addEventListener("click", () => triggerSearch());

  // close dropdown when clicking outside the search box
  document.addEventListener("click", (e) => {
    if (!searchContainer.contains(e.target)) hideSuggestions();
  });
}

/* ============================ SETTINGS PANEL ============================ */

function setupSettings() {
  const panel = document.getElementById("settingsPanel");
  const overlay = document.getElementById("overlay");
  const openBtn = document.getElementById("settingsBtn");
  const closeBtn = document.getElementById("closeSettingsBtn");
  const saveBtn = document.getElementById("saveSettingsBtn");
  const statusEl = document.getElementById("settingsStatus");

  const anthropicInput = document.getElementById("anthropicKeyInput");
  const newsApiInput = document.getElementById("newsApiKeyInput");
  const watchlistInput = document.getElementById("watchlistInput");

  // load saved values
  anthropicInput.value = localStorage.getItem("financeiq_anthropic_key") || "";
  newsApiInput.value = localStorage.getItem("financeiq_newsapi_key") || "";
  watchlistInput.value = localStorage.getItem("financeiq_watchlist") || "";

  const savedTheme = localStorage.getItem("financeiq_theme") || "dark";
  applyTheme(savedTheme);
  document.querySelectorAll(".theme-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.theme === savedTheme);
    btn.addEventListener("click", () => {
      document.querySelectorAll(".theme-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      applyTheme(btn.dataset.theme);
    });
  });

  const open = () => { panel.classList.add("open"); overlay.classList.add("visible"); };
  const close = () => { panel.classList.remove("open"); overlay.classList.remove("visible"); };

  openBtn.addEventListener("click", open);
  closeBtn.addEventListener("click", close);
  overlay.addEventListener("click", close);

  saveBtn.addEventListener("click", () => {
    localStorage.setItem("financeiq_anthropic_key", anthropicInput.value.trim());
    localStorage.setItem("financeiq_newsapi_key", newsApiInput.value.trim());
    localStorage.setItem("financeiq_watchlist", watchlistInput.value.trim());

    const activeTheme = document.querySelector(".theme-btn.active")?.dataset.theme || "dark";
    localStorage.setItem("financeiq_theme", activeTheme);

    statusEl.textContent = "Settings saved.";
    setTimeout(() => { statusEl.textContent = ""; }, 2500);

    // Refresh the watchlist card immediately if the dashboard is visible
    if (document.getElementById("page-dashboard")?.classList.contains("active")) {
      loadWatchlist();
    }
  });
}

function applyTheme(theme) {
  if (theme === "auto") {
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.setAttribute("data-theme", prefersDark ? "dark" : "light");
  } else {
    document.documentElement.setAttribute("data-theme", theme);
  }
}

/* ============================ GENERIC MODAL ============================ */

function openModal(html) {
  const overlay = document.getElementById("modalOverlay");
  const content = document.getElementById("modalContent");
  content.innerHTML = html;
  overlay.classList.add("visible");
}

function closeModal() {
  const overlay = document.getElementById("modalOverlay");
  document.getElementById("modalContent").innerHTML = "";
  overlay.classList.remove("visible");
}

function setupModal() {
  const overlay = document.getElementById("modalOverlay");
  const box = document.getElementById("modalBox");
  document.getElementById("modalCloseBtn").addEventListener("click", closeModal);
  overlay.addEventListener("click", (e) => {
    if (!box.contains(e.target)) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });
}

/* ============================ CLICKABLE STOCK NAMES ============================ */

/** Event delegation: any element with class "stock-link" and a
 *  data-symbol attribute navigates to Stock Research for that symbol. */
function setupStockLinks() {
  document.addEventListener("click", (e) => {
    const link = e.target.closest(".stock-link");
    if (!link) return;
    const symbol = link.dataset.symbol;
    if (!symbol) return;
    e.preventDefault();
    searchStock(symbol);
  });
}

/* ============================ APP INIT ============================ */

document.addEventListener("DOMContentLoaded", () => {
  setupNavigation();
  setupSearch();
  setupSettings();
  setupCalculator();
  setupTaxCalculator();
  setupModal();
  setupStockLinks();

  loadTicker();
  setInterval(loadTicker, 60000);

  // dashboard is the default page
  loadedPages.add("dashboard");
  loadDashboard();
});
