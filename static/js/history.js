/* ============================================================
   FinanceIQ — history.js
   Shared "tap for performance chart" modal for ticker bar items
   and commodities, with a 1Y / 2Y / 3Y / 4Y period toggle.
   ============================================================ */

const HISTORY_CHART_CANVAS_ID = "historyChartCanvas";

/** Open a modal with a price-history line chart and period toggle.
 *  extraHtml (optional) is injected below the chart — used by the
 *  commodities page to also show the news section in the same modal. */
async function openHistoryChartModal(label, opts = {}) {
  const { extraHtml = "", subtitle = "" } = opts;

  openModal(`
    <div class="modal-title">${label}</div>
    ${subtitle ? `<div class="modal-subtitle">${subtitle}</div>` : ""}
    <div class="history-period-toggle" id="historyPeriodToggle">
      ${["1d", "1y", "2y", "3y", "4y"].map((p) => `<button class="period-btn ${p === "1d" ? "active" : ""}" data-period="${p}">${p === "1d" ? "1D" : p.toUpperCase()}</button>`).join("")}
    </div>
    <div class="history-chart-wrap">
      <canvas id="${HISTORY_CHART_CANVAS_ID}"></canvas>
    </div>
    <div id="historyChartNote" class="card-note"></div>
    ${extraHtml}
  `);

  document.querySelectorAll("#historyPeriodToggle .period-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#historyPeriodToggle .period-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      loadHistoryChart(label, btn.dataset.period);
    });
  });

  loadHistoryChart(label, "1d");
}

async function loadHistoryChart(label, period) {
  const noteEl = document.getElementById("historyChartNote");
  const canvas = document.getElementById(HISTORY_CHART_CANVAS_ID);
  if (!canvas) return; // modal closed before response arrived

  if (noteEl) noteEl.textContent = "Loading…";

  const data = await Api.getPriceHistory(label, period);
  if (!document.getElementById(HISTORY_CHART_CANVAS_ID)) return; // modal closed

  if (data.error || !data.prices || data.prices.length === 0) {
    if (noteEl) noteEl.textContent = data.error || "No historical data available.";
    destroyChart(HISTORY_CHART_CANVAS_ID);
    return;
  }

  const first = data.prices[0];
  const last = data.prices[data.prices.length - 1];
  const changePct = first ? ((last - first) / first) * 100 : null;
  const color = (changePct ?? 0) >= 0 ? CHART_COLORS.positive : CHART_COLORS.negative;

  // Thin out labels so the x-axis isn't crowded
  const step = Math.max(1, Math.floor(data.dates.length / 8));
  const labels = data.dates.map((d, i) => (i % step === 0 ? d : ""));

  const trend = linearTrendLine(data.prices);

  buildLineChart(HISTORY_CHART_CANVAS_ID, labels, [
    { label: label, data: data.prices, color, fill: true },
    { label: "Trend", data: trend, color: CHART_COLORS.muted, fill: false, dashed: true, tension: 0, pointRadius: 0 },
  ]);

  const unitSuffix = data.unit && data.unit !== "USD" ? ` $${data.unit}` : "";

  if (noteEl) {
    const trendDirection = trend[trend.length - 1] >= trend[0] ? "upward ▲" : "downward ▼";
    const periodLabel = data.period === "1d" ? "Today's" : data.period.toUpperCase();
    const rangeLabel = data.period === "1d"
      ? `${data.dates[0]} – ${data.dates[data.dates.length - 1]} (IST)`
      : `${data.dates[0]} → ${data.dates[data.dates.length - 1]}`;
    noteEl.innerHTML = `
      ${periodLabel} change:
      <span class="${pctClass(changePct)}">${arrow(changePct)} ${formatPct(changePct)}</span>
      ${unitSuffix ? `&nbsp;·&nbsp; Unit:${unitSuffix}` : ""}
      &nbsp;·&nbsp; Trend: ${trendDirection}
      &nbsp;·&nbsp; ${rangeLabel}
    `;
  }
}

/** Simple least-squares linear regression — returns a straight line
 *  of the same length as `values`, used as a visual trend overlay. */
function linearTrendLine(values) {
  const n = values.length;
  if (n < 2) return values.slice();

  const xMean = (n - 1) / 2;
  const yMean = values.reduce((sum, v) => sum + v, 0) / n;

  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i++) {
    num += (i - xMean) * (values[i] - yMean);
    den += (i - xMean) * (i - xMean);
  }
  const slope = den !== 0 ? num / den : 0;
  const intercept = yMean - slope * xMean;

  return values.map((_, i) => Math.round((slope * i + intercept) * 100) / 100);
}
