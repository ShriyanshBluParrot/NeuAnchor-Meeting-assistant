# AI Meeting Assistant

Records Google Meet calls (online) or in-person meetings (offline), transcribes
them with speaker diarization, and generates summaries, notes, and a RAG chat —
all stored on Google Cloud.

## Pipeline

```
Online:  Meet link → Recall.ai bot → webhook → GCS audio
Offline: Start/Stop mic recording → GCS audio
            ↓
AssemblyAI (speaker diarization) → Gemini 2.5 Pro (summary + notes)
            ↓
Google text-embedding-004 → Vertex AI Vector Search (RAG)
            ↓
All artifacts stored in GCS: audio.wav, transcript.json, summary.txt, notes.json
```

## Tech stack

- **Backend:** FastAPI (async)
- **Frontend:** React + Vite
- **Meeting bot:** Recall.ai
- **Transcription:** AssemblyAI (speaker diarization)
- **LLM:** Gemini 2.5 Pro (Vertex AI)
- **Embeddings:** `text-embedding-004` (Vertex AI)
- **Vector DB:** Vertex AI Vector Search
- **Storage:** Google Cloud Storage
- **Status tracking:** SQLite

## Setup

### 1. Prerequisites
- A GCP project with Vertex AI + Cloud Storage enabled
- A Vertex AI Vector Search index + deployed index endpoint
- Recall.ai and AssemblyAI API keys
- A service-account JSON key with access to GCS + Vertex AI
- `PortAudio` installed on the machine running offline recording
  (`apt-get install libportaudio2` on Debian/Ubuntu)

### 2. Backend
```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env   # fill in your keys
uvicorn main:app --reload --port 8000
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

### 4. Webhook (online meetings)
Recall.ai needs a public URL to deliver recordings. In development:
```bash
ngrok http 8000
# set WEBHOOK_BASE_URL=https://<your-ngrok-id>.ngrok.io in .env
```

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/meetings/online` | `{meet_url}` → dispatch Recall.ai bot |
| POST | `/meetings/offline/start` | Start mic recording |
| POST | `/meetings/offline/stop` | `{session_id}` → stop + process |
| GET | `/meetings/{id}/status` | Poll processing status |
| GET | `/meetings/{id}` | Full transcript, summary, notes |
| POST | `/meetings/{id}/chat` | `{question}` → streaming RAG answer (SSE) |
| POST | `/webhook/recall` | Recall.ai callback |

See `docs/superpowers/specs/` for the full design.
# Neu-anchor
