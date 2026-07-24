/* ╔══════════════════════════════════════════════════════════════════╗
   ║  LEXORA · PITCH DECK ENGINE                                        ║
   ║  Flat, interactive slides driven by GSAP: staggered entrances,    ║
   ║  animated counters, a looping workflow beam, cursor-glow cards,   ║
   ║  detail popups, and tiles that jump into the live product.        ║
   ║  Degrades gracefully without GSAP.                                ║
   ╚══════════════════════════════════════════════════════════════════╝ */
(function () {
  "use strict";

  var GS = window.gsap || null;
  var stage = document.getElementById("pdStage");
  if (!stage) return;

  var deck = document.getElementById("pdDeck");
  var slides = Array.prototype.slice.call(deck.querySelectorAll(".pd-slide"));
  var dotsWrap = document.getElementById("pdDots");
  var prevBtn = document.getElementById("pdPrev");
  var nextBtn = document.getElementById("pdNext");
  var counter = document.getElementById("pdCounter");
  var progress = document.getElementById("pdProgress");
  var total = slides.length;
  var current = 0;
  var flowTL = null;
  var ambientStarted = false;

  /* ── Dots ── */
  var dots = slides.map(function (_, i) {
    var b = document.createElement("button");
    b.setAttribute("aria-label", "Slide " + (i + 1));
    if (i === 0) b.classList.add("active");
    b.addEventListener("click", function () { goTo(i); });
    if (dotsWrap) dotsWrap.appendChild(b);
    return b;
  });

  /* ── Animated counters ── */
  function fmt(el, value) {
    var dec = parseInt(el.getAttribute("data-decimals") || "0", 10);
    var prefix = el.getAttribute("data-prefix") || "";
    var suffix = el.getAttribute("data-suffix") || "";
    var n = dec > 0 ? value.toFixed(dec) : Math.round(value).toLocaleString("en-US");
    return prefix + n + suffix;
  }
  function runCounters(slide) {
    slide.querySelectorAll("[data-count]").forEach(function (el) {
      var target = parseFloat(el.getAttribute("data-count"));
      if (isNaN(target)) return;
      if (GS) {
        var o = { v: 0 };
        GS.killTweensOf(o);
        GS.to(o, {
          v: target, duration: 1.3, ease: "power2.out",
          onUpdate: function () { el.textContent = fmt(el, o.v); },
          onComplete: function () { el.textContent = fmt(el, target); }
        });
      } else {
        el.textContent = fmt(el, target);
      }
    });
  }

  /* ── Workflow pipeline: looping beam + sequential node glow ── */
  function stopFlow() {
    if (flowTL) { flowTL.kill(); flowTL = null; }
    stage.querySelectorAll(".pd-stage-node.lit").forEach(function (n) { n.classList.remove("lit"); });
  }
  function startFlow(slide) {
    var flow = slide.querySelector(".pd-flow");
    if (!flow) return;
    var nodes = Array.prototype.slice.call(flow.querySelectorAll(".pd-stage-node"));
    var beam = flow.querySelector(".pd-flow-beam");
    if (!GS) { nodes.forEach(function (n) { n.classList.add("lit"); }); return; }

    GS.fromTo(nodes,
      { opacity: 0, y: 26, scale: 0.92 },
      { opacity: 1, y: 0, scale: 1, duration: .55, stagger: .12, ease: "back.out(1.6)", overwrite: true });

    var DUR = 3.6;
    flowTL = GS.timeline({ repeat: -1, delay: .5 });
    if (beam) {
      flowTL.fromTo(beam, { left: "-12%", opacity: 0 },
        { left: "100%", opacity: 1, duration: DUR, ease: "none" }, 0);
      flowTL.to(beam, { opacity: 0, duration: .3 }, DUR - .3);
    }
    nodes.forEach(function (n, i) {
      var t0 = (i / nodes.length) * DUR;
      flowTL.call(function () { n.classList.add("lit"); }, null, t0);
      flowTL.call(function () { n.classList.remove("lit"); }, null, t0 + (DUR / nodes.length) * 0.9);
    });
  }

  /* ── Slide entrance ── */
  function animateIn(slide) {
    runCounters(slide);
    startFlow(slide);
    if (!GS) return;
    var items = slide.querySelectorAll("[data-pd-anim]");
    GS.killTweensOf(items);
    GS.fromTo(items,
      { opacity: 0, y: 26 },
      { opacity: 1, y: 0, duration: .6, stagger: .07, ease: "power3.out", overwrite: true });
  }

  /* ── Navigation ── */
  function goTo(idx) {
    idx = Math.max(0, Math.min(total - 1, idx));
    stopFlow();
    if (modal && modal.classList.contains("open")) closeModal();
    slides.forEach(function (s, i) { s.classList.toggle("active", i === idx); });
    dots.forEach(function (d, i) { d.classList.toggle("active", i === idx); });
    current = idx;
    if (prevBtn) prevBtn.disabled = idx === 0;
    if (nextBtn) nextBtn.disabled = idx === total - 1;
    if (counter) counter.textContent = pad(idx + 1) + " / " + pad(total);
    if (progress) progress.style.width = ((idx + 1) / total * 100) + "%";
    animateIn(slides[idx]);
  }
  function pad(n) { return n < 10 ? "0" + n : String(n); }
  function next() { goTo(current + 1); }
  function prev() { goTo(current - 1); }

  if (nextBtn) nextBtn.addEventListener("click", next);
  if (prevBtn) prevBtn.addEventListener("click", prev);

  /* ── Keyboard (only while Pitch tab is active) ── */
  function active() {
    var v = document.querySelector('.view[data-view="pitch"]');
    return v && v.classList.contains("active");
  }
  document.addEventListener("keydown", function (e) {
    if (!active()) return;
    var t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) return;
    if (modal && modal.classList.contains("open")) {
      if (e.key === "Escape") { e.preventDefault(); closeModal(); }
      return;
    }
    if (e.key === "ArrowRight" || e.key === "PageDown" || e.key === " ") { e.preventDefault(); next(); }
    else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); prev(); }
    else if (e.key === "Home") { e.preventDefault(); goTo(0); }
    else if (e.key === "End") { e.preventDefault(); goTo(total - 1); }
  });

  /* ── Cursor-tracking glow on cards ── */
  stage.querySelectorAll(".pd-card").forEach(function (card) {
    card.addEventListener("mousemove", function (e) {
      var r = card.getBoundingClientRect();
      card.style.setProperty("--mx", (e.clientX - r.left) + "px");
      card.style.setProperty("--my", (e.clientY - r.top) + "px");
    });
  });

  /* ── Tiles / CTA cards jump into the live product ── */
  stage.querySelectorAll("[data-goto-view]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var view = btn.getAttribute("data-goto-view");
      if (window.LEXORA && typeof window.LEXORA.switchTo === "function") {
        window.LEXORA.switchTo(view);
      } else {
        var tab = document.querySelector('.tab[data-view="' + view + '"]');
        if (tab) tab.click();
      }
    });
  });

  /* ══════════════════════════════════════════════════════════════
     Interactive detail popups (capabilities & challenges)
     ══════════════════════════════════════════════════════════════ */
  var CAPS = {
    intake: {
      ico: "🧾", kicker: "Capability", title: "Intelligent intake",
      html:
        "<p>Open a new matter from a raw complaint, intake email, spreadsheet, or an intake API — no manual keying.</p>" +
        '<div class="pd-mb-label">What it does</div>' +
        "<ul>" +
        "<li>Parses <strong>PDF · DOCX · PPTX · XLSX · JSON · TXT</strong> and extracts every matter field.</li>" +
        "<li>Auto-fills title, client, practice area, jurisdiction, court, judge, opposing counsel &amp; value.</li>" +
        "<li>Snaps free text to your controlled vocabularies, then lets you review before saving.</li>" +
        "</ul>" +
        '<span class="pd-mb-badge">✓ Working in this product</span>'
    },
    rag: {
      ico: "📚", kicker: "Capability", title: "Document RAG",
      html:
        "<p>Ask plain-English questions across your filings and get answers grounded in your own text.</p>" +
        '<div class="pd-mb-label">What it does</div>' +
        "<ul>" +
        "<li>Chunks and embeds every uploaded document into a private vector index.</li>" +
        "<li>Retrieves the most relevant passages and answers with <strong>page-level citations</strong>.</li>" +
        "<li>Never invents — if it isn't in your documents, it says so.</li>" +
        "</ul>" +
        '<span class="pd-mb-badge">✓ Working in this product</span>'
    },
    agent: {
      ico: "⚖️", kicker: "Capability", title: "Agent copilot",
      html:
        "<p>A tool-calling agent reasons across your whole portfolio, choosing the right tool for each question.</p>" +
        '<div class="pd-mb-label">What it does</div>' +
        "<ul>" +
        "<li>Orchestrates multi-step legal workflows with a LangGraph agent.</li>" +
        "<li>Calls portfolio analytics, document search &amp; matter tools on demand.</li>" +
        "<li>Streams its reasoning and cites every source it used.</li>" +
        "</ul>" +
        '<span class="pd-mb-badge">✓ Working in this product</span>'
    },
    predictor: {
      ico: "🔮", kicker: "Capability", title: "Outcome predictor",
      html:
        "<p>Transparent settlement and duration estimates for any matter — for planning, not as legal advice.</p>" +
        '<div class="pd-mb-label">What it does</div>' +
        "<ul>" +
        "<li>Estimates settlement likelihood, expected value &amp; duration with a statistical model.</li>" +
        "<li>Narrates a strategic assessment and lists the driving factors.</li>" +
        "<li>Shows a full evidence trail — every estimate is explainable.</li>" +
        "</ul>" +
        '<span class="pd-mb-badge">✓ Working in this product</span>'
    }
  };

  var SOLVE = {
    scattered: {
      ico: "🗂️", kicker: "Fits how you work", title: "Scattered tools",
      now: "Matter data lives across email, spreadsheets, a DMS, and a dozen point tools — nothing is in one place.",
      wit: "LEXORA unifies intake, matters, documents, analytics, and calendaring in one governed workspace, so every stage of the lifecycle shares the same source of truth.",
      live: true
    },
    triage: {
      ico: "📄", kicker: "Fits how you work", title: "Manual review",
      now: "Associates read every page by hand to find the facts that matter — slow, costly, and easy to miss.",
      wit: "Document RAG indexes each filing and answers questions with page-level citations, so review becomes ask-and-verify instead of read-everything.",
      live: true
    },
    risk: {
      ico: "🎯", kicker: "Fits how you work", title: "Blind on risk",
      now: "Leadership has no live view of exposure — settlement risk and value sit in people's heads.",
      wit: "The dashboard and outcome predictor surface portfolio health, at-risk matters, and transparent settlement estimates with an evidence trail.",
      live: true
    },
    deadlines: {
      ico: "📅", kicker: "Fits how you work", title: "Deadline chaos",
      now: "Court dates and deadlines are tracked in scattered calendars — a missed date is a real liability.",
      wit: "The calendar centralizes court dates, deadlines, and appointments per matter, with notifications so nothing slips.",
      live: true
    },
    dms: {
      ico: "🔌", kicker: "Fits how you work", title: "DMS silos",
      now: "Documents are locked in a separate system, so the people making the call can't easily question them.",
      wit: "Upload straight into a matter — or connect your source system — and the same documents become live, queryable knowledge for the agent.",
      live: false
    }
  };

  var modal = document.getElementById("pdModal");
  var mIco = document.getElementById("pdModalIco");
  var mKicker = document.getElementById("pdModalKicker");
  var mTitle = document.getElementById("pdModalTitle");
  var mBody = document.getElementById("pdModalBody");
  var mDialog = modal ? modal.querySelector(".pd-modal-dialog") : null;

  function openCapability(d) {
    if (!d) return;
    mIco.textContent = d.ico; mKicker.textContent = d.kicker; mTitle.textContent = d.title;
    mBody.innerHTML = d.html;
    showModal();
  }
  function openChallenge(d) {
    if (!d) return;
    mIco.textContent = d.ico; mKicker.textContent = d.kicker; mTitle.textContent = d.title;
    mBody.innerHTML =
      '<div class="pd-mb-label now">Today</div><p>' + d.now + "</p>" +
      '<div class="pd-mb-label with">With LEXORA</div><p>' + d.wit + "</p>" +
      '<span class="pd-mb-badge' + (d.live ? "" : " build") + '">' +
      (d.live ? "✓ Working in this product" : "◆ New capability we would build") + "</span>";
    showModal();
  }
  function showModal() {
    if (!modal) return;
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
    if (GS && mDialog) {
      GS.fromTo(mDialog, { opacity: 0, y: 24, scale: 0.95 },
        { opacity: 1, y: 0, scale: 1, duration: .4, ease: "back.out(1.5)", overwrite: true });
      GS.fromTo(mBody.children, { opacity: 0, y: 12 },
        { opacity: 1, y: 0, duration: .38, stagger: .06, delay: .1, ease: "power2.out", overwrite: true });
    }
  }
  function closeModal() {
    if (!modal) return;
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
  }

  stage.querySelectorAll("[data-cap]").forEach(function (c) {
    c.addEventListener("click", function () { openCapability(CAPS[c.getAttribute("data-cap")]); });
  });
  stage.querySelectorAll("[data-solve]").forEach(function (c) {
    c.addEventListener("click", function () { openChallenge(SOLVE[c.getAttribute("data-solve")]); });
  });
  if (modal) {
    modal.querySelectorAll("[data-pd-close]").forEach(function (el) {
      el.addEventListener("click", closeModal);
    });
  }

  /* ── Ambient motes ── */
  function startAmbient() {
    if (ambientStarted) return;
    ambientStarted = true;
    var host = document.getElementById("pdMotes");
    if (!host) return;
    for (var i = 0; i < 22; i++) {
      var m = document.createElement("span");
      m.className = "pd-mote";
      m.style.left = (Math.random() * 100) + "%";
      m.style.top = (Math.random() * 100) + "%";
      host.appendChild(m);
      if (GS) {
        GS.to(m, {
          x: (Math.random() * 120 - 60), y: (Math.random() * 120 - 60),
          opacity: Math.random() * .4 + .15,
          duration: Math.random() * 6 + 5, ease: "sine.inOut",
          yoyo: true, repeat: -1, delay: Math.random() * 4
        });
      }
    }
  }

  /* ── Activate when the Pitch tab is shown ── */
  window.addEventListener("lexora:view", function (ev) {
    if (ev.detail && ev.detail.view === "pitch") {
      startAmbient();
      animateIn(slides[current]);
    } else {
      stopFlow();
    }
  });

  /* First paint (in case Pitch is the initial view). */
  goTo(0);
  if (active()) startAmbient();
})();
