const $ = (id) => document.getElementById(id);
const statusEl = $("status");

const DEFAULT_BACKEND_URL = "http://localhost:8000";
// URLs that earlier builds of the extension stored. If any of them are still
// in chrome.storage from an older install we silently migrate to the current
// default. Anything the user typed by hand is preserved.
const LEGACY_BACKEND_URLS = new Set([
  "https://neuanchor.com/meeting-api",
  "http://127.0.0.1:8000",
]);

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
    patientEmail,
    recording,
    recordingSource,
    lastSessionId,
    lastUploadError,
    includeMic,
    stopping,
  } = await chrome.storage.local.get([
    "backendUrl",
    "patientEmail",
    "recording",
    "recordingSource",
    "lastSessionId",
    "lastUploadError",
    "includeMic",
    "stopping",
  ]);
  let url = backendUrl || DEFAULT_BACKEND_URL;
  if (LEGACY_BACKEND_URLS.has(url)) {
    url = DEFAULT_BACKEND_URL;
    await chrome.storage.local.set({ backendUrl: url });
  }
  $("backend").value = url;
  $("email").value = patientEmail || "";
  $("include-mic").checked = !!includeMic;

  // Check `stopping` first: when the user clicks Stop, the background marks
  // stopping=true but leaves recording=true until the offscreen page finishes
  // the upload. Without this order, the popup would still show "Recording…"
  // and the Stop button after a Stop click was already in progress.
  if (stopping) {
    // If the offscreen page is gone, the upload is lost — auto-clear the
    // stale flag so the popup doesn't appear stuck forever after a previous
    // bad run (e.g., extension reload mid-upload).
    const liveness = await chrome.runtime.sendMessage({ type: "ping" }).catch(
      () => null
    );
    if (!liveness?.offscreenAlive) {
      await chrome.storage.local.set({
        recording: false,
        recordingSource: null,
        stopping: false,
        lastUploadError:
          "Previous upload was lost (the recording page is no longer running). Start a new recording.",
      });
      setStatus(
        "Previous upload was lost. Start a new recording.",
        true
      );
      return;
    }
    if (recordingSource) showPanel(recordingSource);
    setStatus("Stopping & uploading…");
    watchForUploadCompletion();
  } else if (recording && recordingSource) {
    showPanel(recordingSource);
    setRecordingUI(recordingSource, true);
    setStatus("Recording…");
  } else if (lastUploadError) {
    setStatus(`Failed: ${lastUploadError}`, true);
  } else if (lastSessionId) {
    setStatus(uploadedLink(url, lastSessionId, "Last upload:"));
  }
}

// ─── Start / Stop recording (tab or mic) ──────────────────────────────────
function emailIsValid(s) {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(s);
}

async function startRecording(source) {
  const backendUrl = $("backend").value.trim().replace(/\/$/, "");
  const patientEmail = $("email").value.trim().toLowerCase();
  if (!backendUrl) return setStatus("Enter a backend URL.", true);
  if (!emailIsValid(patientEmail))
    return setStatus("Enter a valid patient email.", true);

  // Wipe any previous result/error so a stale message doesn't reappear.
  await chrome.storage.local.set({
    backendUrl,
    patientEmail,
    lastSessionId: null,
    lastUploadError: null,
  });

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

$("email").addEventListener("change", (e) =>
  chrome.storage.local.set({ patientEmail: e.target.value.trim().toLowerCase() })
);

$("start-tab").addEventListener("click", () => startRecording("tab"));
$("stop-tab").addEventListener("click", () => stopRecording("tab"));
$("start-mic").addEventListener("click", () => startRecording("mic"));
$("stop-mic").addEventListener("click", () => stopRecording("mic"));

// ─── File upload ──────────────────────────────────────────────────────────
$("start-upload").addEventListener("click", async () => {
  const backendUrl = $("backend").value.trim().replace(/\/$/, "");
  const patientEmail = $("email").value.trim().toLowerCase();
  if (!backendUrl) return setStatus("Enter a backend URL.", true);
  if (!emailIsValid(patientEmail))
    return setStatus("Enter a valid patient email.", true);
  await chrome.storage.local.set({ backendUrl, patientEmail });

  const file = $("file-input").files?.[0];
  if (!file) return setStatus("Pick a file first.", true);

  $("start-upload").disabled = true;
  setStatus(`Uploading ${file.name}…`);

  try {
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("email", patientEmail);
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
