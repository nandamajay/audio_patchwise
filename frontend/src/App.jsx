import { Link, Route, Routes } from "react-router-dom";
import InputConfig from "./pages/InputConfig";
import ConversationThread from "./pages/ConversationThread";
import DiffOutput from "./pages/DiffOutput";

export default function App() {
  return (
    <div style={{ padding: "1rem", display: "grid", gap: "1rem" }}>
      <nav style={{ display: "flex", gap: "1rem" }}>
        <Link to="/">Input</Link>
        <Link to="/conversation">Conversation</Link>
        <Link to="/diff">Diff</Link>
      </nav>
      <Routes>
        <Route path="/" element={<InputConfig />} />
        <Route path="/conversation" element={<ConversationThread />} />
        <Route path="/diff" element={<DiffOutput />} />
      </Routes>
    </div>
  );
}
