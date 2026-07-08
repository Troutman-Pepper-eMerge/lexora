/* Theme toggle - persists in localStorage, default = dark */
(function () {
  const root = document.documentElement;
  const stored = localStorage.getItem("lexora-theme");
  if (stored === "light") root.setAttribute("data-theme", "light");

  function bind() {
    const btn = document.getElementById("themeToggle");
    if (!btn) return;
    btn.addEventListener("click", () => {
      const cur = root.getAttribute("data-theme") || "dark";
      const nxt = cur === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", nxt);
      localStorage.setItem("lexora-theme", nxt);
      window.dispatchEvent(new CustomEvent("lexora:theme", { detail: { theme: nxt } }));
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else { bind(); }
})();
