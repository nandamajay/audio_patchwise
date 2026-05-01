import { Activity, History, House, MessagesSquare, Settings, SplitSquareVertical } from "lucide-react";
import { NavLink, Route, Routes } from "react-router-dom";

import ConversationPage from "./pages/ConversationThread";
import DiffOutputPage from "./pages/DiffOutput";
import HistoryPage from "./pages/HistoryPage";
import InputPage from "./pages/InputConfig";
import SettingsPage from "./pages/SettingsPage";
import SystemHealthDashboard from "./pages/SystemHealthDashboard";

const navClass = ({ isActive }) => `nav-pill ${isActive ? "active" : ""}`;

function NavItem({ to, icon, label }) {
  return (
    <NavLink to={to} className={navClass}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        {icon}
        {label}
      </span>
    </NavLink>
  );
}

export default function App() {
  return (
    <main className="app-shell">
      <nav className="top-nav">
        <NavItem to="/" icon={<House size={16} />} label="New Review" />
        <NavItem to="/conversation" icon={<MessagesSquare size={16} />} label="Conversation" />
        <NavItem to="/diff" icon={<SplitSquareVertical size={16} />} label="Diff & Output" />
        <NavItem to="/history" icon={<History size={16} />} label="History" />
        <NavItem to="/health" icon={<Activity size={16} />} label="System Health" />
        <NavItem to="/settings" icon={<Settings size={16} />} label="Settings" />
      </nav>

      <Routes>
        <Route path="/" element={<InputPage />} />
        <Route path="/conversation" element={<ConversationPage />} />
        <Route path="/diff" element={<DiffOutputPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/health" element={<SystemHealthDashboard />} />
        <Route path="/settings" element={<SettingsPage />} />

        <Route path="/session/:id" element={<ConversationPage />} />
        <Route path="/output/:id" element={<DiffOutputPage />} />
      </Routes>
    </main>
  );
}
