# AI Meeting Assistant — GCP Redesign

**Date:** 2026-05-27  
**Status:** Approved  

---

## Context

The existing system accepts YouTube URLs or local files, uses Whisper/Sarvam for transcription, Mistral for LLM, and stores everything locally with ChromaDB. The goal is to rebuild it as a production-grade meeting assistant that:

- Accepts only Google Meet links (online) or local mic recording (offline)
- Joins online meetings via a bot (Recall.ai)
- Transcribes with AssemblyAI including speaker diarization
- Uses Gemini 2.5 Pro for all text generation
- Stores all artifacts (recording, transcript, summary, notes) on Google Cloud Storage
- Uses Google text-embedding-004 + Vertex AI Vector Search for RAG
- Exposes a FastAPI backend with a React frontend

---

## Architecture

### Dual-Path Recording

**Online path:**
1. User submits Google Meet link via React UI
2. FastAPI calls Recall.ai API to deploy a bot to the meeting
3. Bot joins, waits to be admitted by host, records audio+video
4. When meeting ends, Recall.ai POSTs a webhook to `POST /webhook/recall` with the recording URL
5. Backend downloads audio, converts to WAV, uploads to GCS
6. Processing pipeline starts as a background task

**Offline path:**
1. User clicks **Start Recording** in the React UI
2. FastAPI starts PyAudio microphone capture (mono WAV, 16kHz)
3. User clicks **Stop Recording**
4. WAV file uploaded to GCS
5. Processing pipeline starts as a background task

Both paths converge at the same processing pipeline once audio is in GCS.

### Processing Pipeline

```
GCS audio.wav
    ↓
AssemblyAI transcription (with speaker diarization)
    ↓  returns timestamped JSON with Speaker A/B/... labels
GCS: transcript.json
    ↓
Gemini 2.5 Pro (Vertex AI)
  - generate_summary()     → summary.txt
  - generate_notes()       → notes.json  { action_items, decisions, questions }
    ↓
GCS: summary.txt, notes.json
    ↓
Google text-embedding-004 (batch embed transcript chunks)
    ↓
Vertex AI Vector Search (upsert indexed vectors keyed by session_id)
```

### Status Tracking

A local SQLite database (lightweight, no extra GCP infra) tracks meeting status:

```
meetings table:
  id TEXT PRIMARY KEY       -- session-id (UUID)
  mode TEXT                 -- "online" | "offline"
  status TEXT               -- "recording" | "processing" | "ready" | "error"
  recall_bot_id TEXT        -- Recall.ai bot ID (online only)
  gcs_prefix TEXT           -- gs://<bucket>/meetings/<id>/
  created_at DATETIME
  error_msg TEXT
```

---

## Component Breakdown

### Backend (`backend/`)

```
backend/
├── main.py                 # FastAPI app, lifespan, CORS, router registration
├── db.py                   # SQLite session store (aiosqlite)
├── api/
│   ├── meetings.py         # POST /meetings/online, /offline/start, /offline/stop
│   │                       # GET /meetings/{id}, /meetings/{id}/status
│   ├── webhook.py          # POST /webhook/recall  (Recall.ai callback)
│   └── chat.py             # POST /meetings/{id}/chat  (streaming SSE response)
├── core/
│   ├── recorder.py         # PyAudio offline recording (start/stop, save WAV)
│   ├── recall_client.py    # Recall.ai REST API wrapper (create bot, get status)
│   ├── transcriber.py      # AssemblyAI SDK  (submit audio URL, poll, return JSON)
│   ├── summarizer.py       # Gemini 2.5 Pro via google-generativeai SDK
│   │                       #   generate_summary(transcript) → str
│   │                       #   generate_notes(transcript) → dict
│   ├── rag_engine.py       # Vertex AI Vector Search  (upsert, query, build context)
│   │                       #   embed_chunks(chunks) → batch embeddings
│   │                       #   upsert_to_index(session_id, chunks, embeddings)
│   │                       #   retrieve(session_id, query, k=5) → List[str]
│   │                       #   answer(session_id, question) → AsyncGenerator (stream)
│   ├── gcs_client.py       # GCS upload/download (shared client, singleton)
│   └── pipeline.py         # Orchestrates: transcribe → summarize → embed → index
│                           #   run_pipeline(session_id) — called as background task
└── requirements.txt
```

### Frontend (`frontend/`)

```
frontend/
├── src/
│   ├── App.jsx             # Router: / → NewMeeting, /meetings/:id → MeetingView
│   ├── pages/
│   │   ├── NewMeeting.jsx  # Tab: Online (Meet link input) | Offline (Start/Stop)
│   │   └── MeetingView.jsx # Transcript, summary, notes, RAG chat
│   ├── components/
│   │   ├── StatusBadge.jsx # Shows recording/processing/ready/error
│   │   ├── Transcript.jsx  # Speaker-labeled transcript viewer
│   │   └── ChatPanel.jsx   # Streaming SSE chat interface
│   └── api.js              # Axios wrapper for all backend calls
└── package.json
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/meetings/online` | `{meet_url}` → starts Recall.ai bot, returns `{session_id}` |
| POST | `/meetings/offline/start` | Starts mic recording, returns `{session_id}` |
| POST | `/meetings/offline/stop` | `{session_id}` → stops recording, uploads WAV, starts pipeline |
| GET | `/meetings/{id}/status` | Returns `{status, error_msg}` — frontend polls this |
| GET | `/meetings/{id}` | Returns full meeting data (transcript, summary, notes) |
| POST | `/webhook/recall` | Recall.ai webhook — downloads audio, starts pipeline |
| POST | `/meetings/{id}/chat` | `{question}` → streams SSE response from Gemini |

---

## GCS Storage Layout

```
gs://<BUCKET_NAME>/
  meetings/
    <session-id>/
      audio.wav          # Raw recording
      transcript.json    # AssemblyAI output with speaker diarization
      summary.txt        # Gemini-generated summary
      notes.json         # { action_items: [], decisions: [], questions: [] }
```

---

## Key Optimizations

- **Async I/O**: All FastAPI handlers and core functions use `async def` / `asyncio`
- **Background tasks**: FastAPI `BackgroundTasks` runs pipeline after upload — API returns immediately
- **Streaming chat**: Gemini streaming API + Server-Sent Events (SSE) for real-time chat responses
- **Batch embeddings**: `embed_chunks()` sends all chunks in a single Vertex AI batch call
- **Singleton GCS client**: Initialized once at app startup via FastAPI lifespan, not per-request
- **SQLite for status**: No extra GCP service needed for meeting state tracking

---

## Environment Variables

```
# Recall.ai
RECALL_API_KEY=

# AssemblyAI
ASSEMBLYAI_API_KEY=

# Google Cloud
GCP_PROJECT_ID=
GCP_LOCATION=us-central1
GCS_BUCKET_NAME=
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json

# Vertex AI Vector Search
VECTOR_SEARCH_INDEX_ID=
VECTOR_SEARCH_ENDPOINT_ID=

# App
WEBHOOK_BASE_URL=https://<your-public-url>  # for Recall.ai callback
```

---

## What Is Removed

| Old | Replaced By |
|-----|-------------|
| YouTube URL / local file input | Google Meet link or mic recording |
| Whisper + Sarvam AI | AssemblyAI |
| Mistral AI | Gemini 2.5 Pro |
| HuggingFace embeddings | Google text-embedding-004 |
| ChromaDB (local) | Vertex AI Vector Search |
| Local file storage | Google Cloud Storage |
| Streamlit UI | React + Vite |

---

## Out of Scope

- Authentication / user accounts
- Multi-tenant isolation (all meetings share one bucket and index)
- Real-time transcription during the meeting (transcription runs after meeting ends)
- Mobile app
