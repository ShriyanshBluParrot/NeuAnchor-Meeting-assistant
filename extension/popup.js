const $ = (id) => document.getElementById(id);
const statusEl = $("status");

function setStatus(text, isError = false) {
  statusEl.style.display = "block";
  statusEl.className = isError ? "status error" : "status";
  statusEl.innerHTML = text;
}

function frontendUrlFor(backendUrl, sessionId) {
  // Dev convenience: the frontend dev server runs on :5173, so swap the port.
  const url = backendUrl.replace(/:\d+$/, ":5173");
  return `${url}/meetings/${sessionId}`;
}

function uploadedLink(backendUrl, sessionId, prefix = "Uploaded!") {
  return `${prefix} <a href="${frontendUrlFor(
    backendUrl,
    sessionId
  )}" target="_blank">open meeting ${sessionId.slice(0, 8)}…</a>`;
}

// ─── Mode tabs ────────────────────────────────────────────────────────────
function showPanel(mode) {
  document
    .querySelectorAll(".tab")
    .forEach((t) => t.classList.toggle("active", t.dataset.mode === mode));
  document
    .querySelectorAll(".panel")
    .forEach((p) => p.classList.toggle("active", p.dataset.panel === mode));
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => showPanel(tab.dataset.mode));
});

// ─── Recording state UI (shared by tab + mic) ────────────────────────────
function setRecordingUI(source, recording) {
  $(`start-${source}`).style.display = recording ? "none" : "block";
  $(`stop-${source}`).style.display = recording ? "block" : "none";
}

// ─── Init ─────────────────────────────────────────────────────────────────
async function loadDefaults() {
  const { backendUrl, recording, recordingSource, lastSessionId } =
    await chrome.storage.local.get([
      "backendUrl",
      "recording",
      "recordingSource",
      "lastSessionId",
    ]);
  const url = backendUrl || "http://localhost:8000";
  $("backend").value = url;

  if (recording && recordingSource) {
    showPanel(recordingSource);
    setRecordingUI(recordingSource, true);
    setStatus("Recording…");
  } else if (lastSessionId) {
    setStatus(uploadedLink(url, lastSessionId, "Last upload:"));
  }
}

// ─── Start / Stop recording (tab or mic) ──────────────────────────────────
async function startRecording(source) {
  const backendUrl = $("backend").value.trim().replace(/\/$/, "");
  if (!backendUrl) return setStatus("Enter a backend URL.", true);
  await chrome.storage.local.set({ backendUrl });

  $(`start-${source}`).disabled = true;
  setStatus("Starting…");

  const payload = { type: "start", source, backendUrl };
  if (source === "tab") {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    payload.tabId = tab.id;
  }

  const resp = await chrome.runtime.sendMessage(payload);
  $(`start-${source}`).disabled = false;

  if (!resp?.ok) return setStatus(`Failed: ${resp?.error ?? "unknown"}`, true);

  setRecordingUI(source, true);
  setStatus("Recording…");
}

async function stopRecording(source) {
  setStatus("Stopping & uploading…");
  $(`stop-${source}`).disabled = true;
  const resp = await chrome.runtime.sendMessage({ type: "stop" });
  $(`stop-${source}`).disabled = false;
  setRecordingUI(source, false);

  const url = $("backend").value.trim().replace(/\/$/, "");

  if (!resp?.ok) return setStatus(`Failed: ${resp?.error ?? "unknown"}`, true);

  if (!resp.sessionId) {
    const { lastSessionId } = await chrome.storage.local.get("lastSessionId");
    return lastSessionId
      ? setStatus(uploadedLink(url, lastSessionId, "Already uploaded:"))
      : setStatus("Nothing was recording.");
  }
  setStatus(uploadedLink(url, resp.sessionId));
}

$("start-tab").addEventListener("click", () => startRecording("tab"));
$("stop-tab").addEventListener("click", () => stopRecording("tab"));
$("start-mic").addEventListener("click", () => startRecording("mic"));
$("stop-mic").addEventListener("click", () => stopRecording("mic"));

// ─── File upload ──────────────────────────────────────────────────────────
$("start-upload").addEventListener("click", async () => {
  const backendUrl = $("backend").value.trim().replace(/\/$/, "");
  if (!backendUrl) return setStatus("Enter a backend URL.", true);
  await chrome.storage.local.set({ backendUrl });

  const file = $("file-input").files?.[0];
  if (!file) return setStatus("Pick a file first.", true);

  $("start-upload").disabled = true;
  setStatus(`Uploading ${file.name}…`);

  try {
    const form = new FormData();
    form.append("file", file, file.name);
    const resp = await fetch(`${backendUrl}/meetings/upload`, {
      method: "POST",
      body: form,
    });
    if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
    const data = await resp.json();
    await chrome.storage.local.set({ lastSessionId: data.session_id });
    setStatus(uploadedLink(backendUrl, data.session_id));
  } catch (err) {
    setStatus(`Failed: ${err.message}`, true);
  } finally {
    $("start-upload").disabled = false;
  }
});

loadDefaults();
