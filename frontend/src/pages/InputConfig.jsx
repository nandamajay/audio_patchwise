import { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import AryabhataAvatar from "../components/agents/AryabhataAvatar";
import ChanakyaAvatar from "../components/agents/ChanakyaAvatar";
import ContextBox from "../components/InputPanel/ContextBox";
import PatchUpload from "../components/InputPanel/PatchUpload";
import LLMDropdown from "../components/controls/LLMDropdown";
import GlassCard from "../components/layout/GlassCard";
import GradientHeader from "../components/layout/GradientHeader";
import PatchInput from "../components/patch/PatchInput";
import usePatchSubmit from "../hooks/usePatchSubmit";
import useSessionStore from "../store/sessionStore";

export default function InputConfig() {
  const navigate = useNavigate();
  const { submit } = usePatchSubmit();
  const {
    patchInput,
    kernelVersion,
    subsystem,
    sourcePath,
    llmModel,
    maxRounds,
    setField,
    resetConversation,
  } = useSessionStore();

  const missingContext = useMemo(() => {
    const missing = [];
    if (!patchInput.trim()) missing.push("patch input");
    if (!kernelVersion.trim()) missing.push("kernel version");
    if (!subsystem.trim()) missing.push("subsystem");
    if (!sourcePath.trim()) missing.push("source path");
    return missing;
  }, [patchInput, kernelVersion, subsystem, sourcePath]);

  const onStart = async () => {
    if (missingContext.length) return;
    resetConversation();
    const sessionId = await submit();
    setField("sessionId", sessionId);
    navigate("/conversation");
  };

  return (
    <div className="grid" style={{ gap: 18 }}>
      <GradientHeader
        title="Meet CHANAKYA & ARYABHATA"
        subtitle="Dual-agent autonomous patch review loop for ALSA/ASoC"
      />

      <div className="hero">
        <GlassCard>
          <ChanakyaAvatar size={120} />
          <div style={{ marginTop: 8 }}>
            <span className="badge">Reviewer</span>
          </div>
        </GlassCard>
        <GlassCard>
          <AryabhataAvatar size={120} />
          <div style={{ marginTop: 8 }}>
            <span className="badge">Developer</span>
          </div>
        </GlassCard>
      </div>

      <PatchUpload onPatchLoaded={(value) => setField("patchInput", value)} />
      <PatchInput value={patchInput} onChange={(value) => setField("patchInput", value)} />

      <div className="grid grid-2">
        <ContextBox
          patchContent={patchInput}
          value={{ subsystem, kernelVersion, sourcePath, notes: "" }}
          onChange={(data) => {
            setField("subsystem", data.subsystem || "");
            setField("kernelVersion", data.kernelVersion || "");
            setField("sourcePath", data.sourcePath || "");
          }}
        />

        <GlassCard>
          <h3 style={{ marginBottom: 10 }}>Configuration</h3>
          <div className="grid" style={{ gap: 10 }}>
            <LLMDropdown value={llmModel} onChange={(value) => setField("llmModel", value)} />
            <p className="small">
              Configure API keys securely in <a href="/settings" style={{ color: "var(--accent-blue)" }}>Settings</a>.
            </p>
            <label className="small">Max rounds: {maxRounds}</label>
            <input
              type="range"
              min="1"
              max="10"
              value={maxRounds}
              onChange={(event) => setField("maxRounds", Number(event.target.value))}
            />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {["Style", "Logic", "Memory", "LKML", "Commit Msg"].map((focus) => (
                <label key={focus} className="badge">
                  <input type="checkbox" defaultChecked />
                  {focus}
                </label>
              ))}
            </div>
          </div>
          {missingContext.length ? (
            <p className="small" style={{ marginTop: 10 }}>
              CHANAKYA needs more context: {missingContext.join(", ")}.
            </p>
          ) : null}
        </GlassCard>
      </div>

      <button type="button" className="btn" onClick={onStart} disabled={missingContext.length > 0}>
        Start Review Session
      </button>
    </div>
  );
}
