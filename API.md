# API Reference — Frontend Integration Guide

Backend base URL during dev: `http://localhost:8000`
All responses are JSON unless noted. All times are UTC ISO-8601 strings.

---

## Quick reference

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness probe |
| **GET** | **`/admin/dashboard`** | **One-call payload for the admin home page** |
| GET | `/meetings` | List meetings (paginated, filterable) |
| GET | `/meetings/{id}` | Full meeting (transcript + summary + notes + audio URL) |
| GET | `/meetings/{id}/status` | Lightweight status poll |
| GET | `/meetings/{id}/transcript` | Just the speaker-labelled transcript |
| GET | `/meetings/{id}/summary` | Just the summary (+ title) |
| GET | `/meetings/{id}/notes` | Just the structured notes |
| GET | `/meetings/{id}/audio` | Stream the recorded audio (audio tag / download) |
| POST | `/meetings/{id}/chat` | Streaming SSE chat over the transcript |
| POST | `/meetings/upload` | Multipart upload (extension uses this; admin rarely needs it) |
| GET | `/patients` | List patients (paginated, searchable) |
| GET | `/patients/{email}` | One patient + their meetings (chronological) |
| PATCH | `/patients/{email}` | Update patient name |

---

## Status lifecycle of a meeting

```
upload received  ─▶  "processing"  ─▶  "ready"
                                   └─▶  "error"
```

- **processing** — audio is in storage, AssemblyAI/Gemini still running.
- **ready** — `transcript`, `summary`, `notes`, `title` are populated.
- **error** — see `error_msg` field.

Frontend rule of thumb: **poll `/meetings/{id}/status` every 4 seconds while status is `processing`**.

---

## Endpoints

### `GET /admin/dashboard`
The one call your admin home page needs. Returns aggregate counts + recent activity, no transcripts.

**Response**
```json
{
  "totals": { "patients": 3, "meetings": 4 },
  "meetings_by_status": { "ready": 3, "error": 1 },
  "recent_meetings": [
    {
      "id": "4ff90dc7-…",
      "patient_email": "nk1@bluparrot.in",
      "mode": "offline",
      "status": "ready",
      "title": "Introduction to Agentic Tools",
      "created_at": "2026-06-01T11:26:26.265000",
      "updated_at": "2026-06-01T11:26:54.635000",
      "error_msg": null
    }
    // up to 10 entries, newest first
  ],
  "recent_patients": [
    { "email": "nk1@bluparrot.in", "name": null, "created_at": "…", "updated_at": "…" }
    // up to 5 entries
  ]
}
```

---

### `GET /meetings`
**Query params**
| name | type | default | notes |
|---|---|---|---|
| `limit` | int | 25 | 1–100 |
| `offset` | int | 0 | skip N for pagination |
| `status` | string | — | filter: `processing` / `ready` / `error` |
| `patient_email` | string | — | filter to one patient |

**Response**
```json
{
  "items": [
    {
      "id": "4ff90dc7-…",
      "patient_email": "nk1@bluparrot.in",
      "mode": "offline",
      "status": "ready",
      "title": "…",
      "created_at": "…",
      "updated_at": "…",
      "error_msg": null
    }
  ],
  "total": 42,
  "limit": 25,
  "offset": 0
}
```

`items` are compact (no transcript / summary / notes). Use this for tables and lists; load the full doc with `GET /meetings/{id}` only when the user clicks through.

---

### `GET /meetings/{id}`
Full meeting payload — use for the detail page.

**Response**
```json
{
  "meeting": {
    "id": "4ff90dc7-…",
    "patient_email": "nk1@bluparrot.in",
    "mode": "offline",
    "status": "ready",
    "title": "Introduction to Agentic Tools",
    "audio_file_id": "6ad1d6144b390fb1dba030702",
    "error_msg": null,
    "created_at": "2026-06-01T11:26:26.265000",
    "updated_at": "2026-06-01T11:26:54.635000"
  },
  "transcript": {
    "text": "full plain-text transcript",
    "speakers": ["Speaker A", "Speaker B"],
    "utterances": [
      { "speaker": "Speaker A", "text": "…", "start_ms": 0, "end_ms": 4321 },
      { "speaker": "Speaker B", "text": "…", "start_ms": 4400, "end_ms": 6800 }
    ]
  },
  "summary": "Bullet-point summary text from Gemini",
  "notes": {
    "action_items": [
      { "task": "send the demo deck", "owner": "Speaker B", "deadline": "Thursday" }
    ],
    "decisions": [ "Ship on Friday." ],
    "questions": [ "Who owns customer onboarding?" ]
  },
  "audio_url": "/meetings/4ff90dc7-…/audio"
}
```

When `status !== "ready"`, the `transcript / summary / notes` fields are `null` (and `audio_url` may still be present once the audio reaches GridFS). Show a "Processing…" state in the UI.

---

### `GET /meetings/{id}/transcript`
Just the speaker-diarised transcript — for a dedicated transcript view.

**Response (200)**
```json
{
  "text": "full plain-text transcript",
  "speakers": ["Speaker A", "Speaker B"],
  "utterances": [
    { "speaker": "Speaker A", "text": "Hi everyone.", "start_ms": 0, "end_ms": 1280 },
    { "speaker": "Speaker B", "text": "Let's begin.", "start_ms": 1300, "end_ms": 2450 }
  ]
}
```
Returns **409** if the meeting isn't `ready` yet (`{"detail":"Transcript not available yet (status=processing)"}`).

---

### `GET /meetings/{id}/summary`
Title + Gemini summary text only.

**Response (200)**
```json
{
  "title": "Introduction to Agentic Tools for LinkedIn",
  "summary": "Based on the transcript, the meeting…"
}
```
409 if not ready.

---

### `GET /meetings/{id}/notes`
Structured notes only.

**Response (200)**
```json
{
  "action_items": [
    { "task": "send the demo deck", "owner": "Speaker B", "deadline": "Thursday" }
  ],
  "decisions": [ "Ship on Friday." ],
  "questions": [ "Who owns customer onboarding?" ]
}
```
409 if not ready.

---

### `GET /meetings/{id}/status`
Lightweight poll — use during processing.

**Response**
```json
{ "status": "ready", "error_msg": null }
```

---

### `GET /meetings/{id}/audio`
Streams the original recording. Use directly in an `<audio>` tag or as a download link:

```html
<audio controls src="/meetings/4ff90dc7-.../audio"></audio>
```

Content type is the original recording's (typically `audio/webm`).

---

### `POST /meetings/{id}/chat` — streaming chat (SSE)
Ask a question grounded in the transcript. Returns Server-Sent Events; consume with `fetch` + a reader (EventSource doesn't support POST).

**Request body**
```json
{ "question": "What were the action items?" }
```

**Response** — `text/event-stream`:
```
data: Based on
data:  the transcript
data: , the action items are…
event: done
data:
```

Frontend pattern (vanilla `fetch`):
```js
const resp = await fetch(`/meetings/${id}/chat`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ question })
});
const reader = resp.body.getReader();
const decoder = new TextDecoder();
let buffer = "";
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  const events = buffer.split("\n\n");
  buffer = events.pop() ?? "";
  for (const evt of events) {
    if (evt.includes("event: done")) return;
    const data = evt.split("\n").find(l => l.startsWith("data:"))?.slice(5).trimStart();
    if (data) onToken(data); // append to chat bubble
  }
}
```

---

### `POST /meetings/upload`  *(extension uses this — admin rarely needs)*
Multipart form upload. Returns the new `session_id`; processing runs in the background.

**Form fields**
| field | type | required |
|---|---|---|
| `email` | string | ✅ patient email; auto-creates patient row if new |
| `file` | binary | ✅ audio/video |

**Response**
```json
{ "session_id": "4ff90dc7-…" }
```

After upload, poll `/meetings/{session_id}/status` every ~4s until `status === "ready"`, then fetch `/meetings/{session_id}` for the full doc.

---

### `GET /patients`
**Query params**
| name | type | default | notes |
|---|---|---|---|
| `limit` | int | 25 | 1–100 |
| `offset` | int | 0 |  |
| `search` | string | — | case-insensitive substring on email **or** name |

**Response**
```json
{
  "items": [
    {
      "email": "nk1@bluparrot.in",
      "name": null,
      "created_at": "…",
      "updated_at": "…",
      "meeting_count": 2,
      "last_meeting_at": "2026-06-01T11:26:26.265000"
    }
  ],
  "total": 17,
  "limit": 25,
  "offset": 0
}
```

---

### `GET /patients/{email}`
Patient profile + chronological list of their meetings (newest first).

**Response**
```json
{
  "patient": {
    "email": "nk1@bluparrot.in",
    "name": "Alice",
    "created_at": "…",
    "updated_at": "…"
  },
  "meetings": [
    {
      "id": "4ff90dc7-…",
      "title": "Introduction to Agentic Tools",
      "status": "ready",
      "created_at": "…",
      "summary": "Bullet-point summary…"
    }
  ]
}
```

404 if the email isn't on file.

---

### `PATCH /patients/{email}`
Update the patient's display name.

**Request body**
```json
{ "name": "Alice Cooper" }
```

**Response** — updated patient document.

---

## Error responses

All errors are returned as `{ "detail": "<message>" }` with a non-2xx status.

| status | meaning |
|---|---|
| 400 | invalid request (e.g. bad email format) |
| 404 | resource not found |
| 409 | conflict (e.g. stop without active recording) |
| 500 | server error — show a toast, retry won't help until backend is fixed |

---

## Example frontend snippets

### React hook — paginated meeting list
```jsx
function useMeetings({ status, patientEmail, page = 0, pageSize = 25 } = {}) {
  const [data, setData] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const params = new URLSearchParams({ limit: pageSize, offset: page * pageSize });
    if (status) params.set("status", status);
    if (patientEmail) params.set("patient_email", patientEmail);
    setLoading(true);
    fetch(`/meetings?${params}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); });
  }, [status, patientEmail, page, pageSize]);

  return { ...data, loading };
}
```

### React hook — poll a single meeting until ready
```jsx
function useMeetingStatus(id) {
  const [status, setStatus] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const r = await fetch(`/meetings/${id}/status`).then(r => r.json());
      if (cancelled) return;
      setStatus(r);
      if (r.status === "processing") setTimeout(tick, 4000);
    };
    tick();
    return () => { cancelled = true; };
  }, [id]);
  return status;
}
```

### Dashboard page
```jsx
async function loadDashboard() {
  const dash = await fetch("/admin/dashboard").then(r => r.json());
  // dash.totals.patients
  // dash.totals.meetings
  // dash.meetings_by_status
  // dash.recent_meetings — render a table
  // dash.recent_patients — render a sidebar widget
}
```

---

## CORS

The backend allows:
- Any origin listed in `CORS_ORIGINS` (currently `http://localhost:5173`).
- Any Chrome extension origin (`chrome-extension://*`) — used by the recording extension.

If you deploy the frontend to a different origin, add it to `CORS_ORIGINS` in the backend `.env`.

---

## Versioning

This API is unversioned during development. Once stable, paths will move under `/v1/`. Treat current paths as v0.
