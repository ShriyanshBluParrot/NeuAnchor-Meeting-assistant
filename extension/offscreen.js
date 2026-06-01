// Offscreen document — produces the audio blob, then handoff to background.
//
// Why two-step: Chrome can terminate an offscreen page once its "USER_MEDIA"
// reason is no longer active (after the recorder stops). Doing the upload
// here used to hang because the page died mid-fetch. Instead we build the
// blob, base64-encode it, hand it to the service worker, and the service
// worker performs the fetch — which is far more lifecycle-stable.

let recorder = null;
let chunks = [];
let sourceStreams = [];
let audioCtx = null;
let backendUrl = "";

async function getTabStream(streamId) {
  return navigator.mediaDevices.getUserMedia({
    audio: {
      mandatory: {
        chromeMediaSource: "tab",
        chromeMediaSourceId: streamId,
      },
    },
  });
}

async function getMicStream() {
  try {
    return await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    if (
      err.name === "NotAllowedError" ||
      /dismissed|denied/i.test(err.message || "")
    ) {
      throw new Error(
        "Microphone permission required. Allow it via the mic icon in the address bar, then try again."
      );
    }
    throw err;
  }
}

async function buildRecordingStream(source, streamId, includeMic) {
  if (source === "mic") {
    const mic = await getMicStream();
    sourceStreams.push(mic);
    return mic;
  }
  const tab = await getTabStream(streamId);
  sourceStreams.push(tab);

  audioCtx = new AudioContext();
  const tabNode = audioCtx.createMediaStreamSource(tab);
  tabNode.connect(audioCtx.destination); // keep audible

  if (!includeMic) return tab;

  const mic = await getMicStream();
  sourceStreams.push(mic);
  const dest = audioCtx.createMediaStreamDestination();
  tabNode.connect(dest);
  audioCtx.createMediaStreamSource(mic).connect(dest);
  return dest.stream;
}

async function start(source, streamId, url, includeMic) {
  backendUrl = url;
  chunks = [];
  sourceStreams = [];

  const stream = await buildRecordingStream(source, streamId, includeMic);
  recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
  recorder.ondataavailable = (e) => {
    if (e.data.size > 0) chunks.push(e.data);
  };
  recorder.start(1000);
  console.log("[offscreen] recording started, source=", source);
}

async function stopAndBuildBlob() {
  if (!recorder) {
    throw new Error(
      "No active recording — the extension may have been reloaded or the offscreen page was restarted. Please record again."
    );
  }
  console.log("[offscreen] stopping recorder, chunks so far:", chunks.length);

  // Race the onstop event against a hard timeout: some MediaRecorder/stream
  // combinations intermittently fail to fire `onstop`.
  const blob = await new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      resolve(new Blob(chunks, { type: "audio/webm" }));
    };
    recorder.onstop = finish;
    try {
      recorder.stop();
    } catch (err) {
      console.warn("[offscreen] recorder.stop threw:", err);
      finish();
    }
    setTimeout(() => {
      if (!settled)
        console.warn(
          "[offscreen] onstop never fired after 10s — using existing chunks"
        );
      finish();
    }, 10_000);
  });
  console.log("[offscreen] blob ready:", blob.size, "bytes");

  // Release streams immediately — we've got the bytes, the page can be torn
  // down by Chrome as soon as it likes; the background SW will own the upload.
  try {
    sourceStreams.forEach((s) => s.getTracks().forEach((t) => t.stop()));
    await audioCtx?.close();
  } catch (e) {
    console.warn("[offscreen] cleanup error (ignored):", e);
  }
  recorder = null;
  sourceStreams = [];
  audioCtx = null;

  if (blob.size === 0) throw new Error("Recording was empty (0 bytes).");
  return blob;
}

async function blobToBase64(blob) {
  return await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const url = reader.result;
      // strip "data:audio/webm;base64," prefix
      const comma = url.indexOf(",");
      resolve(url.slice(comma + 1));
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type !== "offscreen-start" && msg?.type !== "offscreen-stop")
    return false;
  (async () => {
    try {
      if (msg?.type === "offscreen-start") {
        await start(
          msg.source ?? "tab",
          msg.streamId,
          msg.backendUrl,
          !!msg.includeMic
        );
        sendResponse({ ok: true });
      } else if (msg?.type === "offscreen-stop") {
        const blob = await stopAndBuildBlob();
        const base64 = await blobToBase64(blob);
        console.log("[offscreen] base64 ready, length:", base64.length);
        // Hand off to background. We don't await a response — background
        // writes the result directly into chrome.storage, which the popup
        // observes.
        chrome.runtime
          .sendMessage({
            type: "upload-blob",
            base64,
            contentType: "audio/webm",
            backendUrl,
          })
          .catch(() => {});
        sendResponse({ ok: true });
      }
    } catch (err) {
      console.error("[offscreen] error:", err);
      // Make sure the popup sees a failure instead of hanging forever.
      try {
        await chrome.storage.local.set({
          recording: false,
          recordingSource: null,
          stopping: false,
          lastUploadError: err.message || "offscreen failed",
        });
      } catch {}
      sendResponse({ ok: false, error: err.message });
    }
  })();
  return true;
});
