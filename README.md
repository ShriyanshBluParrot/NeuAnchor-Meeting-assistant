# NeuAnchor — AI Meeting Assistant

Records any meeting (Google Meet tab audio, microphone, or a pre-recorded
file), transcribes it with speaker diarization, and generates a summary,
action items, decisions, open questions, and an interactive chat over the
transcript.

## Pipeline

```
Chrome extension ─▶ POST /meetings/upload
                      │
                      ├─ store audio in MongoDB GridFS
                      ├─ AssemblyAI → speaker-labelled transcript
                      ├─ Gemini 2.5 Pro → title + summary + notes
                      ▼
              MongoDB `meetings` document
              { transcript, summary, notes, status: "ready" }
                      │
                      ▼
              Frontend / extension reads it back
              Chat panel streams Gemini answers over the transcript
```

## Tech stack

- **Backend:** FastAPI (async, Python 3.10+)
- **Frontend:** React + Vite
- **Recording client:** Chrome extension (MV3, tab + mic + file modes)
- **Transcription:** AssemblyAI (`universal-2`, speaker diarization)
- **LLM:** Gemini 2.5 Pro via Google AI Studio API key
- **Database / storage:** MongoDB Atlas — meeting docs + GridFS for audio

## Setup

### 1. Prerequisites
- A free [MongoDB Atlas](https://cloud.mongodb.com) cluster (M0 tier is fine)
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)
- An AssemblyAI API key

### 2. Backend
```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env   # fill in MONGO_URI, GEMINI_API_KEY, ASSEMBLYAI_API_KEY
uvicorn main:app --reload --port 8000
```
Health check: `curl http://localhost:8000/health` → `{"status":"ok"}`.

### 3. Frontend
```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

### 4. Chrome extension
1. `chrome://extensions` → enable **Developer mode**
2. **Load unpacked** → select `extension/`
3. Pin the icon; backend URL field defaults to `http://localhost:8000`

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/meetings/upload` | multipart audio upload → returns `{session_id}` |
| GET  | `/meetings/{id}/status` | poll processing status |
| GET  | `/meetings/{id}` | full transcript + summary + notes |
| GET  | `/meetings/{id}/audio` | stream the recorded audio |
| POST | `/meetings/{id}/chat` | `{question}` → streaming SSE answer |
| GET  | `/meetings` | list all sessions |

## Repo layout

```
backend/
  main.py            FastAPI app + lifespan
  config.py          env-driven settings
  db.py              MongoDB meeting tracker
  api/
    meetings.py      upload + read endpoints
    chat.py          streaming SSE chat
  core/
    mongo_client.py  shared async Mongo client / GridFS bucket
    storage.py       GridFS audio helpers
    transcriber.py   AssemblyAI REST client
    summarizer.py    Gemini title / summary / notes
    rag_engine.py    transcript-grounded chat
    gemini_client.py shared Gemini client (API-key mode)
    pipeline.py      orchestrates the post-upload pipeline
frontend/            React + Vite UI
extension/           Chrome MV3 recorder (tab / mic / file)
```
