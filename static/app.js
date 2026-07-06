/* StoryBot — frontend logic */
"use strict";

// ── State ──────────────────────────────────────────────────────────────────────
let worlds = [];
let activeWorldId = null;
let stories = [];
let characters = [];
let worldBible = {};

// ── DOM refs ───────────────────────────────────────────────────────────────────
const worldList      = document.getElementById("world-list");
const contentArea    = document.getElementById("content-area");
const emptyState     = document.getElementById("empty-state");
const linkInput      = document.getElementById("link-input");
const modeToggle     = document.getElementById("mode-toggle");
const modeLabelAi    = document.getElementById("mode-label-ai");
const modeLabelTxt   = document.getElementById("mode-label-txt");
const btnProcess     = document.getElementById("btn-process");
const processStatus  = document.getElementById("process-status");

// ── Helpers ────────────────────────────────────────────────────────────────────
const api = async (method, path, body) => {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(`/api${path}`, opts);
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
};

const escHtml = s =>
  String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const setStatus = (msg, type = "inf") => {
  processStatus.className = `mt-2 small status-${type}`;
  processStatus.innerHTML = msg;
  processStatus.classList.remove("d-none");
};

const clearStatus = () => processStatus.classList.add("d-none");

// ── Mode toggle ────────────────────────────────────────────────────────────────
modeToggle.addEventListener("change", () => {
  const isText = modeToggle.checked;
  modeLabelAi.classList.toggle("text-info", !isText);
  modeLabelAi.classList.toggle("text-secondary", isText);
  modeLabelTxt.classList.toggle("text-warning", isText);
  modeLabelTxt.classList.toggle("text-secondary", !isText);
});

// ── Load worlds ────────────────────────────────────────────────────────────────
async function loadWorlds() {
  const { ok, data } = await api("GET", "/worlds");
  if (!ok) return;
  worlds = data;
  renderWorldList();
}

function renderWorldList() {
  worldList.innerHTML = "";
  if (!worlds.length) {
    worldList.innerHTML = `<li class="px-2 text-muted small fst-italic">No worlds yet.</li>`;
    return;
  }
  for (const w of worlds) {
    const li = document.createElement("li");
    li.className = "world-item" + (w.id === activeWorldId ? " active" : "");
    li.innerHTML = `
      <i class="bi bi-globe2 text-warning small me-1"></i>
      <span class="world-name">${escHtml(w.name)}</span>
      <button class="btn btn-outline-danger btn-del-world"
              data-id="${w.id}" title="Delete world">
        <i class="bi bi-trash3"></i>
      </button>`;
    li.addEventListener("click", (e) => {
      if (e.target.closest(".btn-del-world")) return;
      selectWorld(w.id);
    });
    li.querySelector(".btn-del-world").addEventListener("click", () => deleteWorld(w.id));
    worldList.appendChild(li);
  }
}

async function selectWorld(id) {
  activeWorldId = id;
  renderWorldList();
  await Promise.all([loadStories(id), loadCharacters(id), loadBible(id)]);
  renderWorldContent();
}

async function deleteWorld(id) {
  if (!confirm("Delete this world and all its stories?")) return;
  await api("DELETE", `/worlds/${id}`);
  if (activeWorldId === id) {
    activeWorldId = null;
    contentArea.innerHTML = "";
    emptyState.classList.remove("d-none");
  }
  await loadWorlds();
}

// ── Add world ──────────────────────────────────────────────────────────────────
document.getElementById("btn-add-world").addEventListener("click", () => {
  document.getElementById("new-world-name").value = "";
  document.getElementById("new-world-desc").value = "";
  new bootstrap.Modal(document.getElementById("addWorldModal")).show();
});

document.getElementById("btn-create-world").addEventListener("click", async () => {
  const name = document.getElementById("new-world-name").value.trim();
  if (!name) { alert("World name is required."); return; }
  const desc = document.getElementById("new-world-desc").value.trim();
  const { ok, data } = await api("POST", "/worlds", { name, description: desc });
  if (!ok) { alert(data.error || "Failed to create world."); return; }
  bootstrap.Modal.getInstance(document.getElementById("addWorldModal")).hide();
  await loadWorlds();
  selectWorld(data.id);
});

// ── Load world data ────────────────────────────────────────────────────────────
async function loadStories(worldId) {
  const { ok, data } = await api("GET", `/worlds/${worldId}/stories`);
  stories = ok ? data : [];
}

async function loadCharacters(worldId) {
  const { ok, data } = await api("GET", `/worlds/${worldId}/characters`);
  characters = ok ? data : [];
}

async function loadBible(worldId) {
  const { ok, data } = await api("GET", `/worlds/${worldId}/bible`);
  worldBible = ok ? data : {};
}

// ── Render world content ───────────────────────────────────────────────────────
function renderWorldContent() {
  if (!activeWorldId) return;
  const world = worlds.find(w => w.id === activeWorldId) || {};
  emptyState.classList.add("d-none");

  contentArea.innerHTML = `
    <div class="row g-3">
      <!-- Left: stories -->
      <div class="col-lg-7">
        <div class="d-flex justify-content-between align-items-center mb-2">
          <h6 class="text-warning mb-0">
            <i class="bi bi-collection me-1"></i>Stories (${stories.length})
          </h6>
        </div>
        <div id="story-list">
          ${stories.length ? "" :
            `<p class="text-muted small fst-italic">
               No stories yet. Paste a link above and click Process.
             </p>`}
        </div>
      </div>

      <!-- Right: characters + world bible -->
      <div class="col-lg-5">
        <div class="mb-3">
          <h6 class="text-warning mb-2">
            <i class="bi bi-people me-1"></i>Characters (${characters.length})
          </h6>
          <div id="char-list">
            ${characters.length ? "" :
              `<p class="text-muted small fst-italic">No characters identified yet.</p>`}
          </div>
        </div>

        <div>
          <h6 class="text-warning mb-2">
            <i class="bi bi-journal-richtext me-1"></i>World Bible
          </h6>
          <div id="bible-area">
            ${Object.keys(worldBible).length ? "" :
              `<p class="text-muted small fst-italic">
                 No world bible yet — process some stories with AI mode enabled.
               </p>`}
          </div>
        </div>
      </div>
    </div>
  `;

  // Populate stories
  const storyList = document.getElementById("story-list");
  for (const s of stories) {
    storyList.appendChild(buildStoryCard(s));
  }

  // Populate characters
  const charList = document.getElementById("char-list");
  for (const c of characters) {
    const div = document.createElement("div");
    div.className = "char-card mb-2";
    div.innerHTML = `
      <div class="char-name">${escHtml(c.name)}</div>
      <div class="text-muted">${escHtml(c.description || "No description yet.")}</div>
      <div class="text-muted mt-1">
        Appears in ${(c.story_ids || []).length} ${(c.story_ids || []).length === 1 ? 'story' : 'stories'}.
      </div>`;
    charList.appendChild(div);
  }

  // Bible
  const bibleArea = document.getElementById("bible-area");
  if (Object.keys(worldBible).length) {
    bibleArea.appendChild(buildBibleSection(worldBible));
  }
}

function buildStoryCard(s) {
  const div = document.createElement("div");
  div.className = "story-card";
  const typeIcon = s.source_type?.startsWith("discord") ?
    "bi-discord text-indigo" : "bi-chat-dots text-success";
  const date = s.created_at?.slice(0, 10) || "";
  const hasTxt = s.txt_path ? `<span class="badge bg-secondary story-badge ms-1">
    <i class="bi bi-file-text me-1"></i>TXT</span>` : "";
  const hasAi = s.ai_analysis && Object.keys(s.ai_analysis).length &&
    !s.ai_analysis.error ?
    `<span class="badge bg-info bg-opacity-25 text-info story-badge ms-1">
      <i class="bi bi-cpu me-1"></i>AI</span>` : "";

  div.innerHTML = `
    <div class="story-title">
      <i class="bi ${typeIcon} me-1"></i>${escHtml(s.title || "Untitled")}
    </div>
    <div class="story-meta d-flex justify-content-between align-items-center">
      <span>${escHtml(s.source_url?.slice(0, 60))}…</span>
      <span>${date}${hasTxt}${hasAi}</span>
    </div>`;

  div.addEventListener("click", () => openStoryModal(s.id));
  return div;
}

function buildBibleSection(bible) {
  const div = document.createElement("div");
  div.className = "bible-section";

  const overview = bible.overview || "";
  const themes = bible.themes || [];
  const arcs = bible.story_arcs || [];
  const timeline = bible.timeline || [];
  const chars = bible.characters || [];

  div.innerHTML = `
    ${overview ? `<div class="mb-3"><h6>Overview</h6>
      <p class="mb-0">${escHtml(overview)}</p></div>` : ""}
    ${themes.length ? `<div class="mb-3"><h6>Themes</h6>
      ${themes.map(t => `<span class="badge bg-primary bg-opacity-25 text-primary me-1 mb-1">
        ${escHtml(t)}</span>`).join("")}</div>` : ""}
    ${arcs.length ? `<div class="mb-3"><h6>Story Arcs</h6>
      <ul class="mb-0 ps-3">${arcs.map(a =>
        `<li>${escHtml(a)}</li>`).join("")}</ul></div>` : ""}
    ${timeline.length ? `<div class="mb-3"><h6>Timeline</h6>
      <ul class="mb-0 ps-3">${timeline.map(t =>
        `<li>${escHtml(t)}</li>`).join("")}</ul></div>` : ""}
    ${chars.length ? `<div><h6>Characters</h6>
      ${chars.map(c => `<div class="mb-1">
        <span class="fw-semibold text-info">${escHtml(c.name)}</span>
        — ${escHtml(c.description || "")}
      </div>`).join("")}</div>` : ""}
  `;
  return div;
}

// ── Story modal ────────────────────────────────────────────────────────────────
async function openStoryModal(storyId) {
  const { ok, data } = await api("GET", `/stories/${storyId}`);
  if (!ok) { alert("Could not load story."); return; }

  document.getElementById("story-modal-title").textContent =
    data.title || "Untitled Story";

  const body = document.getElementById("story-modal-body");
  const ai = data.ai_analysis || {};
  const hasAi = Object.keys(ai).length && !ai.error && !ai.raw_response;
  const hasAiError = !!(ai.error || ai.raw_response);
  const hasTxt = data.txt_path;

  body.innerHTML = `
    <div class="d-flex gap-2 mb-3 flex-wrap" id="story-action-bar">
      <a id="story-source-link" target="_blank" rel="noopener noreferrer"
         class="btn btn-sm btn-outline-secondary">
        <i class="bi bi-box-arrow-up-right me-1"></i>Open Source
      </a>
      ${hasTxt ? `<span class="btn btn-sm btn-outline-secondary disabled">
        <i class="bi bi-file-text me-1"></i>${escHtml(data.txt_path)}
      </span>` : ""}
      <button class="btn btn-sm btn-outline-danger ms-auto"
              id="story-delete-btn">
        <i class="bi bi-trash3 me-1"></i>Delete
      </button>
    </div>

    ${hasAi ? buildStoryAnalysisHtml(ai) : ""}
    ${hasAiError ? `
      <div class="alert alert-warning py-2 small mb-3">
        <i class="bi bi-exclamation-triangle me-1"></i>
        <strong>AI analysis failed:</strong> ${escHtml(ai.error || "Could not parse AI response.")}
        Check your AI backend settings (Settings → AI Backend).
      </div>` : ""}

    <div class="mt-3">
      <h6 class="text-muted small text-uppercase">Raw Content</h6>
      <pre>${escHtml(data.raw_content)}</pre>
    </div>
  `;

  // Set href via DOM property to prevent attribute injection
  const linkEl = document.getElementById("story-source-link");
  if (linkEl && data.source_url) {
    try {
      const safeUrl = new URL(data.source_url);
      if (safeUrl.protocol === "https:" || safeUrl.protocol === "http:") {
        linkEl.href = safeUrl.href;
      }
    } catch (_) { /* invalid URL — leave href unset */ }
  }

  document.getElementById("story-delete-btn")
    .addEventListener("click", () => deleteStory(storyId));

  new bootstrap.Modal(document.getElementById("storyModal")).show();
}

function buildStoryAnalysisHtml(ai) {
  const chars = (ai.characters || []).map(c => `
    <div class="char-card mb-2">
      <div class="char-name">${escHtml(c.name)}</div>
      <div class="text-muted">${escHtml(c.description || "")}</div>
      ${(c.relationships || []).length ?
        `<div class="mt-1 text-muted small">
          Relationships: ${c.relationships.map(r => escHtml(r)).join(", ")}
        </div>` : ""}
    </div>`).join("");

  const themes = (ai.themes || []).map(t =>
    `<span class="badge bg-primary bg-opacity-25 text-primary me-1 mb-1">${escHtml(t)}</span>`
  ).join("");

  const plots = (ai.plot_points || []).map(p => `<li>${escHtml(p)}</li>`).join("");

  return `
    <div class="mb-3 p-3 bg-dark rounded border border-secondary">
      <h6 class="text-warning"><i class="bi bi-cpu me-1"></i>AI Analysis</h6>

      ${ai.summary ? `<p class="mb-2 fst-italic">${escHtml(ai.summary)}</p>` : ""}

      ${chars ? `<div class="mb-2"><strong class="small">Characters:</strong>
        <div class="mt-1">${chars}</div></div>` : ""}

      ${themes ? `<div class="mb-2"><strong class="small">Themes:</strong>
        <div class="mt-1">${themes}</div></div>` : ""}

      ${plots ? `<div class="mb-2"><strong class="small">Plot Points:</strong>
        <ul class="mb-0 ps-3 small">${plots}</ul></div>` : ""}

      ${ai.story_arc ? `<div><strong class="small">Story Arc:</strong>
        <span class="text-muted ms-1">${escHtml(ai.story_arc)}</span></div>` : ""}
    </div>`;
}

async function deleteStory(storyId) {
  if (!confirm("Delete this story?")) return;
  await api("DELETE", `/stories/${storyId}`);
  bootstrap.Modal.getInstance(document.getElementById("storyModal")).hide();
  if (activeWorldId) await selectWorld(activeWorldId);
}

// ── Process link ───────────────────────────────────────────────────────────────
btnProcess.addEventListener("click", async () => {
  const url = linkInput.value.trim();
  if (!url) { setStatus("Please enter a URL.", "err"); return; }
  if (!activeWorldId) { setStatus("Please select a world first.", "err"); return; }

  const mode = modeToggle.checked ? "text" : "ai";

  btnProcess.disabled = true;
  btnProcess.innerHTML =
    `<span class="spinner-border spinner-border-sm me-1"></span>Processing…`;
  setStatus("Fetching content…", "inf");

  const { ok, data } = await api("POST", "/process", {
    url, world_id: activeWorldId, mode
  });

  btnProcess.disabled = false;
  btnProcess.innerHTML = `<i class="bi bi-lightning-charge-fill me-1"></i>Process`;

  if (!ok) {
    if (data.auth_required) {
      setStatus(
        `Authentication required for ${data.auth_required}. ` +
        `<a href="#" data-bs-toggle="modal" data-bs-target="#authModal">Log in</a>`,
        "err"
      );
    } else {
      setStatus(`Error: ${escHtml(data.error || "Unknown error")}`, "err");
    }
    return;
  }

  const aiErr = mode === "ai" && data.ai_analysis && data.ai_analysis.error;
  const modeStr = mode === "text" ? "saved to TXT" : "analyzed with AI";
  setStatus(
    `<i class="bi bi-${aiErr ? "exclamation-triangle" : "check-circle"} me-1"></i>
     "<strong>${escHtml(data.title)}</strong>" ${mode === "text" ? "saved to TXT" : "saved"}.
     ${aiErr ? `<span class="text-warning">AI analysis failed: ${escHtml(data.ai_analysis.error)}</span>` : `<span class="text-muted">${modeStr}</span>`}
     ${data.txt_path ? `<span class="text-muted ms-2">File: ${escHtml(data.txt_path)}</span>` : ""}`,
    aiErr ? "err" : "ok"
  );

  linkInput.value = "";
  await selectWorld(activeWorldId);
});

// ── MeWe auth ──────────────────────────────────────────────────────────────────
async function refreshMeWeStatus() {
  const { ok, data } = await api("GET", "/auth/mewe/status");
  const badge = document.getElementById("mewe-status-badge");
  const logoutBtn = document.getElementById("btn-mewe-logout");
  const stepLogin = document.getElementById("mewe-step-login");

  if (ok && data.authenticated) {
    badge.innerHTML = `<span class="badge bg-success"><i class="bi bi-check-circle me-1"></i>
      Logged in to MeWe</span>`;
    logoutBtn.classList.remove("d-none");
    stepLogin.classList.add("d-none");
  } else {
    badge.innerHTML = `<span class="badge bg-secondary">Not logged in</span>`;
    logoutBtn.classList.add("d-none");
    stepLogin.classList.remove("d-none");
  }
}

document.querySelector('[data-bs-target="#authModal"]').addEventListener("click",
  () => { refreshMeWeStatus(); refreshDiscordStatus(); });

document.getElementById("btn-mewe-login").addEventListener("click", async () => {
  const email = document.getElementById("mewe-email").value.trim();
  const password = document.getElementById("mewe-password").value;
  const msg = document.getElementById("mewe-auth-msg");
  if (!email || !password) {
    msg.innerHTML = `<span class="status-err">Enter your email and password.</span>`;
    return;
  }

  msg.innerHTML = `<span class="status-inf">Logging in…</span>`;
  const { ok, data } = await api("POST", "/auth/mewe/login", { email, password });
  if (ok) {
    msg.innerHTML = `<span class="status-ok">${escHtml(data.message)}</span>`;
    document.getElementById("mewe-password").value = "";
    refreshMeWeStatus();
  } else {
    msg.innerHTML = `<span class="status-err">${escHtml(data.error)}</span>`;
  }
});

document.getElementById("btn-mewe-logout").addEventListener("click", async () => {
  await api("POST", "/auth/mewe/logout");
  refreshMeWeStatus();
});

// ── Discord auth ───────────────────────────────────────────────────────────────
async function refreshDiscordStatus() {
  const { ok, data } = await api("GET", "/auth/discord/status");
  const badge = document.getElementById("discord-status-badge");
  const logoutBtn = document.getElementById("btn-discord-logout");
  if (ok && data.authenticated) {
    badge.innerHTML = `<span class="badge bg-success"><i class="bi bi-check-circle me-1"></i>
      Discord token active</span>`;
    logoutBtn.classList.remove("d-none");
  } else {
    badge.innerHTML = `<span class="badge bg-secondary">No token saved</span>`;
    logoutBtn.classList.add("d-none");
  }
}

document.getElementById("btn-discord-save").addEventListener("click", async () => {
  const token = document.getElementById("discord-token").value.trim();
  const msg = document.getElementById("discord-auth-msg");
  if (!token) { msg.innerHTML = `<span class="status-err">Enter your token.</span>`; return; }

  msg.innerHTML = `<span class="status-inf">Validating…</span>`;
  const { ok, data } = await api("POST", "/auth/discord", { token });
  if (ok) {
    msg.innerHTML = `<span class="status-ok">${escHtml(data.message)}</span>`;
    document.getElementById("discord-token").value = "";
    refreshDiscordStatus();
  } else {
    msg.innerHTML = `<span class="status-err">${escHtml(data.error)}</span>`;
  }
});

document.getElementById("btn-discord-logout").addEventListener("click", async () => {
  await api("POST", "/auth/discord/logout");
  refreshDiscordStatus();
});

// ── Settings ───────────────────────────────────────────────────────────────────
document.querySelector('[data-bs-target="#settingsModal"]').addEventListener("click", async () => {
  const { ok, data } = await api("GET", "/settings");
  if (!ok) return;
  document.getElementById("ai-backend").value = data.ai_backend || "ollama";
  document.getElementById("ai-model").value = data.ai_model || "";
  toggleOpenAiKey(data.ai_backend || "ollama");
});

document.getElementById("ai-backend").addEventListener("change", e =>
  toggleOpenAiKey(e.target.value));

function toggleOpenAiKey(backend) {
  document.getElementById("openai-key-row").style.display =
    backend === "openai" ? "" : "none";
}

document.getElementById("btn-save-settings").addEventListener("click", async () => {
  const payload = {
    ai_backend: document.getElementById("ai-backend").value,
    ai_model:   document.getElementById("ai-model").value.trim(),
  };
  const key = document.getElementById("openai-key").value.trim();
  if (key) payload.openai_api_key = key;

  const { ok } = await api("POST", "/settings", payload);
  const msg = document.getElementById("settings-msg");
  msg.innerHTML = ok
    ? `<span class="status-ok">Settings saved.</span>`
    : `<span class="status-err">Failed to save.</span>`;
  setTimeout(() => { msg.innerHTML = ""; }, 2500);
});

// ── Init ───────────────────────────────────────────────────────────────────────
(async () => {
  await loadWorlds();
  if (worlds.length) selectWorld(worlds[0].id);
})();
