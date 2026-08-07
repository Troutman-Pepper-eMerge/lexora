/* Analytics view: pattern charts. */
(function () {
  let charts = { adj: null, juris: null };
  let _last = null;

  const baseOpts = () => {
    const c = LEXORA.chartColors();
    return {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: "rgba(20,22,40,0.92)", borderColor: c.grid, borderWidth: 1, titleColor: c.text, bodyColor: c.text },
      },
      scales: {
        x: { ticks: { color: c.muted }, grid: { color: c.grid } },
        y: { ticks: { color: c.muted }, grid: { color: c.grid } },
      },
    };
  };

  function drawAdj(rows) {
    if (charts.adj) charts.adj.destroy();
    const ctx = document.getElementById("chartAdj");
    const labels = rows.map(r => r.jurisdiction);
    const data = rows.map(r => r.avg_days);
    const c = LEXORA.chartColors();
    // Color the leader red, others gradient
    const bg = data.map((v, i) => i === 0 ? c.a7 : (i % 2 ? c.a1 : c.a2));
    charts.adj = new Chart(ctx, {
      type: "bar",
      data: { labels, datasets: [{ label: "Avg days", data,
        backgroundColor: bg, borderRadius: 8 }] },
      options: { ...baseOpts(), indexAxis: "y" },
    });
  }

  async function drawJuris(rows) {
    if (charts.juris) charts.juris.destroy();
    const ctx = document.getElementById("chartJuris");
    const labels = rows.map(r => r.jurisdiction);
    const data = rows.map(r => r.n);
    const c = LEXORA.chartColors();
    charts.juris = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: LEXORA.palette(),
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "58%",
        layout: { padding: 6 },
        plugins: {
          legend: {
            display: true,
            position: "right",
            labels: {
              color: c.text,
              boxWidth: 10,
              boxHeight: 10,
              padding: 8,
              font: { size: 11 },
            },
          },
          tooltip: {
            backgroundColor: "rgba(20,22,40,0.92)",
            borderColor: c.grid,
            borderWidth: 1,
            titleColor: c.text,
            bodyColor: c.text,
            callbacks: {
              label: (ctx) => `${ctx.label}: ${ctx.parsed} matters`,
            },
          },
        },
      },
    });
  }

  function renderTable(rows) {
    const tbody = document.querySelector("#adjTable tbody");
    tbody.innerHTML = rows.map(r => {
      const cls = r.delta_vs_national_pct > 15 ? "high"
                : r.delta_vs_national_pct < -10 ? "low" : "medium";
      const sign = r.delta_vs_national_pct >= 0 ? "+" : "";
      return `<tr>
        <td>${r.jurisdiction}</td>
        <td>${r.n}</td>
        <td>${r.avg_days}</td>
        <td><span class="pill ${cls}">${sign}${r.delta_vs_national_pct}%</span></td>
      </tr>`;
    }).join("");
  }

  async function load() {
    try {
      const r = await LEXORA.api("/api/analytics/patterns");
      _last = r;
      drawAdj(r.adjudication_time_by_state);
      drawJuris(r.adjudication_time_by_state);
      renderTable(r.adjudication_time_by_state);
    } catch (e) { LEXORA.toast("Analytics load failed: " + e.message); }
  }

  window.addEventListener("lexora:view", (e) => {
    if (e.detail.view === "analytics") load();
  });
  window.addEventListener("lexora:rerender", () => {
    if (_last) {
      drawAdj(_last.adjudication_time_by_state);
      drawJuris(_last.adjudication_time_by_state);
    }
  });
})();
