// Runs in an offscreen document — the only place in MV3 where MediaRecorder
// and the legacy `chromeMediaSource: 'tab'` capture path are available.

let recorder = null;
let chunks = [];
let sourceStreams = []; // every raw stream we open, so Stop can release them
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

/**
 * Build the final stream MediaRecorder will consume.
 *
 *   source=tab, includeMic=false → tab stream (also piped back to speakers
 *                                 so the meeting stays audible)
 *   source=tab, includeMic=true  → tab + mic mixed via Web Audio; tab is
 *                                 still piped back to speakers, mic is not
 *                                 (avoids feedback)
 *   source=mic                   → mic stream only, not piped back
 */
async function buildRecordingStream(source, streamId, includeMic) {
  if (source === "mic") {
    const mic = await getMicStream();
    sourceStreams.push(mic);
    return mic;
  }

  // Tab path.
  const tab = await getTabStream(streamId);
  sourceStreams.push(tab);

  audioCtx = new AudioContext();
  const tabNode = audioCtx.createMediaStreamSource(tab);
  // Keep the meeting audible.
  tabNode.connect(audioCtx.destination);

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
  recorder.start(1000); // gather data every second so a crash loses less
}

async function stop() {
  // Idempotent: a duplicate Stop click (or one fired after the popup reopened)
  // shouldn't raise — just report no-op so the UI can recover gracefully.
  if (!recorder) return null;

  const blob = await new Promise((resolve) => {
    recorder.onstop = () => resolve(new Blob(chunks, { type: "audio/webm" }));
    recorder.stop();
  });
  sourceStreams.forEach((s) => s.getTracks().forEach((t) => t.stop()));
  await audioCtx?.close();
  recorder = null;
  sourceStreams = [];
  audioCtx = null;

  const form = new FormData();
  form.append("file", blob, "recording.webm");
  const resp = await fetch(`${backendUrl}/meetings/upload`, {
    method: "POST",
    body: form,
  });
  if (!resp.ok) throw new Error(`upload ${resp.status}: ${await resp.text()}`);
  const data = await resp.json();
  return data.session_id;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
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
        const sessionId = await stop();
        sendResponse({ ok: true, sessionId });
      }
    } catch (err) {
      sendResponse({ ok: false, error: err.message });
    }
  })();
  return true;
});
