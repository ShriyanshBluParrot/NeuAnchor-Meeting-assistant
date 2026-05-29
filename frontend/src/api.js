import axios from "axios";

const client = axios.create({ baseURL: "/" });

export async function startOnline(meetUrl) {
  const { data } = await client.post("/meetings/online", { meet_url: meetUrl });
  return data; // { session_id }
}

export async function startOffline() {
  const { data } = await client.post("/meetings/offline/start");
  return data; // { session_id }
}

export async function stopOffline(sessionId) {
  const { data } = await client.post("/meetings/offline/stop", {
    session_id: sessionId,
  });
  return data;
}

export async function uploadRecording(blob, filename = "recording.webm") {
  const form = new FormData();
  form.append("file", blob, filename);
  const { data } = await client.post("/meetings/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data; // { session_id }
}

export async function getStatus(sessionId) {
  const { data } = await client.get(`/meetings/${sessionId}/status`);
  return data; // { status, error_msg }
}

export async function getMeeting(sessionId) {
  const { data } = await client.get(`/meetings/${sessionId}`);
  return data; // { meeting, transcript, summary, notes }
}

export async function listMeetings() {
  const { data } = await client.get("/meetings");
  return data;
}

/**
 * Stream a chat answer via Server-Sent Events using fetch (EventSource can't POST).
 * Calls onToken for each token and onDone when finished.
 */
export async function streamChat(sessionId, question, onToken, onDone) {
  const resp = await fetch(`/meetings/${sessionId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`Chat failed: ${resp.status}`);
  }

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
      const lines = evt.split("\n");
      const isDone = lines.some((l) => l.startsWith("event: done"));
      const dataLine = lines.find((l) => l.startsWith("data:"));
      if (isDone) {
        onDone?.();
        return;
      }
      if (dataLine) {
        onToken(dataLine.slice("data:".length).replace(/^ /, ""));
      }
    }
  }
  onDone?.();
}
