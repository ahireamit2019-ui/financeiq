/* ============================================================
   FinanceIQ — currency.js
   Currency converter widget on the Dashboard (INR ⇄ USD/EUR/GBP)
   ============================================================ */

const CURRENCY_LABELS = {
  INR: "₹ Indian Rupee (INR)",
  USD: "$ US Dollar (USD)",
  EUR: "€ Euro (EUR)",
  GBP: "£ British Pound (GBP)",
};

const CURRENCY_SYMBOLS = { INR: "₹", USD: "$", EUR: "€", GBP: "£" };

let currencyRatesToInr = null; // { INR: 1, USD: x, EUR: y, GBP: z }

async function loadCurrencyConverter() {
  const el = document.getElementById("currencyConverter");
  if (!el) return;

  const data = await Api.getExchangeRates();
  if (data.error || !data.USD_INR) {
    el.classList.remove("skeleton-block");
    el.innerHTML = errorBlock(data.error || "Could not load exchange rates.", loadCurrencyConverter);
    return;
  }

  currencyRatesToInr = {
    INR: 1,
    USD: data.USD_INR,
    EUR: data.EUR_INR,
    GBP: data.GBP_INR,
  };

  el.classList.remove("skeleton-block");
  el.innerHTML = `
    <div class="currency-converter">
      <div class="currency-row">
        <input type="number" id="currencyAmount" class="currency-input" value="1" min="0" step="any">
        <select id="currencyFrom" class="currency-select">
          ${Object.entries(CURRENCY_LABELS).map(([code, label]) => `<option value="${code}" ${code === "USD" ? "selected" : ""}>${label}</option>`).join("")}
        </select>
      </div>
      <button id="currencySwapBtn" class="currency-swap-btn" aria-label="Swap currencies">⇅</button>
      <div class="currency-row">
        <div id="currencyResult" class="currency-result">—</div>
        <select id="currencyTo" class="currency-select">
          ${Object.entries(CURRENCY_LABELS).map(([code, label]) => `<option value="${code}" ${code === "INR" ? "selected" : ""}>${label}</option>`).join("")}
        </select>
      </div>
      <p class="card-note" id="currencyRateNote"></p>
    </div>
  `;

  const amountEl = document.getElementById("currencyAmount");
  const fromEl = document.getElementById("currencyFrom");
  const toEl = document.getElementById("currencyTo");
  const swapBtn = document.getElementById("currencySwapBtn");

  const recalc = () => updateCurrencyResult(amountEl, fromEl, toEl);

  amountEl.addEventListener("input", recalc);
  fromEl.addEventListener("change", recalc);
  toEl.addEventListener("change", recalc);
  swapBtn.addEventListener("click", () => {
    const tmp = fromEl.value;
    fromEl.value = toEl.value;
    toEl.value = tmp;
    recalc();
  });

  recalc();
}

function updateCurrencyResult(amountEl, fromEl, toEl) {
  const resultEl = document.getElementById("currencyResult");
  const noteEl = document.getElementById("currencyRateNote");
  if (!currencyRatesToInr) return;

  const amount = parseFloat(amountEl.value);
  const from = fromEl.value;
  const to = toEl.value;

  if (isNaN(amount)) {
    resultEl.textContent = "—";
    return;
  }

  const amountInInr = amount * currencyRatesToInr[from];
  const result = amountInInr / currencyRatesToInr[to];

  const decimals = to === "INR" ? 2 : 4;
  resultEl.textContent = `${CURRENCY_SYMBOLS[to]} ${formatIndian(result, decimals)}`;

  // 1 unit of "from" expressed in "to", for context
  const oneInTo = currencyRatesToInr[from] / currencyRatesToInr[to];
  noteEl.textContent = `1 ${from} = ${CURRENCY_SYMBOLS[to]}${formatIndian(oneInTo, 4)} ${to} · rates update hourly`;
}
