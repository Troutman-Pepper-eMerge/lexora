/* App-wide helpers, router, auth bootstrap. */
window.LEXORA = (function () {
  const api = async (path, opts = {}) => {
    const r = await fetch(path, {
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      ...opts,
    });
    if (r.status === 401) { window.location.href = "/login"; throw new Error("unauth"); }
    if (!r.ok) {
      let detail = "";
      try { detail = (await r.json()).detail || ""; } catch { detail = r.statusText; }
      throw new Error(detail || `HTTP ${r.status}`);
    }
    return r.json();
  };

  const toast = (msg, ms = 2400) => {
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = msg; el.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.remove("show"), ms);
  };

  const fmtMoney = (n) => {
    if (n == null) return "—";
    if (n >= 1e9) return `$${(n/1e9).toFixed(2)}B`;
    if (n >= 1e6) return `$${(n/1e6).toFixed(2)}M`;
    if (n >= 1e3) return `$${(n/1e3).toFixed(1)}K`;
    return `$${n.toFixed(0)}`;
  };

  const fmtNum = (n) => (n ?? 0).toLocaleString();

  const fmtDate = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      year: "numeric", month: "short", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  };

  const priorityPill = (p) => {
    const k = (p || "").toLowerCase();
    return `<span class="pill ${k}">${p || "—"}</span>`;
  };

  // --- Chart theme helper (re-themed on toggle) ---
  const chartColors = () => {
    const styles = getComputedStyle(document.documentElement);
    return {
      text: styles.getPropertyValue("--text").trim(),
      muted: styles.getPropertyValue("--muted").trim(),
      grid: styles.getPropertyValue("--line").trim(),
      a1: "#7c5cff", a2: "#29d3c4", a3: "#ff6bcb",
      a4: "#ffb454", a5: "#38d39f", a6: "#5fb3ff",
      a7: "#ff5d6c", a8: "#c084fc",
    };
  };

  const palette = () => {
    const c = chartColors();
    return [c.a1, c.a2, c.a3, c.a4, c.a5, c.a6, c.a7, c.a8];
  };

  // --- Router (tabs) ---
  const views = document.querySelectorAll(".view");
  const tabs = document.querySelectorAll("#navTabs .tab");
  const switchTo = (name) => {
    views.forEach(v => v.classList.toggle("active", v.dataset.view === name));
    tabs.forEach(t => t.classList.toggle("active", t.dataset.view === name));
    window.dispatchEvent(new CustomEvent("lexora:view", { detail: { view: name } }));
  };
  tabs.forEach(t => t.addEventListener("click", () => switchTo(t.dataset.view)));

  // --- Boot: identify user ---
  (async function init() {
    try {
      const { principal } = await api("/api/auth/me");
      const who = document.getElementById("who");
      who.innerHTML = `<strong>${principal.display_name}</strong><small>${principal.role} · ${principal.department || ""}</small>`;
      window.LEXORA_PRINCIPAL = principal;
    } catch (e) {
      window.location.href = "/login";
      return;
    }
    document.getElementById("logoutBtn").addEventListener("click", async () => {
      await api("/api/auth/logout", { method: "POST" });
      window.location.href = "/login";
    });
    window.dispatchEvent(new CustomEvent("lexora:ready"));
  })();

  // Re-render charts on theme change (each chart module listens)
  window.addEventListener("lexora:theme", () => {
    window.dispatchEvent(new CustomEvent("lexora:rerender"));
  });

  return { api, toast, fmtMoney, fmtNum, fmtDate, priorityPill,
           chartColors, palette, switchTo };
})();
