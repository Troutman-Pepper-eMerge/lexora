/* Documents view: drag-drop upload + table. */
(function () {
  const dz = document.getElementById("dropzone");
  const fileInput = document.getElementById("fileInput");
  const browseBtn = document.getElementById("browseBtn");
  const caseSel = document.getElementById("uploadCaseId");
  const progress = document.getElementById("uploadProgress");
  const tbody = document.querySelector("#docTable tbody");

  async function loadCases() {
    try {
      const { cases } = await LEXORA.api("/api/cases?limit=200");
      caseSel.innerHTML = '<option value="">No matter (general)</option>' +
        cases.map(c => `<option value="${c.id}">${c.case_number} — ${c.title}</option>`).join("");
    } catch {}
  }

  async function loadDocs() {
    try {
      const { documents } = await LEXORA.api("/api/documents?limit=100");
      tbody.innerHTML = documents.map(d => `<tr>
        <td>${d.filename}</td>
        <td>${d.case_id ?? '—'}</td>
        <td>${d.file_type || ''}</td>
        <td>${d.pages || '—'}</td>
        <td><span class="pill">${d.category || '—'}</span></td>
        <td>${d.indexed ? '✓' : '⏳'}</td>
        <td class="muted" style="max-width:380px">${(d.summary||'').slice(0,180)}</td>
        <td>${d.case_id ? `<button class="btn-ghost" data-id="${d.id}">Re-analyze</button>` : ''}</td>
      </tr>`).join("") || `<tr><td colspan="8" class="muted">No documents uploaded yet.</td></tr>`;
      tbody.querySelectorAll("button[data-id]").forEach(b => {
        b.addEventListener("click", async (e) => {
          e.stopPropagation();
          b.disabled = true; b.textContent = "Analyzing…";
          try {
            await LEXORA.api(`/api/documents/${b.dataset.id}/analyze`, { method: "POST" });
            LEXORA.toast("Document re-analyzed");
            loadDocs();
          } catch (err) { LEXORA.toast(err.message); b.disabled = false; b.textContent = "Re-analyze"; }
        });
      });
    } catch (e) { LEXORA.toast("Doc load failed: " + e.message); }
  }

  async function uploadFile(file) {
    const id = `up-${Date.now()}`;
    const item = document.createElement("div");
    item.className = "item"; item.id = id;
    item.innerHTML = `<span>📄 ${file.name}</span><span class="muted">uploading…</span>`;
    progress.prepend(item);

    const fd = new FormData();
    fd.append("file", file);
    if (caseSel.value) fd.append("case_id", caseSel.value);

    try {
      const r = await fetch("/api/documents/upload", {
        method: "POST", body: fd, credentials: "include",
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        throw new Error(j.detail || r.statusText);
      }
      const data = await r.json();
      item.querySelector(".muted").textContent = `queued · processing in background (#${data.document_id})`;
      LEXORA.toast(`Uploaded ${file.name}; processing…`);
      setTimeout(loadDocs, 1500);
      setTimeout(loadDocs, 6000);
      setTimeout(() => item.remove(), 12000);
    } catch (e) {
      item.querySelector(".muted").textContent = `failed: ${e.message}`;
    }
  }

  // Drag & drop
  ["dragenter","dragover"].forEach(ev => dz.addEventListener(ev, e => {
    e.preventDefault(); dz.classList.add("drag");
  }));
  ["dragleave","drop"].forEach(ev => dz.addEventListener(ev, e => {
    e.preventDefault(); dz.classList.remove("drag");
  }));
  dz.addEventListener("drop", e => {
    [...e.dataTransfer.files].forEach(uploadFile);
  });
  browseBtn.addEventListener("click", e => { e.stopPropagation(); fileInput.click(); });
  caseSel.addEventListener("click", e => e.stopPropagation());
  caseSel.addEventListener("change", e => e.stopPropagation());
  fileInput.addEventListener("change", () => {
    [...fileInput.files].forEach(uploadFile);
    fileInput.value = "";
  });

  window.addEventListener("lexora:view", (e) => {
    if (e.detail.view === "documents") { loadCases(); loadDocs(); }
  });
})();
