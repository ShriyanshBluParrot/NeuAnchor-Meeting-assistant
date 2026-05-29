// Runs in an offscreen document — the only place in MV3 where MediaRecorder
// and the legacy `chromeMediaSource: 'tab'` capture path are available.

let recorder = null;
let chunks = [];
let stream = null;
let audioCtx = null;
let backendUrl = "";

async function getStream(source, streamId) {
  if (source === "mic") {
    return navigator.mediaDevices.getUserMedia({ audio: true });
  }
  // Tab capture.
  return navigator.mediaDevices.getUserMedia({
    audio: {
      mandatory: {
        chromeMediaSource: "tab",
        chromeMediaSourceId: streamId,
      },
    },
  });
}

async function start(source, streamId, url) {
  backendUrl = url;
  chunks = [];

  stream = await getStream(source, streamId);

  // For tab capture, pipe the audio back to the user's speakers so the meeting
  // stays audible while recording. Microphone capture doesn't need this and
  // doing so would cause feedback.
  if (source === "tab") {
    audioCtx = new AudioContext();
    audioCtx.createMediaStreamSource(stream).connect(audioCtx.destination);
  }

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
  stream?.getTracks().forEach((t) => t.stop());
  await audioCtx?.close();
  recorder = null;
  stream = null;
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
        await start(msg.source ?? "tab", msg.streamId, msg.backendUrl);
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
