function formatTime(ms) {
  if (ms == null) return "";
  const total = Math.floor(ms / 1000);
  const m = String(Math.floor(total / 60)).padStart(2, "0");
  const s = String(total % 60).padStart(2, "0");
  return `${m}:${s}`;
}

export default function Transcript({ transcript }) {
  if (!transcript) return null;
  const utterances = transcript.utterances ?? [];

  if (utterances.length === 0) {
    return <p className="transcript-plain">{transcript.text}</p>;
  }

  return (
    <div className="transcript">
      {utterances.map((u, i) => (
        <div key={i} className="utterance">
          <span className="utterance-speaker">{u.speaker}</span>
          <span className="utterance-time">{formatTime(u.start_ms)}</span>
          <p className="utterance-text">{u.text}</p>
        </div>
      ))}
    </div>
  );
}
