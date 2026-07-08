/* Notification Center: live feed of all queued/sent notifications. */
(function () {
  const feed     = document.getElementById("ntFeed");
  const kpis     = document.getElementById("ntKpis");
  const countEl  = document.getElementById("ntCount");
  const selChan  = document.getElementById("ntChannel");
  const selStat  = document.getElementById("ntStatus");
  const refresh  = document.getElementById("ntRefresh");

  let _all = [];

  const CHANNEL_ICON = { email: "✉", sms: "💬", inapp: "🔔" };

  function relTime(iso) {
    if (!iso) return "—";
    const then = new Date(iso).getTime();
    const diff = Date.now() - then;
    const m = Math.round(diff / 60000);
    if (m < 1) return "just now";
    if (m < 60) return `${m}m ago`;
    const h = Math.round(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.round(h / 24);
    if (d < 30) return `${d}d ago`;
    return new Date(iso).toLocaleDateString(undefined,
      { month: "short", day: "2-digit", year: "numeric" });
  }

  function esc(s) {
    return (s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  }

  function renderKpis(list) {
    const total  = list.length;
    const sent   = list.filter(n => n.status === "sent").length;
    const queued = list.filter(n => n.status === "queued").length;
    const recips = new Set(list.map(n => n.recipient)).size;
    const items = [
      { label: "Total Notifications", value: total,  sub: "Across all channels" },
      { label: "Delivered",           value: sent,   sub: "Marked sent", cls: "good" },
      { label: "Queued",              value: queued, sub: "Awaiting dispatch", cls: "danger" },
      { label: "Unique Recipients",   value: recips, sub: "Attorneys & clients" },
    ];
    kpis.innerHTML = items.map(i =>
      `<div class="kpi ${i.cls||''}"><div class="label">${i.label}</div>
       <div class="value">${i.value}</div><div class="sub">${i.sub}</div></div>`
    ).join("");
  }

  function card(n) {
    const icon = CHANNEL_ICON[n.channel] || "🔔";
    const statusCls = n.status === "sent" ? "low"
                    : n.status === "failed" ? "high" : "medium";
    return `<div class="nt-card">
      <div class="nt-icon">${icon}</div>
      <div class="nt-main">
        <div class="nt-top">
          <span class="nt-subject">${esc(n.subject)}</span>
          <span class="pill ${statusCls}">${n.status}</span>
        </div>
        <div class="nt-meta">
          <span class="nt-to">${esc(n.recipient)}</span>
          <span class="nt-dot">·</span>
          <span class="nt-chan">${n.channel}</span>
          ${n.case_id ? `<span class="nt-dot">·</span><span class="nt-case">Case #${n.case_id}</span>` : ""}
          <span class="nt-dot">·</span>
          <span class="nt-time">${relTime(n.sent_at || n.created_at)}</span>
        </div>
        <div class="nt-body">${esc(n.body)}</div>
      </div>
    </div>`;
  }

  function applyFilters() {
    const ch = selChan.value, st = selStat.value;
    const list = _all.filter(n =>
      (!ch || n.channel === ch) && (!st || n.status === st));
    countEl.textContent = `${list.length} of ${_all.length}`;
    feed.innerHTML = list.map(card).join("") ||
      `<div class="muted" style="padding:20px;text-align:center">No notifications match these filters.</div>`;
  }

  async function load() {
    try {
      const { notifications } = await LEXORA.api("/api/notifications?limit=200");
      _all = notifications || [];
      renderKpis(_all);
      applyFilters();
    } catch (e) { LEXORA.toast("Notifications load failed: " + e.message); }
  }

  selChan.addEventListener("change", applyFilters);
  selStat.addEventListener("change", applyFilters);
  refresh.addEventListener("click", load);

  window.addEventListener("lexora:view", (e) => {
    if (e.detail.view === "notifications") load();
  });
})();
