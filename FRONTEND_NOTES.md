# Frontend Integration — Quick Notes

Companion to **[API.md](API.md)** (full reference). Read this first; jump to
API.md when you need exact request/response shapes.

---

## 1. Setup (5 minutes)

- **Backend base URL (dev)**: `http://localhost:8000`
- **Auth**: none yet (will be added later — for now everything is public)
- **CORS**: backend already allows `http://localhost:5173`. If your dev server runs elsewhere, add the origin to backend `.env` (`CORS_ORIGINS`).
- **Health check**: `GET /health` → `{"status":"ok"}`. Run this on boot to fail fast if the backend isn't reachable.

In your app's API client, set:
```js
const API = "http://localhost:8000"; // override per env later
```

---

## 2. Mental model in one diagram

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│  patients   │1──▶N│  meetings   │1──▶1│ audio (GridFS)│
└─────────────┘     └─────────────┘     └──────────────┘
   keyed by         each meeting       streamed via
   email            embeds transcript  GET /meetings/{id}/audio
                   + summary + notes
```

- A **patient** is identified by **email** (lowercased, unique).
- A **meeting** is one recording session, linked to a patient via `patient_email`.
- A meeting's `status` walks through `processing → ready` (or `error`). Transcript / summary / notes only exist when `status === "ready"`.

---

## 3. The five flows you'll build

### A. Admin dashboard / home page
**One call:** `GET /admin/dashboard`
Returns `totals`, `meetings_by_status`, `recent_meetings` (10), `recent_patients` (5).
No transcripts in the payload → tiny and fast.

### B. Patients list page
`GET /patients?limit=25&offset=0&search=alice`
Returns `{items, total, limit, offset}`. Each item has `meeting_count` and `last_meeting_at` already aggregated.

### C. Patient detail page
`GET /patients/{email}`
Returns the patient profile + chronological list of their meetings (newest first). Each meeting in the list is summarised; click one to load full detail.

### D. Meeting detail page
`GET /meetings/{id}` — one call returns transcript + summary + notes + `audio_url`.
For tab-based UI you can lazy-load each section:
- `GET /meetings/{id}/transcript`
- `GET /meetings/{id}/summary`
- `GET /meetings/{id}/notes`
- `<audio src={audio_url}>` for playback

### E. Streaming chat over a meeting
`POST /meetings/{id}/chat` with `{ question }` — **Server-Sent Events stream**.
Use `fetch` + a reader (EventSource doesn't support POST). Snippet in section 6.

---

## 4. Status lifecycle — important

Every meeting goes through:

```
processing  ──▶  ready                ✅ show data
            ╲
             ╲──▶ error               ❌ show error_msg
```

**Rules:**
- Poll `GET /meetings/{id}/status` every **4 seconds** while status is `processing`.
- The focused endpoints (`/transcript`, `/summary`, `/notes`) return **409 Conflict** with `{detail: "...not available yet"}` if you call them before `ready`. Treat 409 as "still processing".
- If the status is `error`, the doc has `error_msg` — render it.

A meeting that says `processing` for >5 minutes is almost certainly stuck — surface a "retry" button. (Backend retry endpoint TBD; for now backend will auto-recover failed runs in a future deploy.)

---

## 5. Pagination conventions

Both `/meetings` and `/patients` use the same shape:

| param | default | range |
|---|---|---|
| `limit` | 25 | 1–100 |
| `offset` | 0 | ≥0 |

Response:
```json
{ "items": [...], "total": 42, "limit": 25, "offset": 0 }
```

Build pagination on the frontend by tracking `offset = page * pageSize`.

---

## 6. Copy-paste snippets

### Generic API client
```js
async function api(path, opts = {}) {
  const r = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`);
  return r.status === 204 ? null : r.json();
}
```

### Polling hook
```js
function useMeetingStatus(id) {
  const [status, setStatus] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const r = await api(`/meetings/${id}/status`);
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

### Streaming chat
```js
async function streamChat(meetingId, question, onToken, onDone) {
  const resp = await fetch(`${API}/meetings/${meetingId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
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
      if (evt.includes("event: done")) { onDone?.(); return; }
      const data = evt.split("\n").find(l => l.startsWith("data:"))?.slice(5).trimStart();
      if (data) onToken(data);
    }
  }
  onDone?.();
}
```

### Audio playback
```jsx
<audio controls src={`${API}/meetings/${id}/audio`} />
```

---

## 7. Error handling

All errors come back as `{ "detail": "<message>" }`. Status codes:

| status | meaning | UI action |
|---|---|---|
| 400 | bad request (e.g. invalid email) | inline form error |
| 404 | not found | "this resource doesn't exist" page |
| 409 | data not ready yet | "still processing" placeholder |
| 5xx | backend issue | toast + retry button |

Always show the `detail` string to the user — it's intentionally human-readable.

---

## 8. Things that will change later

- **Auth**: We'll add JWT/session auth. All endpoints will require `Authorization: Bearer <token>`. Plan your API client to forward auth headers from a single place so this is a 1-line change.
- **Base URL**: Will move from `localhost:8000` to a real domain. Read it from a `VITE_API_URL` env var so deploys flip via build config.
- **Versioning**: Paths will eventually move under `/v1/`. Treat current paths as v0 (no breaking-change promises during development).

---

## 9. What NOT to do

- ❌ **Don't poll `GET /meetings/{id}` repeatedly** — it returns the full transcript on every call. Use `/status` for polling, `/meetings/{id}` only when the user actually loads the detail page.
- ❌ **Don't download `/audio` to display a waveform** — it streams from MongoDB GridFS, can be 100+ MB for long meetings. Use the `<audio>` element which streams progressively.
- ❌ **Don't store patient emails in URL params unescaped** — emails contain `@`; encode them: `encodeURIComponent(email)`.
- ❌ **Don't expect timestamps to be local** — all `created_at` / `updated_at` are UTC ISO-8601. Convert with `new Date(s).toLocaleString()` for display.

---

## 10. Open questions for the backend team (raise as you build)

- Need an endpoint to **delete a meeting**? Tell us.
- Need **CSV / PDF export** of a meeting? Tell us.
- Need **bulk patient import**? Tell us.
- Need **retry** for failed meetings (re-run summarisation)? Tell us — it's a 10-line endpoint.

---

📖 **Full reference**: [API.md](API.md)
🩺 **Backend status**: `GET /health`
📚 **Swagger UI** (live, interactive): `http://localhost:8000/docs`
