/* Calendar view: upcoming appointments + reschedule modal with custom date/time picker. */
(function () {
  const tbody     = document.querySelector("#apptTable tbody");
  const modal     = document.getElementById("rescheduleModal");
  const rsApptId  = document.getElementById("rsApptId");
  const rsWhen    = document.getElementById("rsWhen");
  const rsReason  = document.getElementById("rsReason");

  // New appointment modal elements
  const newApptModal = document.getElementById("newApptModal");
  const newApptForm  = document.getElementById("newApptForm");
  const naCase       = document.getElementById("naCase");
  const naTitle      = document.getElementById("naTitle");
  const naType       = document.getElementById("naType");
  const naWhen       = document.getElementById("naWhen");
  const naDuration   = document.getElementById("naDuration");
  const naLocation   = document.getElementById("naLocation");
  const naAttendees  = document.getElementById("naAttendees");

  // Custom datetime picker bits
  const dateBtn    = document.getElementById("rsDateBtn");
  const dateLabel  = document.getElementById("rsDateLabel");
  const datePop    = document.getElementById("rsDatePop");
  const monthLabel = document.getElementById("rsMonthLabel");
  const grid       = document.getElementById("rsGrid");
  const prevBtn    = document.getElementById("rsPrev");
  const nextBtn    = document.getElementById("rsNext");
  const selHour    = document.getElementById("rsHour");
  const selMinute  = document.getElementById("rsMinute");
  const selAmPm    = document.getElementById("rsAmPm");

  const MONTHS = ["January","February","March","April","May","June",
                  "July","August","September","October","November","December"];

  let _currentId = null;
  let _viewYear, _viewMonth;
  let _selected = null;          // Date object

  // Build hour / minute selects once
  for (let h = 1; h <= 12; h++) {
    const o = document.createElement("option");
    o.value = String(h); o.textContent = String(h).padStart(2,"0");
    selHour.appendChild(o);
  }
  for (let m = 0; m < 60; m += 15) {
    const o = document.createElement("option");
    o.value = String(m); o.textContent = String(m).padStart(2,"0");
    selMinute.appendChild(o);
  }

  function row(a) {
    return `<tr>
      <td>${LEXORA.fmtDate(a.when)}</td>
      <td>${a.title}</td>
      <td>${a.type||''}</td>
      <td>#${a.case_id ?? '—'}</td>
      <td>${a.location||''}</td>
      <td><span class="pill">${a.status}</span></td>
      <td><button class="btn-ghost" data-id="${a.id}">Reschedule</button></td>
    </tr>`;
  }

  async function load() {
    try {
      const { appointments } = await LEXORA.api("/api/appointments?days=60");
      tbody.innerHTML = appointments.map(row).join("") ||
        `<tr><td colspan="7" class="muted">No appointments.</td></tr>`;
      tbody.querySelectorAll("button[data-id]").forEach(b => {
        b.addEventListener("click", () => openModal(parseInt(b.dataset.id)));
      });
    } catch (e) { LEXORA.toast("Calendar load failed: " + e.message); }
  }

  function openModal(id) {
    _currentId = id;
    rsApptId.textContent = `#${id}`;
    rsReason.value = "";
    // Default to tomorrow 10:00 AM
    const def = new Date();
    def.setDate(def.getDate() + 1);
    def.setHours(10, 0, 0, 0);
    setSelected(def);
    datePop.classList.add("hidden");
    modal.classList.remove("hidden");
  }

  function pad(n) { return String(n).padStart(2, "0"); }

  function setSelected(d) {
    _selected = d;
    _viewYear = d.getFullYear();
    _viewMonth = d.getMonth();
    dateLabel.textContent = d.toLocaleDateString(undefined, {
      year: "numeric", month: "short", day: "2-digit",
    });
    // Sync time selects
    const h24 = d.getHours();
    const m = Math.round(d.getMinutes() / 15) * 15 % 60;
    const ampm = h24 >= 12 ? "PM" : "AM";
    const h12 = h24 % 12 || 12;
    selHour.value = String(h12);
    selMinute.value = String(m);
    selAmPm.value = ampm;
    renderGrid();
    syncHidden();
  }

  function syncHidden() {
    if (!_selected) { rsWhen.value = ""; return; }
    const d = new Date(_selected);
    let h = parseInt(selHour.value, 10);
    const m = parseInt(selMinute.value, 10);
    if (selAmPm.value === "PM" && h !== 12) h += 12;
    if (selAmPm.value === "AM" && h === 12) h = 0;
    d.setHours(h, m, 0, 0);
    rsWhen.value =
      `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T` +
      `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function renderGrid() {
    monthLabel.textContent = `${MONTHS[_viewMonth]} ${_viewYear}`;
    const firstDay   = new Date(_viewYear, _viewMonth, 1);
    const startDow   = firstDay.getDay();
    const daysInMo   = new Date(_viewYear, _viewMonth + 1, 0).getDate();
    const daysInPrev = new Date(_viewYear, _viewMonth, 0).getDate();
    const today = new Date(); today.setHours(0,0,0,0);
    const selStr = _selected
      ? `${_selected.getFullYear()}-${_selected.getMonth()}-${_selected.getDate()}`
      : "";

    let cells = "";
    for (let i = startDow - 1; i >= 0; i--) {
      cells += `<button type="button" class="dtp-cell other" disabled>${daysInPrev - i}</button>`;
    }
    for (let d = 1; d <= daysInMo; d++) {
      const dt = new Date(_viewYear, _viewMonth, d);
      const isToday = dt.getTime() === today.getTime();
      const isSel = `${_viewYear}-${_viewMonth}-${d}` === selStr;
      cells += `<button type="button" class="dtp-cell${isToday?' today':''}${isSel?' selected':''}" data-day="${d}">${d}</button>`;
    }
    const total = startDow + daysInMo;
    const trailing = (7 - (total % 7)) % 7;
    for (let i = 1; i <= trailing; i++) {
      cells += `<button type="button" class="dtp-cell other" disabled>${i}</button>`;
    }
    grid.innerHTML = cells;

    grid.querySelectorAll("button[data-day]").forEach(b => {
      b.addEventListener("click", () => {
        const day = parseInt(b.dataset.day, 10);
        const picked = new Date(_viewYear, _viewMonth, day,
                                _selected ? _selected.getHours() : 10,
                                _selected ? _selected.getMinutes() : 0);
        setSelected(picked);
        datePop.classList.add("hidden");
      });
    });
  }

  dateBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    datePop.classList.toggle("hidden");
  });
  document.addEventListener("click", (e) => {
    if (!datePop.contains(e.target) && e.target !== dateBtn) {
      datePop.classList.add("hidden");
    }
  });
  prevBtn.addEventListener("click", () => {
    _viewMonth--; if (_viewMonth < 0) { _viewMonth = 11; _viewYear--; }
    renderGrid();
  });
  nextBtn.addEventListener("click", () => {
    _viewMonth++; if (_viewMonth > 11) { _viewMonth = 0; _viewYear++; }
    renderGrid();
  });
  [selHour, selMinute, selAmPm].forEach(el =>
    el.addEventListener("change", syncHidden));

  document.getElementById("rsCancel")?.addEventListener("click",
    () => modal.classList.add("hidden"));

  document.getElementById("rsConfirm")?.addEventListener("click", async () => {
    if (!rsWhen.value) { LEXORA.toast("Pick a new date/time"); return; }
    try {
      await LEXORA.api(`/api/appointments/${_currentId}/reschedule`, {
        method: "POST",
        body: JSON.stringify({ new_datetime: rsWhen.value, reason: rsReason.value }),
      });
      LEXORA.toast(`Rescheduled #${_currentId}; attendees notified`);
      modal.classList.add("hidden"); load();
    } catch (e) { LEXORA.toast(e.message); }
  });

  // Load matters for dropdown
  async function loadMattersDropdown() {
    try {
      const { cases } = await LEXORA.api("/api/cases");
      const list = Array.isArray(cases) ? cases : [];
      naCase.innerHTML = "";
      const blank = document.createElement("option");
      blank.value = "";
      blank.textContent = "Select a matter...";
      naCase.appendChild(blank);
      list.forEach((c) => {
        const opt = document.createElement("option");
        opt.value = String(c.id);
        opt.textContent = `${c.case_number} — ${c.title}`;
        naCase.appendChild(opt);
      });
    } catch (e) {
      console.error("Failed to load matters:", e);
    }
  }

  // New appointment modal handlers
  document.getElementById("newApptBtn")?.addEventListener("click", async () => {
    const role = window.LEXORA_PRINCIPAL?.role;
    if (!role || !["Partner", "Associate", "Paralegal"].includes(role)) {
      LEXORA.toast("You don't have permission to schedule appointments.");
      return;
    }
    newApptForm.reset();
    await loadMattersDropdown();
    // Set default datetime to tomorrow at 10 AM
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    tomorrow.setHours(10, 0, 0, 0);
    const iso = tomorrow.toISOString().slice(0, 16);
    naWhen.value = iso;
    newApptModal.classList.remove("hidden");
  });

  document.getElementById("naClose")?.addEventListener("click", () => {
    newApptModal.classList.add("hidden");
  });

  document.getElementById("naCancel")?.addEventListener("click", () => {
    newApptModal.classList.add("hidden");
  });

  newApptModal?.addEventListener("click", (e) => {
    if (e.target === newApptModal) newApptModal.classList.add("hidden");
  });

  newApptForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const attendees = naAttendees.value.trim()
      ? naAttendees.value.split(",").map(s => s.trim()).filter(Boolean)
      : [];

    const payload = {
      case_id: parseInt(naCase.value, 10),
      title: naTitle.value.trim(),
      appointment_type: naType.value,
      scheduled_at: naWhen.value,
      duration_minutes: parseInt(naDuration.value, 10),
      location: naLocation.value.trim(),
      attendees,
    };

    const btn = document.getElementById("naSave");
    btn.disabled = true;
    btn.textContent = "Scheduling...";

    try {
      await LEXORA.api("/api/appointments", {
        method: "POST",
        body: JSON.stringify(payload),
        headers: { "Content-Type": "application/json" },
      });
      LEXORA.toast("Appointment scheduled successfully");
      newApptModal.classList.add("hidden");
      load();
    } catch (err) {
      LEXORA.toast("Failed to schedule: " + err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Schedule";
    }
  });

  window.addEventListener("lexora:view", (e) => {
    if (e.detail.view === "calendar") load();
  });
})();
