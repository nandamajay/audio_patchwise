import { useEffect, useMemo, useState } from "react";
import GlassCard from "../components/layout/GlassCard";
import useSessionStore from "../store/sessionStore";

const PRESETS = {
  openai: "gpt-4o",
  anthropic: "claude-3-5-sonnet-latest",
  qualcomm: "qualcomm-internal",
  mock: "local",
};

export default function SettingsPage() {
  const setField = useSessionStore((state) => state.setField);
  const [provider, setProvider] = useState("mock");
  const [model, setModel] = useState("local");
  const [apiKey, setApiKey] = useState("");
  const [keyMasked, setKeyMasked] = useState("");
  const [keySource, setKeySource] = useState("none");
  const [keysPresent, setKeysPresent] = useState({ openai: false, anthropic: false, qualcomm: false });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const currentSelection = useMemo(() => `${provider}:${model}`, [provider, model]);

  const loadSettings = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/settings/llm");
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Failed to load settings");
      setProvider(data.llm_provider || "mock");
      setModel(data.llm_model || PRESETS[data.llm_provider] || "local");
      setKeyMasked(data.key_masked || "");
      setKeySource(data.key_source || "none");
      setKeysPresent(data.keys_present || { openai: false, anthropic: false, qualcomm: false });
      setField("llmModel", `${data.llm_provider || "mock"}:${data.llm_model || "local"}`);
    } catch (err) {
      setError(err.message || "Unable to load settings");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings().catch(() => undefined);
  }, []);

  const saveSettings = async () => {
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const payload = {
        llm_provider: provider,
        llm_model: model,
        api_key: apiKey,
        key_provider: provider,
        persist_runtime: true,
      };
      const res = await fetch("/api/settings/llm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Failed to save settings");
      setApiKey("");
      setKeyMasked(data.key_masked || "");
      setKeySource(data.key_source || "none");
      setKeysPresent(data.keys_present || keysPresent);
      setField("llmModel", `${data.llm_provider}:${data.llm_model}`);
      setMessage("LLM settings updated.");
    } catch (err) {
      setError(err.message || "Unable to save settings");
    } finally {
      setSaving(false);
    }
  };

  const clearProviderKey = async () => {
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const res = await fetch("/api/settings/llm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          llm_provider: provider,
          llm_model: model,
          key_provider: provider,
          clear_key: true,
          persist_runtime: true,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Failed to clear key");
      setApiKey("");
      setKeyMasked(data.key_masked || "");
      setKeySource(data.key_source || "none");
      setKeysPresent(data.keys_present || keysPresent);
      setMessage(`Cleared runtime key for ${provider}.`);
    } catch (err) {
      setError(err.message || "Unable to clear key");
    } finally {
      setSaving(false);
    }
  };

  const onProviderChange = (value) => {
    setProvider(value);
    if (!model || model === PRESETS[provider]) {
      setModel(PRESETS[value] || "local");
    }
  };

  if (loading) {
    return (
      <GlassCard>
        <p className="small">Loading settings...</p>
      </GlassCard>
    );
  }

  return (
    <div className="grid" style={{ gap: 16 }}>
      <GlassCard>
        <h3 style={{ marginBottom: 8 }}>LLM Settings</h3>
        <p className="small" style={{ marginBottom: 14 }}>
          Configure provider and key without editing <code>.env</code>. Saved keys go to runtime secrets storage, not git.
        </p>

        <div className="grid" style={{ gap: 10 }}>
          <label className="small">Provider</label>
          <select className="select" value={provider} onChange={(event) => onProviderChange(event.target.value)}>
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic</option>
            <option value="qualcomm">Qualcomm</option>
            <option value="mock">Mock / Local</option>
          </select>

          <label className="small">Model</label>
          <input className="input" value={model} onChange={(event) => setModel(event.target.value)} />

          <label className="small">API Key ({provider.toUpperCase()})</label>
          <input
            type="password"
            className="input"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="Enter key only if you want to set/update it"
          />

          <div className="small" style={{ color: "var(--text-secondary)" }}>
            Active key source: <strong>{keySource}</strong>
            {keyMasked ? ` (${keyMasked})` : ""}
          </div>

          <div className="small" style={{ color: "var(--text-secondary)" }}>
            Key availability: OpenAI {keysPresent.openai ? "yes" : "no"} · Anthropic {keysPresent.anthropic ? "yes" : "no"} · Qualcomm {keysPresent.qualcomm ? "yes" : "no"}
          </div>

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button type="button" className="btn" onClick={saveSettings} disabled={saving}>
              {saving ? "Saving..." : "Save Settings"}
            </button>
            <button type="button" className="btn secondary" onClick={clearProviderKey} disabled={saving}>
              Clear Provider Key
            </button>
            <button type="button" className="btn secondary" onClick={loadSettings} disabled={saving}>
              Refresh
            </button>
          </div>

          <div className="small" style={{ color: "var(--text-secondary)" }}>
            Current UI selection: <code>{currentSelection}</code>
          </div>

          {message ? <p className="small" style={{ color: "#86efac" }}>{message}</p> : null}
          {error ? <p className="small" style={{ color: "#fca5a5" }}>{error}</p> : null}
        </div>
      </GlassCard>
    </div>
  );
}
