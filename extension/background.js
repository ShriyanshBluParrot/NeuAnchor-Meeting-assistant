// Background service worker: orchestrates audio capture via an offscreen
// document. Supports two audio sources:
//   - "tab" → captures the current tab's audio (online meeting in a Meet tab)
//   - "mic" → captures the user's microphone (in-person meeting)
//
// MV3 service workers cannot use MediaRecorder, and `chrome.tabCapture` needs
// to be initiated from a user gesture. So the popup's Start click lands here;
// we acquire whatever resource the source needs and hand it to the offscreen
// page, which runs the actual recording.
//
// Stop flow: we *don't* await a sendMessage response from offscreen — that
// channel rejects spuriously when the popup closes mid-upload, surfacing a
// confusing "message channel closed" error. Instead, offscreen writes the
// upload result directly into chrome.storage, and a storage listener here
// tears down the offscreen page when it's done. The popup watches the same
// storage keys to reflect status to the user.

const OFFSCREEN_PATH = "offscreen.html";

async function ensureOffscreen() {
  const has = await chrome.offscreen.hasDocument?.();
  if (has) return;
  await chrome.offscreen.createDocument({
    url: OFFSCREEN_PATH,
    reasons: ["USER_MEDIA"],
    justification: "Recording audio for meeting transcription.",
  });
}

async function closeOffscreen() {
  if (await chrome.offscreen.hasDocument?.()) {
    await chrome.offscreen.closeDocument();
  }
}

async function setState(state) {
  await chrome.storage.local.set(state);
}

async function handleUploadBlob({ base64, contentType, backendUrl }) {
  let sessionId = null;
  let errorMessage = null;
  try {
    const { patientEmail } = await chrome.storage.local.get("patientEmail");
    if (!patientEmail) throw new Error("Missing patient email.");
    if (!backendUrl) throw new Error("Missing backend URL.");

    // Decode base64 → Uint8Array → Blob → FormData → fetch.
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const blob = new Blob([bytes], { type: contentType || "audio/webm" });

    const form = new FormData();
    form.append("file", blob, "recording.webm");
    form.append("email", patientEmail);

    console.log(
      "[background] uploading",
      blob.size,
      "bytes to",
      `${backendUrl}/meetings/upload`
    );
    const resp = await fetch(`${backendUrl}/meetings/upload`, {
      method: "POST",
      body: form,
    });
    if (!resp.ok) throw new Error(`upload ${resp.status}: ${await resp.text()}`);
    const data = await resp.json();
    sessionId = data.session_id;
    console.log("[background] upload OK, session:", sessionId);
  } catch (err) {
    console.error("[background] upload error:", err);
    errorMessage = err.message || "upload failed";
  }
  await setState({
    recording: false,
    recordingSource: null,
    stopping: false,
    lastSessionId: sessionId,
    lastUploadError: errorMessage,
  });
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  // Only claim messages we actually handle.
  if (msg?.type === "ping") {
    chrome.offscreen.hasDocument?.().then((alive) =>
      sendResponse({ offscreenAlive: !!alive })
    );
    return true;
  }
  if (msg?.type === "upload-blob") {
    // Offscreen finished recording and handed us the base64 blob. Do the
    // upload here — service workers are far more lifecycle-stable than
    // offscreen pages, so the fetch reliably completes.
    handleUploadBlob(msg).finally(() => closeOffscreen().catch(() => {}));
    sendResponse({ ok: true });
    return false;
  }
  if (msg?.type !== "start" && msg?.type !== "stop") return false;
  (async () => {
    try {
      if (msg?.type === "start") {
        const source = msg.source ?? "tab";
        // Tear down any leftover offscreen + stream first. Chrome's tabCapture
        // refuses a second stream on the same tab ("active stream") until the
        // old one is released.
        await closeOffscreen();
        const startMsg = {
          type: "offscreen-start",
          source,
          backendUrl: msg.backendUrl,
          includeMic: !!msg.includeMic,
        };
        if (source === "tab") {
          startMsg.streamId = await chrome.tabCapture.getMediaStreamId({
            targetTabId: msg.tabId,
          });
        }
        await ensureOffscreen();
        const resp = await chrome.runtime.sendMessage(startMsg);
        if (!resp?.ok) throw new Error(resp?.error ?? "offscreen failed");
        await setState({
          recording: true,
          recordingSource: source,
          stopping: false,
          lastSessionId: null,
          lastUploadError: null,
        });
        sendResponse({ ok: true });
      } else if (msg?.type === "stop") {
        // Clear previous result and mark uploading.
        await setState({
          stopping: true,
          lastSessionId: null,
          lastUploadError: null,
        });
        // Fire-and-forget. The offscreen page will write the result to
        // chrome.storage when the upload completes; the popup watches storage,
        // and our own storage listener (below) closes the offscreen.
        if (await chrome.offscreen.hasDocument?.()) {
          chrome.runtime
            .sendMessage({ type: "offscreen-stop" })
            .catch(() => {});
        } else {
          // No offscreen — nothing to stop.
          await setState({
            recording: false,
            recordingSource: null,
            stopping: false,
          });
        }
        sendResponse({ ok: true, queued: true });
      }
    } catch (err) {
      await setState({
        recording: false,
        recordingSource: null,
        stopping: false,
        lastUploadError: err.message,
      });
      sendResponse({ ok: false, error: err.message });
    }
  })();
  return true; // keep the message channel open for the async sendResponse
});

// We intentionally don't auto-close the offscreen page after an upload. An
// earlier version did so on storage.stopping(true → false), but that listener
// also fired the next time the user clicked Start — because the Start handler
// resets stopping back to false — and silently closed the brand-new offscreen
// page mid-recording. The next Start already calls closeOffscreen() before
// creating a fresh one, which is enough cleanup; an idle offscreen page
// between sessions costs essentially nothing.
