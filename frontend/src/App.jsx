import { Link, Route, Routes } from "react-router-dom";
import NewMeeting from "./pages/NewMeeting.jsx";
import MeetingView from "./pages/MeetingView.jsx";

export default function App() {
  return (
    <div className="app">
      <header className="app-header">
        <Link to="/" className="brand">
          AI Meeting Assistant
        </Link>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<NewMeeting />} />
          <Route path="/meetings/:id" element={<MeetingView />} />
        </Routes>
      </main>
    </div>
  );
}
