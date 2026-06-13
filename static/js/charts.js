/* ============================================================
   FinanceIQ — charts.js
   Reusable Chart.js builders for the macro/inflation pages.
   ============================================================ */

const CHART_COLORS = {
  primary: "#2563EB",
  positive: "#10B981",
  negative: "#EF4444",
  accent: "#F59E0B",
  muted: "#8B949E",
  grid: "rgba(139, 148, 166, 0.12)",
};

const chartRegistry = {};

function destroyChart(id) {
  if (chartRegistry[id]) {
    chartRegistry[id].destroy();
    delete chartRegistry[id];
  }
}

function getTextColor() {
  return getComputedStyle(document.body).getPropertyValue("--text-primary").trim() || "#F0F6FC";
}

/** Line chart with one or more series. */
function buildLineChart(canvasId, labels, series) {
  destroyChart(canvasId);
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  chartRegistry[canvasId] = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: series.map((s) => ({
        label: s.label,
        data: s.data,
        borderColor: s.color,
        backgroundColor: s.color + "22",
        tension: 0.35,
        fill: s.fill !== false,
        pointRadius: 2,
        borderWidth: 2,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      aspectRatio: 2,
      plugins: {
        legend: { labels: { color: getTextColor() } },
      },
      scales: {
        x: { ticks: { color: CHART_COLORS.muted }, grid: { color: CHART_COLORS.grid } },
        y: { ticks: { color: CHART_COLORS.muted }, grid: { color: CHART_COLORS.grid } },
      },
    },
  });
}

/** Bar chart, optionally colored per-bar based on sign. */
function buildBarChart(canvasId, labels, data, opts = {}) {
  destroyChart(canvasId);
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  const colors = opts.signedColors
    ? data.map((v) => (v >= 0 ? CHART_COLORS.positive : CHART_COLORS.negative))
    : (opts.color || CHART_COLORS.primary);

  chartRegistry[canvasId] = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{ label: opts.label || "", data, backgroundColor: colors, borderRadius: 4 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      aspectRatio: 2,
      plugins: { legend: { display: !!opts.label, labels: { color: getTextColor() } } },
      scales: {
        x: { ticks: { color: CHART_COLORS.muted }, grid: { display: false } },
        y: { ticks: { color: CHART_COLORS.muted }, grid: { color: CHART_COLORS.grid } },
      },
    },
  });
}

/** Tiny sparkline (no axes), used in commodity cards. */
function buildSparkline(canvasId, data, color) {
  destroyChart(canvasId);
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  chartRegistry[canvasId] = new Chart(ctx, {
    type: "line",
    data: {
      labels: data.map((_, i) => i),
      datasets: [{
        data,
        borderColor: color,
        backgroundColor: color + "22",
        tension: 0.35,
        fill: true,
        pointRadius: 0,
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      aspectRatio: 4,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { display: false }, y: { display: false } },
    },
  });
}
