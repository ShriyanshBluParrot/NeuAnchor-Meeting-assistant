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
  const {
    backendUrl,
    recording,
    recordingSource,
    lastSessionId,
    lastUploadError,
    includeMic,
    stopping,
  } = await chrome.storage.local.get([
    "backendUrl",
    "recording",
    "recordingSource",
    "lastSessionId",
    "lastUploadError",
    "includeMic",
    "stopping",
  ]);
  const url = backendUrl || "http://localhost:8000";
  $("backend").value = url;
  $("include-mic").checked = !!includeMic;

  if (recording && recordingSource) {
    showPanel(recordingSource);
    setRecordingUI(recordingSource, true);
    setStatus("Recording…");
  } else if (stopping) {
    // Upload is in progress in the background — keep showing it until done.
    setStatus("Stopping & uploading…");
    watchForUploadCompletion();
  } else if (lastUploadError) {
    setStatus(`Failed: ${lastUploadError}`, true);
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
    payload.includeMic = $("include-mic").checked;
  }

  // For any mode that needs the mic, request the permission from the popup
  // itself first. If it fails (often because Chrome cached a previous denial),
  // open a dedicated permission page in a normal tab where the user can grant
  // it cleanly — the popup itself can't reliably show a fresh prompt once a
  // denial is cached for the extension's origin.
  if (source === "mic" || payload.includeMic) {
    try {
      const probe = await navigator.mediaDevices.getUserMedia({ audio: true });
      probe.getTracks().forEach((t) => t.stop());
    } catch {
      $(`start-${source}`).disabled = false;
      const permUrl = chrome.runtime.getURL("permission.html");
      setStatus(
        `Microphone permission needed. <a href="${permUrl}" target="_blank">Open permission page</a> → click Allow, then try again.`,
        true
      );
      chrome.tabs.create({ url: permUrl });
      return;
    }
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
  setRecordingUI(source, false);
  // Fire-and-forget; the upload runs in the background. The storage watcher
  // (attached in loadDefaults / below) reflects completion in the UI whenever
  // the popup is open.
  await chrome.runtime.sendMessage({ type: "stop" });
  watchForUploadCompletion();
}

let _uploadWatcher = null;
function watchForUploadCompletion() {
  if (_uploadWatcher) return; // only one listener at a time
  _uploadWatcher = (changes, area) => {
    if (area !== "local" || !("stopping" in changes)) return;
    if (changes.stopping.newValue !== false) return;
    chrome.storage.onChanged.removeListener(_uploadWatcher);
    _uploadWatcher = null;
    showFinalUploadStatus();
  };
  chrome.storage.onChanged.addListener(_uploadWatcher);
}

async function showFinalUploadStatus() {
  const { lastSessionId, lastUploadError } = await chrome.storage.local.get([
    "lastSessionId",
    "lastUploadError",
  ]);
  const url = $("backend").value.trim().replace(/\/$/, "");
  document
    .querySelectorAll('button[id^="stop-"]')
    .forEach((b) => (b.disabled = false));
  if (lastUploadError) setStatus(`Failed: ${lastUploadError}`, true);
  else if (lastSessionId) setStatus(uploadedLink(url, lastSessionId));
  else setStatus("Nothing was recording.");
}

$("include-mic").addEventListener("change", (e) =>
  chrome.storage.local.set({ includeMic: e.target.checked })
);

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
