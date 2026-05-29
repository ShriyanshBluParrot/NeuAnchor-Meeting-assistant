# AI Meeting Assistant — Chrome Extension

Captures the audio of the active browser tab (e.g. a Google Meet you're in) and
uploads it to your local backend for transcription, summary, and notes. Works
for any meeting you can join yourself — no sign-in/admit dance, no Recall.ai
cost.

## Install (developer mode)

1. Make sure the backend is running: `cd backend && uvicorn main:app --reload --port 8000`
2. Open **Chrome → chrome://extensions**
3. Toggle **Developer mode** (top-right) ON
4. Click **Load unpacked** → select this `extension/` folder
5. Pin the extension to the toolbar (puzzle icon → pin "AI Meeting Assistant Recorder")

## Use

1. Join your Google Meet in a tab (sign-in works because *you're* signed in)
2. Click the extension icon on that tab
3. Set the backend URL (default `http://localhost:8000`) → **Start recording this tab**
4. Talk through the meeting normally
5. When done, click the extension icon again → **Stop & upload**
6. The popup shows a link to the meeting page — open it to see transcript,
   summary, notes, and chat once processing finishes.

## How it works

```
popup ──Start──▶ background (service worker)
                    │ chrome.tabCapture.getMediaStreamId(activeTab)
                    ▼
                  offscreen document
                    │ getUserMedia({audio: chromeMediaSource:'tab'})
                    │ MediaRecorder → audio/webm Blob
                    ▼
              POST /meetings/upload  →  GCS + AssemblyAI + Gemini
```

The offscreen document is required because MV3 service workers can't use
`MediaRecorder`. It also keeps the meeting audible to you while recording (the
captured stream is piped to the local speakers).

## Notes

- Only Chromium browsers (Chrome, Edge, Brave). Firefox/Safari MV3 support is
  incomplete for this API surface.
- Recording continues even if you close the popup. Re-open the popup to stop.
- The extension only has access to the tab you started recording from; if you
  switch tabs the audio you capture is still the *original* tab's audio.
