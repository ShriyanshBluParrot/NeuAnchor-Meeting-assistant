import { useState } from "react";
import { streamChat } from "../api.js";

export default function ChatPanel({ sessionId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  async function send(e) {
    e.preventDefault();
    const question = input.trim();
    if (!question || busy) return;

    setInput("");
    setMessages((m) => [...m, { role: "user", text: question }]);
    setMessages((m) => [...m, { role: "assistant", text: "" }]);
    setBusy(true);

    try {
      await streamChat(
        sessionId,
        question,
        (token) =>
          setMessages((m) => {
            const copy = [...m];
            copy[copy.length - 1] = {
              role: "assistant",
              text: copy[copy.length - 1].text + token,
            };
            return copy;
          }),
        () => setBusy(false)
      );
    } catch (err) {
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = {
          role: "assistant",
          text: `Error: ${err.message}`,
        };
        return copy;
      });
      setBusy(false);
    }
  }

  return (
    <div className="chat-panel">
      <h3>Ask about this meeting</h3>
      <div className="chat-messages">
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg chat-${m.role}`}>
            {m.text || (m.role === "assistant" && busy ? "…" : "")}
          </div>
        ))}
      </div>
      <form className="chat-form" onSubmit={send}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. What were the action items?"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
