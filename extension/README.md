# AI Meeting Assistant — Chrome Extension

Records any meeting from your browser and uploads it to the backend for
transcription, summary, and notes. Three capture modes:

- **Online (tab audio)** — records the active tab (e.g. a Google Meet you're
  in). Captures every participant. Optional checkbox to also mix in your
  microphone.
- **Offline (mic)** — records the device microphone (e.g. a laptop on a
  table in an in-person meeting).
- **Upload file** — pick a pre-recorded audio/video file from disk.

## Install (developer mode)

1. Make sure the backend is running and reachable.
2. Open **Chrome → chrome://extensions**.
3. Toggle **Developer mode** (top-right) ON.
4. Click **Load unpacked** → select this `extension/` folder.
5. Pin the extension to the toolbar (puzzle icon → pin "AI Meeting Assistant Recorder").

## Use

1. Click the extension icon.
2. Set the **Backend URL** (default `http://localhost:8000`).
3. Pick a mode tab:
   - **Online** → optionally tick "Also record my microphone" → **Start
     recording this tab**.
   - **Offline** → **Start mic recording** (Chrome will ask for mic permission
     the first time — click Allow).
   - **Upload file** → pick a file → **Upload & process**.
4. When done, click **Stop & upload**. The popup shows a link to the meeting
   page when the upload completes.

## How it works

```
popup ──Start──▶ background (service worker)
                    │ chrome.tabCapture.getMediaStreamId(activeTab)
                    ▼
                  offscreen document
                    │ getUserMedia({audio: chromeMediaSource:'tab' / mic})
                    │ MediaRecorder → audio/webm Blob
                    ▼
              POST /meetings/upload  →  MongoDB GridFS + AssemblyAI + Gemini
```

The offscreen document is required because MV3 service workers can't use
`MediaRecorder`. In tab-capture mode it also pipes the captured stream back to
your speakers so you keep hearing the meeting while it records.

## Notes

- Only Chromium browsers (Chrome, Edge, Brave). Firefox/Safari MV3 support is
  incomplete for this API surface.
- Recording continues even if you close the popup. Re-open it to stop —
  the upload finishes in the background and the popup shows the link on the
  next open.
- The extension records the tab it was started on, regardless of which tab is
  currently active.
- The first time you use the mic, Chrome shows a permission prompt. If you
  miss it / accidentally deny, open `permission.html` from the extension's
  folder via `chrome-extension://<id>/permission.html` to re-grant.
