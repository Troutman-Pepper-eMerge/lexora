/* Notification Center: live feed + notification rules management. */
(function () {
  const feed     = document.getElementById("ntFeed");
  const kpis     = document.getElementById("ntKpis");
  const countEl  = document.getElementById("ntCount");
  const selChan  = document.getElementById("ntChannel");
  const selStat  = document.getElementById("ntStatus");
  const refresh  = document.getElementById("ntRefresh");

  // Notification rule modal elements
  const newNotifyModal = document.getElementById("newNotifyModal");
  const newNotifyForm  = document.getElementById("newNotifyForm");
  const nnRuleName     = document.getElementById("nnRuleName");
  const nnTrigger      = document.getElementById("nnTrigger");
  const nnChannel      = document.getElementById("nnChannel");
  const nnScope        = document.getElementById("nnScope");
  const nnMatters      = document.getElementById("nnMatters");
  const nnMessageType  = document.getElementById("nnMessageType");
  const nnTemplate     = document.getElementById("nnTemplate");
  const nnReportPath   = document.getElementById("nnReportPath");
  const nnCondStatus   = document.getElementById("nnCondStatus");
  const nnCondPriority = document.getElementById("nnCondPriority");
  const nnCondPractice = document.getElementById("nnCondPractice");

  // Conditional sections
  const nnScopeSection         = document.getElementById("nnScopeSection");
  const nnSpecificMatters      = document.getElementById("nnSpecificMatters");
  const nnConditionsSection    = document.getElementById("nnConditionsSection");
  const nnMatterCreatedFilter  = document.getElementById("nnMatterCreatedFilter");
  const nnThresholdSection     = document.getElementById("nnThresholdSection");
  const nnCustomMessage        = document.getElementById("nnCustomMessage");
  const nnReportLink           = document.getElementById("nnReportLink");

  let _all = [];
  let _allMatters = [];

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
    return (s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
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
          ${n.case_id ? `<span class="nt-dot">·</span><span class="nt-case">Matter #${n.case_id}</span>` : ""}
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

  // --- Notification Rules Modal ---

  async function loadMatters() {
    try {
      const { cases } = await LEXORA.api("/api/cases");
      _allMatters = cases || [];
      nnMatters.innerHTML = cases.map(c =>
        `<option value="${c.id}">${c.case_number} — ${c.title}</option>`
      ).join("");

      // Populate practice area dropdown
      const practices = [...new Set(cases.map(c => c.practice_area).filter(Boolean))].sort();
      nnCondPractice.innerHTML = '<option value="">Any</option>' +
        practices.map(p => `<option value="${p}">${p}</option>`).join("");
    } catch (e) {
      console.error("Failed to load matters:", e);
    }
  }

  function updateConditionalSections() {
    const trigger = nnTrigger.value;
    const scope = nnScope.value;
    const messageType = nnMessageType.value;

    // Show/hide scope section based on trigger
    // "matter_assigned" is about FUTURE assignments, so no need to select matters
    // Only show scope for triggers that apply to existing/ongoing matters
    const scopeNeededTriggers = ["status_changed", "document_uploaded"];
    if (scopeNeededTriggers.includes(trigger)) {
      nnScopeSection.classList.remove("hidden");
      nnConditionsSection.classList.remove("hidden");
    } else {
      nnScopeSection.classList.add("hidden");
      // Still show conditions for matter_assigned (e.g., only High priority assignments)
      if (trigger === "matter_assigned" || trigger === "matter_created") {
        nnConditionsSection.classList.remove("hidden");
      } else {
        nnConditionsSection.classList.add("hidden");
      }
    }

    // Show threshold section for analytics trigger
    if (trigger === "analytics_threshold") {
      nnThresholdSection.classList.remove("hidden");
    } else {
      nnThresholdSection.classList.add("hidden");
    }

    // Show matter created filter
    if (trigger === "matter_created") {
      nnMatterCreatedFilter.classList.remove("hidden");
    } else {
      nnMatterCreatedFilter.classList.add("hidden");
    }

    // Show/hide specific matters multi-select
    if (scope === "specific_matters") {
      nnSpecificMatters.classList.remove("hidden");
    } else {
      nnSpecificMatters.classList.add("hidden");
    }

    // Show/hide message configuration
    if (messageType === "custom_message") {
      nnCustomMessage.classList.remove("hidden");
      nnReportLink.classList.add("hidden");
    } else if (messageType === "report_link") {
      nnCustomMessage.classList.add("hidden");
      nnReportLink.classList.remove("hidden");
    } else {
      nnCustomMessage.classList.add("hidden");
      nnReportLink.classList.add("hidden");
    }

    // Hide "all_matters" scope unless user is Admin
    const role = window.LEXORA_PRINCIPAL?.role;
    if (role !== "Admin") {
      const allMattersOption = nnScope.querySelector('option[value="all_matters"]');
      if (allMattersOption) allMattersOption.hidden = true;
    }
  }

  nnTrigger.addEventListener("change", updateConditionalSections);
  nnScope.addEventListener("change", updateConditionalSections);
  nnMessageType.addEventListener("change", updateConditionalSections);

  document.getElementById("newNotifyBtn")?.addEventListener("click", async () => {
    newNotifyForm.reset();
    await loadMatters();
    updateConditionalSections();
    newNotifyModal.classList.remove("hidden");
  });

  document.getElementById("nnClose")?.addEventListener("click", () => {
    newNotifyModal.classList.add("hidden");
  });

  document.getElementById("nnCancel")?.addEventListener("click", () => {
    newNotifyModal.classList.add("hidden");
  });

  newNotifyModal?.addEventListener("click", (e) => {
    if (e.target === newNotifyModal) newNotifyModal.classList.add("hidden");
  });

  newNotifyForm?.addEventListener("submit", async (e) => {
    e.preventDefault();

    // Build trigger conditions
    const trigger_conditions = {};
    const scope = nnScope.value;
    const trigger = nnTrigger.value;

    // Scope handling
    if (scope === "specific_matters") {
      const selected = Array.from(nnMatters.selectedOptions).map(o => parseInt(o.value, 10));
      if (selected.length === 0) {
        LEXORA.toast("Please select at least one matter");
        return;
      }
      trigger_conditions.matter_ids = selected;
    } else if (scope) {
      trigger_conditions.scope = scope;
    }

    // Additional conditions
    if (nnCondStatus.value) trigger_conditions.status = nnCondStatus.value;
    if (nnCondPriority.value) trigger_conditions.priority = nnCondPriority.value;
    if (nnCondPractice.value) trigger_conditions.practice_area = nnCondPractice.value;

    // Analytics threshold configuration
    if (trigger === "analytics_threshold") {
      const metric = document.getElementById("nnMetric").value;
      const operator = document.getElementById("nnOperator").value;
      const thresholdValue = document.getElementById("nnThresholdValue").value;

      if (!thresholdValue) {
        LEXORA.toast("Please specify a threshold value for analytics");
        return;
      }

      trigger_conditions.metric = metric;
      trigger_conditions.operator = operator;
      trigger_conditions.threshold_value = parseFloat(thresholdValue);
    }

    // Matter created filter
    if (trigger === "matter_created") {
      const onlyMyMatters = document.getElementById("nnOnlyMyMatters").checked;
      if (onlyMyMatters) {
        trigger_conditions.only_assigned_to_me = true;
      }
    }

    // Advanced options - time constraints
    const time_constraints = {};
    const businessHours = document.getElementById("nnBusinessHours").checked;
    const weekdaysOnly = document.getElementById("nnWeekdaysOnly").checked;
    if (businessHours) time_constraints.business_hours_only = true;
    if (weekdaysOnly) time_constraints.weekdays_only = true;

    // Advanced options - frequency limits
    const frequency_limit = {};
    const maxPerDay = document.getElementById("nnMaxPerDay").value;
    const digestMode = document.getElementById("nnDigestMode").value;
    if (maxPerDay) frequency_limit.max_per_day = parseInt(maxPerDay, 10);
    if (digestMode) frequency_limit.digest_mode = digestMode;

    const payload = {
      rule_name: nnRuleName.value.trim(),
      trigger_type: trigger,
      trigger_conditions,
      channel: nnChannel.value,
      message_type: nnMessageType.value,
      condition_logic: document.getElementById("nnConditionLogic").value,
    };

    // Only add optional fields if they have values
    if (nnMessageType.value === "custom_message" && nnTemplate.value.trim()) {
      payload.message_template = nnTemplate.value.trim();
    }
    if (nnMessageType.value === "report_link") {
      payload.report_path = nnReportPath.value;
    }
    if (Object.keys(time_constraints).length > 0) {
      payload.time_constraints = time_constraints;
    }
    if (Object.keys(frequency_limit).length > 0) {
      payload.frequency_limit = frequency_limit;
    }

    const btn = document.getElementById("nnSave");
    btn.disabled = true;
    btn.textContent = "Creating...";

    try {
      await LEXORA.api("/api/notification-rules", {
        method: "POST",
        body: JSON.stringify(payload),
        headers: { "Content-Type": "application/json" },
      });
      LEXORA.toast("Notification rule created successfully");
      newNotifyModal.classList.add("hidden");
      // Optionally reload rules list if you add a list view
    } catch (err) {
      LEXORA.toast("Failed to create rule: " + err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Create rule";
    }
  });

  window.addEventListener("lexora:view", (e) => {
    if (e.detail.view === "notifications") load();
  });
})();
