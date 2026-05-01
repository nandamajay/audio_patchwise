import { NavLink, Route, Routes } from "react-router-dom";

import ConversationThread from "./pages/ConversationThread";
import DiffOutput from "./pages/DiffOutput";
import InputConfig from "./pages/InputConfig";
import SettingsPage from "./pages/SettingsPage";

const navClass = ({ isActive }) => `nav-pill ${isActive ? "active" : ""}`;

export default function App() {
  return (
    <main className="app-shell">
      <nav className="top-nav">
        <NavLink to="/" className={navClass}>Input & Config</NavLink>
        <NavLink to="/conversation" className={navClass}>Conversation</NavLink>
        <NavLink to="/diff" className={navClass}>Diff & Output</NavLink>
        <NavLink to="/settings" className={navClass}>Settings</NavLink>
      </nav>

      <Routes>
        <Route path="/" element={<InputConfig />} />
        <Route path="/conversation" element={<ConversationThread />} />
        <Route path="/diff" element={<DiffOutput />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </main>
  );
}
