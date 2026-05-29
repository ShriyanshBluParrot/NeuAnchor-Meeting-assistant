// Background service worker: orchestrates audio capture via an offscreen
// document. Supports two audio sources:
//   - "tab" → captures the current tab's audio (online meeting in a Meet tab)
//   - "mic" → captures the user's microphone (in-person meeting)
//
// MV3 service workers cannot use MediaRecorder, and `chrome.tabCapture` needs
// to be initiated from a user gesture. So the popup's Start click lands here;
// we acquire whatever resource the source needs and hand it to the offscreen
// page, which runs the actual recording.

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

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
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
          lastSessionId: null,
        });
        sendResponse({ ok: true });
      } else if (msg?.type === "stop") {
        // Kick off the upload in the background and return immediately. The
        // popup might close before the upload finishes; persisting state via
        // chrome.storage.local lets a re-opened popup pick up the result.
        await setState({
          stopping: true,
          lastSessionId: null,
          lastUploadError: null,
        });
        (async () => {
          let result = { ok: true, sessionId: null };
          try {
            if (await chrome.offscreen.hasDocument?.()) {
              const r = await chrome.runtime.sendMessage({
                type: "offscreen-stop",
              });
              if (r) result = r;
            }
          } catch (err) {
            result = { ok: false, error: err.message };
          } finally {
            await closeOffscreen();
            await setState({
              recording: false,
              recordingSource: null,
              stopping: false,
              lastSessionId: result.ok ? result.sessionId ?? null : null,
              lastUploadError: result.ok ? null : result.error ?? "unknown",
            });
          }
        })();
        sendResponse({ ok: true, queued: true });
      }
    } catch (err) {
      await setState({ recording: false, recordingSource: null });
      sendResponse({ ok: false, error: err.message });
    }
  })();
  return true; // keep the message channel open for the async sendResponse
});
