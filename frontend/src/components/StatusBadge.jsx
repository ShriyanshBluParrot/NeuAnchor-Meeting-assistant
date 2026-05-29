const LABELS = {
  recording: "Recording",
  processing: "Processing",
  ready: "Ready",
  error: "Error",
};

export default function StatusBadge({ status }) {
  return (
    <span className={`badge badge-${status}`}>{LABELS[status] ?? status}</span>
  );
}
