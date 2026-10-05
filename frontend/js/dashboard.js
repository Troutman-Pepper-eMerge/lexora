/* Dashboard view: KPIs + charts + patterns. */
(function () {
  let charts = { status: null, practice: null, filings: null, value: null };
  let _lastData = null;

  const renderKpis = (k) => {
    const g = document.getElementById("kpiGrid");
    const items = [
      { label: "Total Matters",     value: LEXORA.fmtNum(k.total_cases), sub: `${k.open_cases} open · ${k.closed_cases} closed` },
      { label: "Critical Matters",  value: LEXORA.fmtNum(k.critical_cases), sub: "Require partner attention", cls: "danger" },
      { label: "Portfolio Value",   value: LEXORA.fmtMoney(k.total_value_usd), sub: "Estimated exposure / claim value" },
      { label: "Billable Hours",    value: LEXORA.fmtNum(Math.round(k.billable_hours)), sub: "Recorded against open matters" },
      { label: "Documents Indexed", value: LEXORA.fmtNum(k.documents_indexed), sub: "Searchable via RAG", cls: "good" },
      { label: "Upcoming (14d)",    value: LEXORA.fmtNum(k.upcoming_events_14d), sub: "Hearings, depos, filings" },
      { label: "Notifications (30d)", value: LEXORA.fmtNum(k.notifications_30d), sub: "Auto + manual sent" },
    ];
    g.innerHTML = items.map(i =>
      `<div class="kpi ${i.cls||''}"><div class="label">${i.label}</div>
       <div class="value">${i.value}</div><div class="sub">${i.sub}</div></div>`
    ).join("");
  };

  const baseOpts = () => {
    const c = LEXORA.chartColors();
    return {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: c.text, boxWidth: 12, padding: 12, font: { size: 11 } } },
        tooltip: { backgroundColor: "rgba(20,22,40,0.92)", borderColor: c.grid, borderWidth: 1, titleColor: c.text, bodyColor: c.text },
      },
      scales: {
        x: { ticks: { color: c.muted }, grid: { color: c.grid } },
        y: { ticks: { color: c.muted }, grid: { color: c.grid } },
      },
    };
  };

  const drawStatus = (data) => {
    if (charts.status) charts.status.destroy();
    const ctx = document.getElementById("chartStatus");
    const labels = Object.keys(data); const values = Object.values(data);
    const pal = LEXORA.palette();
    charts.status = new Chart(ctx, {
      type: "doughnut",
      data: { labels, datasets: [{ data: values, backgroundColor: pal, borderWidth: 0 }] },
      options: { ...baseOpts(), cutout: "62%", scales: {} },
    });
  };

  const drawPractice = (data) => {
    if (charts.practice) charts.practice.destroy();
    const ctx = document.getElementById("chartPractice");
    const labels = Object.keys(data); const values = Object.values(data);
    const c = LEXORA.chartColors();
    charts.practice = new Chart(ctx, {
      type: "bar",
      data: { labels, datasets: [{ label: "Matters", data: values,
        backgroundColor: c.a1, borderRadius: 8 }] },
      options: baseOpts(),
    });
  };

  const drawFilings = (data) => {
    if (charts.filings) charts.filings.destroy();
    const ctx = document.getElementById("chartFilings");
    const labels = Object.keys(data); const values = Object.values(data);
    const c = LEXORA.chartColors();
    charts.filings = new Chart(ctx, {
      type: "line",
      data: { labels, datasets: [{ label: "Filings", data: values,
        borderColor: c.a2, backgroundColor: "rgba(41,211,196,.20)", fill: true,
        tension: .35, pointRadius: 3, pointHoverRadius: 6,
        pointBackgroundColor: c.a2 }] },
      options: baseOpts(),
    });
  };

  const drawValue = (data) => {
    if (charts.value) charts.value.destroy();
    const ctx = document.getElementById("chartValue");
    const labels = Object.keys(data);
    const values = Object.values(data).map(v => +(v/1e6).toFixed(2));
    const pal = LEXORA.palette();
    charts.value = new Chart(ctx, {
      type: "bar",
      data: { labels, datasets: [{ label: "USD (M)", data: values,
        backgroundColor: pal, borderRadius: 8 }] },
      options: baseOpts(),
    });
  };

  let _patterns = [];

  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  const renderPatterns = (list) => {
    const el = document.getElementById("patternList");
    _patterns = Array.isArray(list) ? list : [];
    if (!_patterns.length) { el.innerHTML = `<div class="muted">No anomalies detected.</div>`; return; }
    el.innerHTML = _patterns.map((p, i) => {
      const conf = p.confidence != null ? Math.round(p.confidence * 100) : null;
      const isAI = p.source === "llm";
      const src = isAI
        ? `<span class="pat-chip src ai" title="Discovered by the LLM reasoning layer">✦ AI</span>`
        : `<span class="pat-chip src stat" title="Detected by the statistical engine">∑ STAT</span>`;
      const chips = [
        src,
        p.category ? `<span class="pat-chip cat">${esc(p.category)}</span>` : "",
        p.metric ? `<span class="pat-chip metric">${esc(p.metric)}</span>` : "",
        conf != null ? `<span class="pat-chip conf">${conf}% conf</span>` : "",
      ].join("");
      return `<div class="pattern ${esc(p.severity)}${isAI ? " ai" : ""}">
         <div class="pattern-bar"></div>
         <div class="pattern-body">
           <div class="title">${esc(p.title)}</div>
           <div class="pat-chips">${chips}</div>
           <div class="detail">${esc(p.detail)}</div>
           <button class="pat-explain" data-idx="${i}">Explain &rsaquo;</button>
         </div>
       </div>`;
    }).join("");
  };

  const openPatternModal = (idx) => {
    const p = _patterns[idx];
    if (!p) return;
    const modal = document.getElementById("patternModal");
    const isAI = p.source === "llm";
    const conf = p.confidence != null ? Math.round(p.confidence * 100) : null;

    const srcEl = document.getElementById("pmSource");
    srcEl.className = "pat-chip src " + (isAI ? "ai" : "stat");
    srcEl.textContent = isAI ? "✦ AI" : "∑ STAT";

    document.getElementById("pmTitle").textContent = p.title || "";

    document.getElementById("pmChips").innerHTML = [
      `<span class="pat-chip method">${esc(p.method || (isAI ? "LLM synthesis" : "Statistical model"))}</span>`,
      p.category ? `<span class="pat-chip cat">${esc(p.category)}</span>` : "",
      p.severity ? `<span class="pat-chip sev ${esc(p.severity)}">${esc(p.severity)}</span>` : "",
      p.metric ? `<span class="pat-chip metric">${esc(p.metric)}</span>` : "",
      conf != null ? `<span class="pat-chip conf">${conf}% confidence</span>` : "",
    ].join("");

    document.getElementById("pmDetail").textContent = p.detail || "—";

    const actWrap = document.getElementById("pmActionWrap");
    if (p.recommended_action) {
      actWrap.classList.remove("hidden");
      document.getElementById("pmAction").textContent = p.recommended_action;
    } else { actWrap.classList.add("hidden"); }

    const evWrap = document.getElementById("pmEvidenceWrap");
    if (Array.isArray(p.evidence) && p.evidence.length) {
      evWrap.classList.remove("hidden");
      document.getElementById("pmEvidence").innerHTML =
        p.evidence.map(e => `<li>${esc(e)}</li>`).join("");
    } else { evWrap.classList.add("hidden"); }

    modal.classList.remove("hidden");
  };

  const closePatternModal = () => {
    document.getElementById("patternModal").classList.add("hidden");
  };

  const renderEngine = (engine) => {
    const el = document.getElementById("patternEngine");
    if (!el || !engine) return;
    el.textContent = `${engine.statistical} statistical · ${engine.llm} AI-discovered`;
  };

  async function loadInsight() {
    try {
      const data = await LEXORA.api("/api/analytics/insights");
      if (data && Array.isArray(data.patterns) && data.patterns.length) {
        renderPatterns(data.patterns);   // fused statistical + AI-discovered list
        renderEngine(data.engine);
      }
    } catch (e) { /* keep the statistical-only paint already shown */ }
  }

  async function load() {
    try {
      const [ov, pat] = await Promise.all([
        LEXORA.api("/api/analytics/overview"),
        LEXORA.api("/api/analytics/patterns"),
      ]);
      _lastData = { ov, pat };
      renderKpis(ov.kpis);
      drawStatus(ov.status_distribution);
      drawPractice(ov.by_practice);
      drawFilings(ov.monthly_filings);
      drawValue(ov.value_by_practice);
      renderPatterns(pat.patterns);   // instant statistical paint
      loadInsight();                  // progressive hybrid enhancement
    } catch (e) { LEXORA.toast("Dashboard load failed: " + e.message); }
  }

  // Event wiring: open via "Explain" pill, close via button/backdrop/Esc.
  document.addEventListener("click", (e) => {
    const pill = e.target.closest(".pat-explain");
    if (pill) { openPatternModal(+pill.dataset.idx); return; }
    if (e.target.id === "pmClose") { closePatternModal(); return; }
    if (e.target.id === "patternModal") { closePatternModal(); }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closePatternModal();
  });

  window.addEventListener("lexora:ready", load);
  window.addEventListener("lexora:view", (e) => {
    if (e.detail.view === "dashboard") load();
  });
  window.addEventListener("lexora:rerender", () => {
    if (_lastData) {
      drawStatus(_lastData.ov.status_distribution);
      drawPractice(_lastData.ov.by_practice);
      drawFilings(_lastData.ov.monthly_filings);
      drawValue(_lastData.ov.value_by_practice);
    }
  });
})();
