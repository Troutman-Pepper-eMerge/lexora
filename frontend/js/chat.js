/* Chat view: agent + tool catalog. */
(function () {
  const log = document.getElementById("chatLog");
  const input = document.getElementById("chatInput");
  const sendBtn = document.getElementById("chatSend");
  const toolList = document.getElementById("toolList");
  const history = [];

  async function loadTools() {
    try {
      const { tools } = await LEXORA.api("/api/chat/tools");
      toolList.innerHTML = tools.map(t =>
        `<div class="tool"><b>${t.name}</b><br><span class="muted small">${t.description}</span></div>`
      ).join("");
    } catch {}
  }

  function append(role, content, trace) {
    const el = document.createElement("div");
    el.className = `msg ${role}`;
    el.innerHTML = renderMarkdownLite(content);
    if (trace && trace.length) {
      const callsOnly = trace.filter(t => t.args !== undefined);
      if (callsOnly.length) {
        const tlist = callsOnly.map(t => `<code>${t.tool}</code>`).join(" → ");
        const t = document.createElement("div");
        t.className = "trace"; t.innerHTML = `🛠 ${tlist}`;
        el.appendChild(t);
      }
    }
    log.appendChild(el); log.scrollTop = log.scrollHeight;
    return el;
  }

  function escape(s) {
    return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
  }

  function inline(s) {
    // bold, code, italic, then bold key (Foo:) -> gradient bold
    s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
         .replace(/`([^`]+)`/g, "<code>$1</code>")
         .replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "<em>$1</em>");
    // Highlight "Key:" at the start of a bullet line (after escape)
    s = s.replace(/^([A-Z][\w &/-]{1,40}):(\s)/,
                  '<span class="md-key">$1</span>:$2');
    return s;
  }

  function renderMarkdownLite(src) {
    if (!src) return "";
    const text = escape(src.replace(/\r\n/g, "\n"));
    const lines = text.split("\n");
    const out = [];
    let listType = null;   // 'ul' | 'sub' | null
    const closeList = () => {
      if (listType) { out.push(`</${listType === "sub" ? "ul" : "ul"}>`); listType = null; }
    };

    for (let raw of lines) {
      const line = raw.replace(/\s+$/,"");
      if (!line.trim()) { closeList(); continue; }

      // Headings (## Heading or **Heading** on its own line)
      const h2 = line.match(/^##\s+(.+)$/);
      const boldOnly = line.match(/^\*\*(.+)\*\*:?$/);
      if (h2 || boldOnly) {
        closeList();
        const title = inline(h2 ? h2[1] : boldOnly[1]);
        out.push(`<h4 class="md-h">${title}</h4>`);
        continue;
      }

      // Sub-bullet (indented "- " or "  - ")
      const sub = line.match(/^\s{2,}-\s+(.+)$/);
      if (sub) {
        if (listType !== "sub") { closeList(); out.push(`<ul class="md-list sub">`); listType = "sub"; }
        out.push(`<li>${inline(sub[1])}</li>`);
        continue;
      }

      // Top bullet ("- " or "• " or "* ")
      const bullet = line.match(/^[-*•]\s+(.+)$/);
      if (bullet) {
        if (listType !== "ul") { closeList(); out.push(`<ul class="md-list">`); listType = "ul"; }
        out.push(`<li>${inline(bullet[1])}</li>`);
        continue;
      }

      // Plain paragraph
      closeList();
      out.push(`<p class="md-p">${inline(line)}</p>`);
    }
    closeList();
    return out.join("");
  }

  async function send() {
    const msg = input.value.trim();
    if (!msg) return;
    input.value = "";
    append("user", msg);
    history.push({ role: "user", content: msg });

    const thinking = append("assistant", "▌ thinking…");
    sendBtn.disabled = true;
    try {
      const r = await LEXORA.api("/api/chat", {
        method: "POST",
        body: JSON.stringify({ message: msg, history: history.slice(0, -1) }),
      });
      thinking.remove();
      append("assistant", r.answer || "(no response)", r.trace);
      history.push({ role: "assistant", content: r.answer || "" });
    } catch (e) {
      thinking.remove();
      append("assistant", `⚠️ ${e.message}`);
    } finally { sendBtn.disabled = false; input.focus(); }
  }

  sendBtn.addEventListener("click", send);
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });

  document.querySelectorAll(".suggest-pill").forEach(btn => {
    btn.addEventListener("click", () => {
      input.value = btn.textContent.trim();
      input.focus();
      // Move caret to end
      input.setSelectionRange(input.value.length, input.value.length);
    });
  });

  window.addEventListener("lexora:view", (e) => {
    if (e.detail.view === "chat") loadTools();
  });
})();
