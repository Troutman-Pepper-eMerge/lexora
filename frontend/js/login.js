/* Login page logic. Pulls demo profiles, lets user pick a role,
   then redirects to the dashboard. */
(async function () {
  const grid = document.getElementById("profiles");
  try {
    const r = await fetch("/api/auth/profiles");
    if (!r.ok) throw new Error("Demo mode disabled");
    const { profiles } = await r.json();
    grid.innerHTML = "";
    profiles.forEach(p => {
      const el = document.createElement("div");
      el.className = "profile";
      el.innerHTML = `
        <div class="who-bits">
          <strong>${p.name}</strong>
          <span>${p.email} · ${p.department}</span>
        </div>
        <span class="role-pill">${p.role}</span>`;
      el.addEventListener("click", async () => {
        const res = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: p.email }),
        });
        if (res.ok) window.location.href = "/";
        else alert("Login failed");
      });
      grid.appendChild(el);
    });
  } catch (e) {
    grid.innerHTML = `<div class="profile">
      <div class="who-bits">
        <strong>Entra ID required</strong>
        <span>Demo mode is off; supply a Bearer token from Azure AD.</span>
      </div>
    </div>`;
  }
})();
