/* Cases view: list, filter, detail. */
(function () {
  const tbody = document.querySelector("#caseTable tbody");
  const detail = document.getElementById("caseDetail");
  const casesView = document.querySelector('.view[data-view="cases"]');
  const listCard = document.getElementById("caseListCard");
  const search = document.getElementById("caseSearch");
  const statusSel = document.getElementById("caseStatus");
  const jurisSel = document.getElementById("caseJuris");
  const editBtn = document.getElementById("cdEdit");
  let _cases = [];
  let _detailCase = null;
  const EDIT_ROLES = new Set(["Admin", "Partner", "Associate", "Paralegal"]);

  function canEditMatters() {
    const role = window.LEXORA_PRINCIPAL?.role;
    return EDIT_ROLES.has(role);
  }

  function syncEditVisibility() {
    if (!editBtn) return;
    editBtn.classList.toggle("hidden", !canEditMatters());
  }
  // Don't call on initial load - wait for principal to be ready
  // syncEditVisibility();

  function rowHTML(c) {
    const actions = canEditMatters()
      ? `<button class="btn-ghost case-edit-row" data-edit-id="${c.id}">Edit</button>`
      : "—";
    return `<tr data-id="${c.id}">
      <td>${c.case_number}</td>
      <td>${c.title}</td>
      <td>${c.client_name || ''}</td>
      <td>${c.practice_area || ''}</td>
      <td>${c.jurisdiction || ''}</td>
      <td><span class="pill">${c.status || ''}</span></td>
      <td>${LEXORA.priorityPill(c.priority)}</td>
      <td>${LEXORA.fmtMoney(c.estimated_value)}</td>
      <td>${actions}</td>
    </tr>`;
  }

  function populateFilters() {
    const uniq = (k) => [...new Set(_cases.map(c => c[k]).filter(Boolean))].sort();
    statusSel.innerHTML = '<option value="">All Statuses</option>' +
      uniq("status").map(s => `<option>${s}</option>`).join("");
    jurisSel.innerHTML = '<option value="">All Jurisdictions</option>' +
      uniq("jurisdiction").map(s => `<option>${s}</option>`).join("");
  }

  async function load() {
    const params = new URLSearchParams();
    if (search.value) params.set("q", search.value);
    if (statusSel.value) params.set("status", statusSel.value);
    if (jurisSel.value) params.set("jurisdiction", jurisSel.value);
    const { cases } = await LEXORA.api(`/api/cases?${params}`);
    _cases = cases;
    if (!statusSel.options.length || statusSel.options.length === 1) populateFilters();
    tbody.innerHTML = cases.map(rowHTML).join("") ||
      `<tr><td colspan="9" class="muted">No matters match.</td></tr>`;
    tbody.querySelectorAll("button[data-edit-id]").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (!canEditMatters()) return;
        const id = parseInt(btn.dataset.editId, 10);
        const c = _cases.find(row => row.id === id);
        if (c) openEditModal(c);
      });
    });
    tbody.querySelectorAll("tr[data-id]").forEach(tr => {
      tr.addEventListener("click", () => showDetail(parseInt(tr.dataset.id)));
    });
  }

  const CAT_META = {
    intake:     { icon: "IN", label: "Intake" },
    filing:     { icon: "FL", label: "Filing" },
    discovery:  { icon: "DS", label: "Discovery" },
    motion:     { icon: "MO", label: "Motion" },
    hearing:    { icon: "HR", label: "Hearing" },
    settlement: { icon: "ST", label: "Settlement" },
    closed:     { icon: "OK", label: "Closed" },
    other:      { icon: "EV", label: "Event" },
  };

  function renderTimeline(items) {
    if (!items || !items.length) return "";
    const fmt = (iso) => {
      if (!iso) return "—";
      const d = new Date(iso);
      return d.toLocaleDateString(undefined,
        { year: "numeric", month: "short", day: "numeric" });
    };
    const rows = items.map((e) => {
      const cat = e.category || "other";
      const meta = CAT_META[cat] || CAT_META.other;
      const cls = `tl-item tl-${cat}` + (e.upcoming ? " tl-upcoming" : "");
      const badge = e.upcoming
        ? '<span class="tl-flag upcoming">Upcoming</span>'
        : '<span class="tl-flag done">Completed</span>';
      const sub = e.description
        ? `<div class="tl-desc">${e.description}</div>` : "";
      return `<li class="${cls}">
        <span class="tl-node"><span class="tl-ico">${meta.icon}</span></span>
        <div class="tl-body">
          <div class="tl-top">
            <span class="tl-date">${fmt(e.date)}</span>${badge}
          </div>
          <div class="tl-title">${e.title || meta.label}</div>
          ${sub}
        </div>
      </li>`;
    }).join("");
    return `
      <details class="cd-timeline-wrap">
        <summary class="cd-timeline-toggle">
          <span class="tl-chevron" aria-hidden="true">▶</span>
          <span class="tl-toggle-label">Matter History Timeline</span>
          <span class="tl-count">${items.length}</span>
        </summary>
        <ol class="cd-timeline">${rows}</ol>
      </details>`;
  }

  async function showDetail(id) {
    const c = await LEXORA.api(`/api/cases/${id}`);
    _detailCase = c;
    syncEditVisibility();
    listCard?.classList.add("hidden");
    detail.classList.remove("hidden");
    casesView?.classList.add("detail-open");
    document.getElementById("cdTitle").textContent = `${c.case_number} — ${c.title}`;
    const priorityTone = (p) => {
      const s = String(p || "").toLowerCase();
      if (s === "critical" || s === "high") return "danger";
      if (s === "medium") return "warn";
      if (s === "low") return "good";
      return "violet";
    };
    const statusTone = (s) => {
      const v = String(s || "").toLowerCase();
      if (v.includes("closed") || v.includes("settl")) return "good";
      if (v.includes("trial") || v.includes("appeal")) return "danger";
      if (v.includes("discovery") || v.includes("pending")) return "warn";
      return "teal";
    };
    // [key, value, tone] — tone drives the color coding
    const grid = [
      ["Client", c.client_name, "violet"], ["Practice", c.practice_area, "teal"],
      ["Type", c.case_type, "pink"], ["Status", c.status, statusTone(c.status)],
      ["Priority", c.priority, priorityTone(c.priority)], ["Jurisdiction", c.jurisdiction, "teal"],
      ["Court", c.court, "violet"], ["Judge", c.judge, "pink"],
      ["Opposing", c.opposing_counsel, "warn"],
      ["Filed", c.filed_date ? new Date(c.filed_date).toLocaleDateString() : "—", "teal"],
      ["Value", LEXORA.fmtMoney(c.estimated_value), "good"],
      ["Billable Hrs", LEXORA.fmtNum(Math.round(c.billable_hours || 0)), "violet"],
    ];
    const summary = c.summary ? `<p class="muted" style="margin-top:8px">${c.summary}</p>` : "";
    const docs = c.documents.map(d => `<tr>
      <td>${d.filename}</td><td>${d.category||''}</td>
      <td>${d.indexed ? '✓' : '—'}</td>
      <td>${d.pages || '—'}</td>
      <td class="muted" style="max-width:380px">${(d.summary||'').slice(0,160)}</td>
    </tr>`).join("");
    const appts = c.appointments.map(a => `<tr>
      <td>${LEXORA.fmtDate(a.when)}</td><td>${a.title}</td>
      <td>${a.type||''}</td><td>${a.location||''}</td>
      <td><span class="pill">${a.status}</span></td>
    </tr>`).join("");
    const notes = c.notes.map(n => `<div class="pattern">
      <div class="pattern-bar" style="background:var(--accent-2)"></div>
      <div><div class="detail">${n.body}</div>
           <div class="muted small">${LEXORA.fmtDate(n.created_at)}</div></div>
    </div>`).join("");

    const timeline = renderTimeline(c.timeline || []);

    document.getElementById("cdBody").innerHTML = `
      <div class="cd-grid">${grid.map(([k,v,tone]) =>
        `<div class="item tone-${tone||'violet'}"><div class="k">${k}</div><div class="v">${v||'—'}</div></div>`).join("")}
      </div>${summary}
      ${timeline}
      <h4 style="margin-top:18px">Documents (${c.documents.length})</h4>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>File</th><th>Category</th><th>Indexed</th><th>Pages</th><th>Summary</th></tr></thead>
        <tbody>${docs || '<tr><td colspan="5" class="muted">None yet</td></tr>'}</tbody></table></div>
      <h4 style="margin-top:18px">Appointments (${c.appointments.length})</h4>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>When</th><th>Title</th><th>Type</th><th>Location</th><th>Status</th></tr></thead>
        <tbody>${appts || '<tr><td colspan="5" class="muted">None</td></tr>'}</tbody></table></div>
      <h4 style="margin-top:18px">Notes (${c.notes.length})</h4>
      <div class="pattern-list">${notes || '<div class="muted">No notes.</div>'}</div>`;
    detail.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  document.getElementById("cdClose")?.addEventListener("click", () => {
    detail.classList.add("hidden");
    listCard?.classList.remove("hidden");
    casesView?.classList.remove("detail-open");
  });

  let _t;
  const debounced = () => { clearTimeout(_t); _t = setTimeout(load, 250); };
  search.addEventListener("input", debounced);
  statusSel.addEventListener("change", load);
  jurisSel.addEventListener("change", load);

  // ---------------------------------------------------------------- //
  // New Case intake                                                  //
  // ---------------------------------------------------------------- //
  const modal = document.getElementById("newCaseModal");
  const $ = (id) => document.getElementById(id);
  let _optionsLoaded = false;
  let _editingCaseId = null;

  const fillSelect = (el, items, withBlank) => {
    el.innerHTML = (withBlank ? '<option value="">—</option>' : "") +
      items.map(o => `<option>${o}</option>`).join("");
  };

  async function ensureOptions() {
    if (_optionsLoaded) return;
    try {
      const o = await LEXORA.api("/api/cases/intake-options");
      fillSelect($("ncPractice"), o.practice_areas, true);
      fillSelect($("ncType"), o.case_types, true);
      fillSelect($("ncJuris"), o.jurisdictions, true);
      fillSelect($("ncStatusSel"), o.statuses, false);
      fillSelect($("ncPriority"), o.priorities, false);
      $("ncStatusSel").value = "Open";
      $("ncPriority").value = "Medium";
      _optionsLoaded = true;
    } catch (e) { LEXORA.toast("Could not load intake options"); }
  }

  function resetForm() {
    ["ncTitle","ncClient","ncCourt","ncJudge","ncOpposing","ncFiled",
     "ncValue","ncSummary","ncPasteText","ncApiUrl"].forEach(id => {
      const el = $(id); if (el) el.value = "";
    });
    if (_optionsLoaded) {
      ["ncPractice","ncType","ncJuris"].forEach(id => $(id).value = "");
      $("ncStatusSel").value = "Open";
      $("ncPriority").value = "Medium";
    }
    $("ncFile").value = "";
    $("ncFileName").textContent = "";
    setStatus("", "");
    switchMode("manual");
    setEditMode(false);
  }

  function setStatus(msg, kind) {
    const el = $("ncStatus");
    if (!msg) { el.classList.add("hidden"); el.textContent = ""; return; }
    el.className = "intake-status " + (kind || "");
    el.textContent = msg;
  }

  function switchMode(mode) {
    document.querySelectorAll(".intake-mode").forEach(b =>
      b.classList.toggle("active", b.dataset.mode === mode));
    $("ncSourceUpload").hidden = mode !== "upload";
    $("ncSourcePaste").hidden = mode !== "paste";
    $("ncSourceApi").hidden = mode !== "api";
  }

  function setEditMode(enabled, caseNumber = "") {
    if (!enabled) _editingCaseId = null;
    $("ncModalTitle").textContent = enabled ? `Edit Matter ${caseNumber}` : "New Matter Intake";
    $("ncModalSubhead").textContent = enabled
      ? "Update matter details and save changes"
      : "Matter # auto-assigned on save";
    $("ncSave").textContent = enabled ? "Save changes" : "Save matter";
    document.querySelectorAll(".intake-mode").forEach((b) => {
      b.disabled = enabled;
      b.classList.toggle("hidden", enabled);
    });
    if (enabled) switchMode("manual");
  }

  function applyFields(f) {
    if (!f) return;
    const set = (id, v) => { if (v != null && v !== "") $(id).value = v; };
    set("ncTitle", f.title);
    set("ncClient", f.client_name);
    set("ncCourt", f.court);
    set("ncJudge", f.judge);
    set("ncOpposing", f.opposing_counsel);
    set("ncSummary", f.summary);
    set("ncValue", f.estimated_value);
    if (f.filed_date) set("ncFiled", String(f.filed_date).slice(0, 10));
    const setSel = (id, v) => {
      if (!v) return; const el = $(id);
      const opt = [...el.options].find(o => o.value === v);
      if (opt) el.value = v;
    };
    setSel("ncPractice", f.practice_area);
    setSel("ncType", f.case_type);
    setSel("ncJuris", f.jurisdiction);
    setSel("ncPriority", f.priority);
  }

  async function runExtract(formData, btn) {
    const orig = btn.textContent;
    btn.disabled = true; btn.textContent = "Extracting…";
    setStatus("AI is reading the source and filling the form…", "working");
    try {
      const res = await fetch("/api/cases/extract", {
        method: "POST", body: formData, credentials: "same-origin",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      applyFields(data.fields);
      const n = Object.keys(data.fields || {}).length;
      if (n) {
        setStatus(`✓ Pre-filled ${n} field${n === 1 ? "" : "s"} from ${data.source}. Review and Save.`, "ok");
        switchMode("manual");
      } else {
        setStatus("No fields could be extracted — please enter manually.", "warn");
      }
    } catch (e) {
      setStatus("Extraction failed: " + e.message, "error");
    } finally {
      btn.disabled = false; btn.textContent = orig;
    }
  }

  function openCreateModal() {
    ensureOptions().then(() => {
      _editingCaseId = null;
      resetForm();
      modal.classList.remove("hidden");
    });
  }

  function openEditModal(c) {
    ensureOptions().then(() => {
      resetForm();
      _editingCaseId = c.id;
      setEditMode(true, c.case_number || "");
      applyFields(c);
      modal.classList.remove("hidden");
    });
  }
  function closeModal() { modal.classList.add("hidden"); }

  $("newCaseBtn")?.addEventListener("click", openCreateModal);
  $("ncClose")?.addEventListener("click", closeModal);
  $("ncCancel")?.addEventListener("click", closeModal);
  editBtn?.addEventListener("click", () => {
    if (!canEditMatters()) return;
    if (!_detailCase) return;
    openEditModal(_detailCase);
  });
  modal?.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });

  document.querySelectorAll(".intake-mode").forEach(b =>
    b.addEventListener("click", () => switchMode(b.dataset.mode)));

  // Upload source
  $("ncBrowse")?.addEventListener("click", () => $("ncFile").click());
  $("ncDrop")?.addEventListener("click", (e) => {
    if (e.target.id !== "ncBrowse") $("ncFile").click();
  });
  $("ncFile")?.addEventListener("change", () => {
    const f = $("ncFile").files[0];
    $("ncFileName").textContent = f ? `Selected: ${f.name}` : "";
  });
  ["dragover","dragenter"].forEach(ev => $("ncDrop")?.addEventListener(ev, (e) => {
    e.preventDefault(); $("ncDrop").classList.add("drag");
  }));
  ["dragleave","drop"].forEach(ev => $("ncDrop")?.addEventListener(ev, (e) => {
    e.preventDefault(); $("ncDrop").classList.remove("drag");
  }));
  $("ncDrop")?.addEventListener("drop", (e) => {
    const f = e.dataTransfer.files[0];
    if (f) { $("ncFile").files = e.dataTransfer.files;
             $("ncFileName").textContent = `Selected: ${f.name}`; }
  });

  $("ncExtractFile")?.addEventListener("click", () => {
    const f = $("ncFile").files[0];
    if (!f) { setStatus("Choose a file first.", "warn"); return; }
    const fd = new FormData(); fd.append("file", f);
    runExtract(fd, $("ncExtractFile"));
  });
  $("ncExtractText")?.addEventListener("click", () => {
    const t = $("ncPasteText").value.trim();
    if (!t) { setStatus("Paste some text first.", "warn"); return; }
    const fd = new FormData(); fd.append("text", t);
    runExtract(fd, $("ncExtractText"));
  });
  $("ncExtractApi")?.addEventListener("click", () => {
    const u = $("ncApiUrl").value.trim();
    if (!u) { setStatus("Enter a URL first.", "warn"); return; }
    const fd = new FormData(); fd.append("source_url", u);
    runExtract(fd, $("ncExtractApi"));
  });

  // Save
  $("ncForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const title = $("ncTitle").value.trim();
    if (!title) { setStatus("Matter title is required.", "warn"); return; }
    const payload = {
      title,
      client_name: $("ncClient").value.trim() || null,
      practice_area: $("ncPractice").value || null,
      case_type: $("ncType").value || null,
      status: $("ncStatusSel").value || "Open",
      priority: $("ncPriority").value || "Medium",
      jurisdiction: $("ncJuris").value || null,
      court: $("ncCourt").value.trim() || null,
      judge: $("ncJudge").value.trim() || null,
      opposing_counsel: $("ncOpposing").value.trim() || null,
      filed_date: $("ncFiled").value || null,
      estimated_value: $("ncValue").value ? parseFloat($("ncValue").value) : null,
      summary: $("ncSummary").value.trim() || null,
    };
    const btn = $("ncSave");
    const isEdit = _editingCaseId != null;
    const saveLabel = isEdit ? "Save changes" : "Save matter";
    btn.disabled = true; btn.textContent = "Saving…";
    try {
      const c = await LEXORA.api(isEdit ? `/api/cases/${_editingCaseId}` : "/api/cases", {
        method: isEdit ? "PUT" : "POST", body: JSON.stringify(payload),
        headers: { "Content-Type": "application/json" },
      });
      LEXORA.toast(isEdit
        ? `Matter ${c.case_number} updated`
        : `Matter ${c.case_number} created`);
      closeModal();
      await load();
      await showDetail(c.id);
    } catch (err) {
      setStatus("Save failed: " + err.message, "error");
    } finally {
      btn.disabled = false; btn.textContent = saveLabel;
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.classList.contains("hidden")) closeModal();
  });

  window.addEventListener("lexora:view", (e) => {
    if (e.detail.view === "cases") {
      syncEditVisibility();
      if (detail.classList.contains("hidden")) {
        listCard?.classList.remove("hidden");
        casesView?.classList.remove("detail-open");
      }
      load();
    }
  });

  window.addEventListener("lexora:ready", syncEditVisibility);
})();
