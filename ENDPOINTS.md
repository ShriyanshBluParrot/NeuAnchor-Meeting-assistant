# Endpoint Cheat Sheet

Base URL (dev): `http://localhost:8000`
All responses are JSON unless noted. Times are UTC ISO-8601.
Auth: none yet. CORS: allows the listed `CORS_ORIGINS` + Chrome extensions.

---

## 1. Health

### `GET /health`
Liveness check.

**Response 200**
```json
{ "status": "ok" }
```

---

## 2. Admin

### `GET /admin/dashboard`
One-call payload for the admin home page.

**Response 200**
```json
{
  "totals": { "patients": 3, "meetings": 4 },
  "meetings_by_status": { "ready": 3, "error": 1 },
  "recent_meetings": [
    {
      "id": "4ff90dc7-6a27-4a0b-9f08-796db67ad1c7",
      "patient_email": "nk1@bluparrot.in",
      "mode": "offline",
      "status": "ready",
      "title": "Introduction to Agentic Tools for LinkedIn",
      "created_at": "2026-06-01T11:26:26.265000",
      "updated_at": "2026-06-01T11:26:54.635000",
      "error_msg": null
    }
  ],
  "recent_patients": [
    {
      "email": "nk1@bluparrot.in",
      "name": null,
      "created_at": "2026-06-01T11:26:26.252000",
      "updated_at": "2026-06-01T11:26:26.252000"
    }
  ]
}
```

---

## 3. Patients

### `GET /patients`
Paginated list, with meeting counts.

**Query params**
| name | type | default | notes |
|---|---|---|---|
| `limit` | int | 25 | 1–100 |
| `offset` | int | 0 | skip N |
| `search` | string | — | case-insensitive substring on email **or** name |

**Response 200**
```json
{
  "items": [
    {
      "email": "nk1@bluparrot.in",
      "name": "Alice",
      "created_at": "2026-06-01T11:26:26.252000",
      "updated_at": "2026-06-01T11:26:26.252000",
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

**Path params**
| name | type | notes |
|---|---|---|
| `email` | string | URL-encode the `@` (`%40`) |

**Response 200**
```json
{
  "patient": {
    "email": "nk1@bluparrot.in",
    "name": "Alice",
    "created_at": "2026-06-01T11:26:26.252000",
    "updated_at": "2026-06-01T11:26:26.252000"
  },
  "meetings": [
    {
      "id": "4ff90dc7-…",
      "title": "Introduction to Agentic Tools",
      "status": "ready",
      "created_at": "2026-06-01T11:26:26.265000",
      "summary": "Based on the transcript…"
    }
  ]
}
```

**Errors**
- `400 Bad Request` — invalid email format
- `404 Not Found` — email not on file

---

### `PATCH /patients/{email}`
Update the patient's display name.

**Request body**
```json
{ "name": "Alice Cooper" }
```

**Response 200**
```json
{
  "email": "nk1@bluparrot.in",
  "name": "Alice Cooper",
  "created_at": "2026-06-01T11:26:26.252000",
  "updated_at": "2026-06-01T12:10:33.000000"
}
```

---

## 4. Meetings

### `POST /meetings/upload`
Create a new meeting from an uploaded audio file. Used by the Chrome extension; the admin panel rarely needs this unless you build a re-upload UI.

**Form data (multipart)**
| field | type | required | notes |
|---|---|---|---|
| `email` | string | ✅ | patient email; auto-creates the patient row if new |
| `file` | binary | ✅ | audio or video file |

**Response 200**
```json
{ "session_id": "4ff90dc7-6a27-4a0b-9f08-796db67ad1c7" }
```

Processing runs asynchronously in the background. Poll `/meetings/{id}/status`.

**Errors**
- `400 Bad Request` — invalid email

---

### `GET /meetings`
Paginated list of meetings (compact — no transcript).

**Query params**
| name | type | default | notes |
|---|---|---|---|
| `limit` | int | 25 | 1–100 |
| `offset` | int | 0 |  |
| `status` | string | — | filter: `processing` / `ready` / `error` |
| `patient_email` | string | — | filter to one patient |

**Response 200**
```json
{
  "items": [
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
  ],
  "total": 4,
  "limit": 25,
  "offset": 0
}
```

---

### `GET /meetings/{id}`
Full meeting detail.

**Response 200**
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
      { "speaker": "Speaker A", "text": "Hi.", "start_ms": 0, "end_ms": 1280 },
      { "speaker": "Speaker B", "text": "Hi there.", "start_ms": 1300, "end_ms": 2450 }
    ]
  },
  "summary": "Bullet-point summary text from Gemini",
  "notes": {
    "action_items": [
      { "task": "send the demo deck", "owner": "Speaker B", "deadline": "Thursday" }
    ],
    "decisions": [ "Ship on Friday." ],
    "questions": [ "Who owns onboarding?" ]
  },
  "audio_url": "/meetings/4ff90dc7-…/audio"
}
```

When `meeting.status !== "ready"`, `transcript`, `summary`, `notes` are `null`. `audio_url` is non-null as soon as the audio is in storage.

**Errors**
- `404 Not Found` — unknown session id

---

### `GET /meetings/{id}/status`
Lightweight status poll (don't poll `/meetings/{id}` — too heavy).

**Response 200**
```json
{ "status": "ready", "error_msg": null }
```

`status` ∈ `processing` | `ready` | `error`. Poll every ~4s while `processing`.

---

### `GET /meetings/{id}/transcript`
Just the transcript (for a transcript-only view).

**Response 200**
```json
{
  "text": "full plain-text transcript",
  "speakers": ["Speaker A", "Speaker B"],
  "utterances": [
    { "speaker": "Speaker A", "text": "Hi.", "start_ms": 0, "end_ms": 1280 }
  ]
}
```

**Errors**
- `404 Not Found` — unknown session
- `409 Conflict` — `{"detail": "Transcript not available yet (status=processing)"}`

---

### `GET /meetings/{id}/summary`
Title + summary text only.

**Response 200**
```json
{
  "title": "Introduction to Agentic Tools for LinkedIn",
  "summary": "Based on the transcript, the meeting…"
}
```

**Errors**
- `404 Not Found` — unknown session
- `409 Conflict` — not ready yet

---

### `GET /meetings/{id}/notes`
Structured notes only.

**Response 200**
```json
{
  "action_items": [
    { "task": "send the demo deck", "owner": "Speaker B", "deadline": "Thursday" }
  ],
  "decisions": [ "Ship on Friday." ],
  "questions": [ "Who owns onboarding?" ]
}
```

**Errors**
- `404 Not Found`
- `409 Conflict` — not ready yet

---

### `GET /meetings/{id}/audio`
Streams the original recording binary. Use directly:

```html
<audio controls src="http://localhost:8000/meetings/{id}/audio"></audio>
```

**Response 200**
- `Content-Type: audio/webm` (or `audio/wav`, depending on the source)
- Body: the audio bytes (streamed; supports range requests automatically via FastAPI's `StreamingResponse`)

**Errors**
- `404 Not Found` — meeting has no audio yet

---

### `POST /meetings/{id}/chat`
Streaming chat over the transcript. **Server-Sent Events** — consume with `fetch` + a reader, not `EventSource` (EventSource doesn't support POST).

**Request body**
```json
{ "question": "What were the action items?" }
```

**Response 200** — `text/event-stream`:
```
data: Based on the
data:  transcript, the action
data:  items are…
event: done
data:
```

Pseudo-code:
```js
const resp = await fetch(`${API}/meetings/${id}/chat`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ question })
});
const reader = resp.body.getReader();
const decoder = new TextDecoder();
let buf = "";
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buf += decoder.decode(value, { stream: true });
  const events = buf.split("\n\n");
  buf = events.pop() ?? "";
  for (const evt of events) {
    if (evt.includes("event: done")) return;
    const data = evt.split("\n").find(l => l.startsWith("data:"))?.slice(5).trimStart();
    if (data) appendToken(data);
  }
}
```

**Errors**
- `404 Not Found` — unknown session
- `409 Conflict` — meeting not ready

---

## 5. Standard error shape

Every non-2xx response uses this shape:

```json
{ "detail": "human-readable error message" }
```

| status | when | UI handling |
|---|---|---|
| 400 | bad input | inline form / field error |
| 404 | not found | "doesn't exist" page |
| 409 | data not ready yet (still processing) | "Processing…" placeholder, keep polling |
| 500 | server error | toast + retry button |

---

## 6. Common flows (which endpoints to hit, in order)

### Dashboard / home
1. `GET /admin/dashboard`

### Patients list
1. `GET /patients?limit=25&offset=0&search=alice`

### One patient
1. `GET /patients/{email}` → render profile + list of meetings

### Meeting detail (full)
1. `GET /meetings/{id}` → render transcript + summary + notes
2. `<audio src={data.audio_url}>` for playback

### Meeting detail (tabbed / lazy)
1. `GET /meetings/{id}/status` → poll until `ready`
2. On click "Transcript" tab → `GET /meetings/{id}/transcript`
3. On click "Summary" tab → `GET /meetings/{id}/summary`
4. On click "Notes" tab → `GET /meetings/{id}/notes`
5. `<audio src="/meetings/{id}/audio">` always available

### Chat
1. Confirm meeting is `ready`.
2. `POST /meetings/{id}/chat` with `{question}` → stream tokens into the UI.

---

## 7. Live, interactive reference
The backend exposes auto-generated Swagger docs at:

**`http://localhost:8000/docs`**

Every endpoint above can be invoked from there (form fields + try-it-out button). Useful for sanity checks while building.
