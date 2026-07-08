/* Litigation Outcome & Settlement Predictor */
(function () {
  const L = window.LEXORA;
  const $ = (id) => document.getElementById(id);
  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (m) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[m]));

  let modal, loadedCases = false, running = false;

  const pct = (x) => `${Math.round((x ?? 0) * 100)}%`;
  const days = (n) => (n == null ? "—" : `${Math.round(n)}d`);

  function setStatus(msg, kind) {
    const el = $("prStatus");
    if (!msg) { el.classList.add("hidden"); el.textContent = ""; return; }
    el.className = `pr-status ${kind || ""}`;
    el.textContent = msg;
    el.classList.remove("hidden");
  }

  async function ensureCases() {
    if (loadedCases) return;
    const sel = $("prCaseSel");
    try {
      const data = await L.api("/api/cases?limit=200");
      const cases = (data.cases || []).slice().sort((a, b) =>
        (a.case_number || "").localeCompare(b.case_number || ""));
      if (!cases.length) {
        sel.innerHTML = `<option value="">No cases available</option>`;
        return;
      }
      sel.innerHTML =
        `<option value="">— Choose a matter —</option>` +
        cases.map((c) =>
          `<option value="${c.id}">${esc(c.case_number)} · ${esc(c.title)}</option>`
        ).join("");
      loadedCases = true;
    } catch (e) {
      sel.innerHTML = `<option value="">Failed to load cases</option>`;
    }
  }

  function riskClass(band) {
    const b = (band || "").toLowerCase();
    if (b === "high") return "risk-high";
    if (b === "moderate") return "risk-mod";
    return "risk-low";
  }

  function renderFactors(factors) {
    const wrap = $("prFactors");
    if (!factors || !factors.length) { wrap.innerHTML = ""; return; }
    const max = Math.max(...factors.map((f) => f.weight || 0), 0.01);
    wrap.innerHTML = factors.map((f) => {
      const w = Math.max(6, Math.round((f.weight / max) * 100));
      const imp = f.impact || "neutral";
      const arrow = imp === "increases" ? "▲" : imp === "decreases" ? "▼" : "•";
      return `
        <div class="pr-factor ${imp}">
          <div class="pr-factor-top">
            <span class="pr-factor-arrow">${arrow}</span>
            <span class="pr-factor-label">${esc(f.label)}</span>
            <span class="pr-factor-weight">${(f.weight ?? 0).toFixed(2)}</span>
          </div>
          <div class="pr-factor-bar"><span style="width:${w}%"></span></div>
          ${f.detail ? `<div class="pr-factor-detail">${esc(f.detail)}</div>` : ""}
        </div>`;
    }).join("");
  }

  function render(res) {
    const p = res.prediction || {};
    // Gauge
    const sp = p.settlement_likelihood ?? 0;
    $("prSettlePct").textContent = pct(sp);
    const deg = Math.round(sp * 360);
    const gauge = $("prGauge");
    const col = sp >= 0.6 ? "var(--good)" : sp >= 0.4 ? "var(--warn)" : "var(--danger)";
    gauge.style.background =
      `conic-gradient(${col} ${deg}deg, rgba(255,255,255,.08) ${deg}deg)`;

    $("prDuration").textContent = days(p.expected_duration_days);
    $("prDurationRange").textContent =
      `${days(p.duration_low_days)} – ${days(p.duration_high_days)} · age ${days(p.age_days)}`;

    $("prSettleExp").textContent = L.fmtMoney(p.settlement_expected);
    $("prSettleRange").textContent =
      `${L.fmtMoney(p.settlement_low)} – ${L.fmtMoney(p.settlement_high)}`;

    $("prFavorable").textContent = pct(p.favorable_outcome);
    $("prTrial").textContent = `Trial risk ${pct(p.trial_likelihood)}`;

    const risk = $("prRisk");
    risk.textContent = p.risk_band || "—";
    risk.className = `pr-mc-val ${riskClass(p.risk_band)}`;
    $("prConf").textContent = `Confidence ${p.confidence ?? "—"}`;

    $("prNarrative").textContent = res.narrative || "";

    renderFactors(res.factors);

    const ev = res.evidence || [];
    $("prEvCount").textContent = ev.length ? `(${ev.length})` : "";
    $("prEvidence").innerHTML = ev.map((e) => `<li>${esc(e)}</li>`).join("");

    $("prResults").classList.remove("hidden");
  }

  async function run() {
    if (running) return;
    const id = $("prCaseSel").value;
    if (!id) { setStatus("Select a matter first.", "warn"); return; }
    running = true;
    const btn = $("prRun");
    btn.disabled = true;
    btn.textContent = "✦ Running model…";
    $("prResults").classList.add("hidden");
    setStatus("Scoring matter against portfolio model and generating strategy…", "working");
    try {
      const res = await L.api(`/api/analytics/predict/${id}`);
      setStatus("", null);
      render(res);
    } catch (e) {
      setStatus("Prediction failed. Try another matter.", "error");
    } finally {
      running = false;
      btn.disabled = false;
      btn.textContent = "✦ Run prediction";
    }
  }

  function open() {
    modal.classList.remove("hidden");
    ensureCases();
  }
  function close() { modal.classList.add("hidden"); }

  document.addEventListener("DOMContentLoaded", () => {
    modal = $("predictorModal");
    if (!modal) return;
    const btn = $("predictorBtn");
    if (btn) btn.addEventListener("click", open);
    $("prClose").addEventListener("click", close);
    $("prCloseBtn").addEventListener("click", close);
    $("prRun").addEventListener("click", run);
    modal.addEventListener("click", (e) => { if (e.target === modal) close(); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !modal.classList.contains("hidden")) close();
    });
  });
})();
