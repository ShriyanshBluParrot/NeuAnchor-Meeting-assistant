import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { startOnline, uploadRecording } from "../api.js";

export default function NewMeeting() {
  const navigate = useNavigate();
  const [tab, setTab] = useState("online");
  const [meetUrl, setMeetUrl] = useState("");
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);

  async function submitOnline(e) {
    e.preventDefault();
    if (!meetUrl.trim()) return;
    setBusy(true);
    setError("");
    try {
      const { session_id } = await startOnline(meetUrl.trim());
      navigate(`/meetings/${session_id}`);
    } catch (err) {
      setError(err?.response?.data?.detail ?? err.message);
    } finally {
      setBusy(false);
    }
  }

  async function startRecording() {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setRecording(true);
    } catch (err) {
      setError(
        err.name === "NotAllowedError"
          ? "Microphone permission denied. Allow mic access and try again."
          : `Could not access microphone: ${err.message}`
      );
    }
  }

  async function stopRecording() {
    const recorder = mediaRecorderRef.current;
    if (!recorder) return;
    setBusy(true);

    const blob = await new Promise((resolve) => {
      recorder.onstop = () =>
        resolve(new Blob(chunksRef.current, { type: "audio/webm" }));
      recorder.stop();
    });
    streamRef.current?.getTracks().forEach((t) => t.stop());
    setRecording(false);

    try {
      const { session_id } = await uploadRecording(blob, "recording.webm");
      navigate(`/meetings/${session_id}`);
    } catch (err) {
      setError(err?.response?.data?.detail ?? err.message);
    } finally {
      setBusy(false);
    }
  }

  async function uploadFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const { session_id } = await uploadRecording(file, file.name);
      navigate(`/meetings/${session_id}`);
    } catch (err) {
      setError(err?.response?.data?.detail ?? err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="tabs">
        <button
          className={tab === "online" ? "tab active" : "tab"}
          onClick={() => setTab("online")}
        >
          Online (Google Meet)
        </button>
        <button
          className={tab === "offline" ? "tab active" : "tab"}
          onClick={() => setTab("offline")}
        >
          Offline (In-person)
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {tab === "online" ? (
        <form onSubmit={submitOnline} className="form">
          <label>Google Meet link</label>
          <input
            value={meetUrl}
            onChange={(e) => setMeetUrl(e.target.value)}
            placeholder="https://meet.google.com/abc-defg-hij"
          />
          <p className="hint">
            A bot will join the meeting. The host must admit it before recording
            begins.
          </p>
          <button type="submit" disabled={busy || !meetUrl.trim()}>
            {busy ? "Sending bot…" : "Send bot to meeting"}
          </button>
        </form>
      ) : (
        <div className="form">
          <p className="hint">
            Records using this device's microphone (via your browser). Place the
            laptop between participants so the mic captures everyone. Speakers are
            separated automatically.
          </p>
          {!recording ? (
            <button onClick={startRecording} disabled={busy}>
              {busy ? "Uploading…" : "Start recording"}
            </button>
          ) : (
            <button className="stop" onClick={stopRecording} disabled={busy}>
              Stop recording & process
            </button>
          )}

          <p className="hint" style={{ marginTop: 16 }}>
            Or upload an existing recording (e.g. a downloaded Google Meet
            recording):
          </p>
          <input
            type="file"
            accept="audio/*,video/*"
            onChange={uploadFile}
            disabled={busy || recording}
          />
        </div>
      )}
    </div>
  );
}
