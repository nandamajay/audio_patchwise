import { useEffect, useMemo, useState } from "react";

function groupByProvider(models) {
  const grouped = { qgenie: [], openai: [], anthropic: [] };
  for (const model of models || []) {
    const provider = String(model.provider || "").toLowerCase();
    if (!grouped[provider]) continue;
    grouped[provider].push(model);
  }
  return grouped;
}

export default function LLMDropdown({ value, onChange }) {
  const [modelsData, setModelsData] = useState(null);

  useEffect(() => {
    let active = true;
    fetch("/api/models")
      .then((response) => response.json())
      .then((data) => {
        if (active) setModelsData(data);
      })
      .catch(() => {
        if (active) setModelsData(null);
      });

    return () => {
      active = false;
    };
  }, []);

  const grouped = useMemo(() => groupByProvider(modelsData?.models || []), [modelsData]);

  const optionsAvailable =
    grouped.qgenie.length + grouped.openai.length + grouped.anthropic.length > 0;

  const selectedValue = value || "qgenie/gpt-4o";
  const provider = selectedValue.includes("/")
    ? selectedValue.split("/", 1)[0]
    : selectedValue.includes(":")
      ? selectedValue.split(":", 1)[0]
      : "qgenie";

  return (
    <div className="llm-dropdown-container" style={{ display: "grid", gap: 8 }}>
      <label className="small">AI Provider &amp; Model</label>
      <select className="select" value={selectedValue} onChange={(event) => onChange(event.target.value)}>
        {optionsAvailable ? (
          <>
            <optgroup label="QGenie (Qualcomm Internal — Recommended)">
              {grouped.qgenie.map((model) => (
                <option key={`qgenie-${model.id}`} value={`qgenie/${model.id}`}>
                  {model.recommended ? "⭐ " : ""}
                  {model.label}
                </option>
              ))}
            </optgroup>

            <optgroup label="OpenAI (Direct — Fallback)">
              {grouped.openai.map((model) => (
                <option key={`openai-${model.id}`} value={`openai/${model.id}`}>
                  {model.label}
                </option>
              ))}
            </optgroup>

            <optgroup label="Anthropic (Direct — Fallback)">
              {grouped.anthropic.map((model) => (
                <option key={`anthropic-${model.id}`} value={`anthropic/${model.id}`}>
                  {model.label}
                </option>
              ))}
            </optgroup>
          </>
        ) : (
          <>
            <option value="qgenie/gpt-4o">⭐ GPT-4o via QGenie (Recommended)</option>
            <option value="openai/gpt-4o">GPT-4o (OpenAI Direct)</option>
            <option value="anthropic/claude-sonnet-4-5">Claude Sonnet 4.5 (Anthropic Direct)</option>
          </>
        )}
      </select>

      <span className={`provider-badge provider-${provider}`}>
        {provider === "qgenie"
          ? "🔵 QGenie Active"
          : provider === "openai"
            ? "🟢 OpenAI Active"
            : "🟠 Anthropic Active"}
      </span>
    </div>
  );
}
