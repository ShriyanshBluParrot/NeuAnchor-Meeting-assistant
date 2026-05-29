import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getMeeting, getStatus } from "../api.js";
import StatusBadge from "../components/StatusBadge.jsx";
import Transcript from "../components/Transcript.jsx";
import ChatPanel from "../components/ChatPanel.jsx";

export default function MeetingView() {
  const { id } = useParams();
  const [status, setStatus] = useState("processing");
  const [errorMsg, setErrorMsg] = useState("");
  const [data, setData] = useState(null);

  // Poll status until the meeting is ready or errors out.
  useEffect(() => {
    let timer;
    let cancelled = false;

    async function poll() {
      try {
        const s = await getStatus(id);
        if (cancelled) return;
        setStatus(s.status);
        setErrorMsg(s.error_msg ?? "");
        if (s.status === "ready") {
          setData(await getMeeting(id));
          return;
        }
        if (s.status === "error") return;
      } catch {
        // transient; keep polling
      }
      timer = setTimeout(poll, 4000);
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [id]);

  return (
    <div className="meeting-view">
      <div className="meeting-head">
        <h2>{data?.meeting?.title ?? "Meeting"}</h2>
        <StatusBadge status={status} />
      </div>

      {status === "recording" && (
        <p className="hint">Recording in progress…</p>
      )}
      {status === "processing" && (
        <p className="hint">Transcribing and analysing the meeting…</p>
      )}
      {status === "error" && (
        <div className="error">Processing failed: {errorMsg}</div>
      )}

      {status === "ready" && data && (
        <div className="results">
          <section className="card">
            <h3>Summary</h3>
            <pre className="summary">{data.summary}</pre>
          </section>

          <section className="card notes-grid">
            <div>
              <h4>Action items</h4>
              <ul>
                {data.notes.action_items.map((a, i) => (
                  <li key={i}>
                    {a.task}
                    {a.owner ? ` — ${a.owner}` : ""}
                    {a.deadline ? ` (${a.deadline})` : ""}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h4>Decisions</h4>
              <ul>
                {data.notes.decisions.map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>
            </div>
            <div>
              <h4>Open questions</h4>
              <ul>
                {data.notes.questions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ul>
            </div>
          </section>

          <section className="card">
            <h3>Transcript</h3>
            <Transcript transcript={data.transcript} />
          </section>

          <section className="card">
            <ChatPanel sessionId={id} />
          </section>
        </div>
      )}
    </div>
  );
}
