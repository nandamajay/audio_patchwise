import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import AryabhataAvatar from "../components/agents/AryabhataAvatar";
import ChanakyaAvatar from "../components/agents/ChanakyaAvatar";
import ContextBox from "../components/InputPanel/ContextBox";
import LLMSelector from "../components/LLMSelector";
import MaintainerSelector from "../components/MaintainerSelector";
import GlassCard from "../components/layout/GlassCard";
import GradientHeader from "../components/layout/GradientHeader";
import PatchInput from "../components/patch/PatchInput";
import usePatchSubmit from "../hooks/usePatchSubmit";
import useSessionStore from "../store/sessionStore";

export default function InputConfig() {
  const navigate = useNavigate();
  const [targets, setTargets] = useState({ lists: [], maintainers: [] });
  const { submit } = usePatchSubmit();
  const {
    patchInput,
    kernelVersion,
    subsystem,
    sourcePath,
    maxRounds,
    setMaxRounds,
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

  const contextValue = useMemo(
    () => ({ subsystem, kernelVersion, sourcePath, notes: "" }),
    [subsystem, kernelVersion, sourcePath],
  );

  const handleContextChange = useCallback(
    (data) => {
      const nextSubsystem = data?.subsystem || "";
      const nextKernelVersion = data?.kernelVersion || "";
      const nextSourcePath = data?.sourcePath || "";

      if (nextSubsystem !== subsystem) setField("subsystem", nextSubsystem);
      if (nextKernelVersion !== kernelVersion) setField("kernelVersion", nextKernelVersion);
      if (nextSourcePath !== sourcePath) setField("sourcePath", nextSourcePath);
    },
    [setField, subsystem, kernelVersion, sourcePath],
  );

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

      <PatchInput value={patchInput} onChange={(value) => setField("patchInput", value)} />

      <div className="grid grid-2">
        <ContextBox
          patchContent={patchInput}
          value={contextValue}
          onChange={handleContextChange}
        />

        <GlassCard>
          <h3 style={{ marginBottom: 10 }}>Configuration</h3>
          <div className="grid" style={{ gap: 10 }}>
            <LLMSelector />
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <p className="small">
                Configure API keys securely in Settings.
              </p>
              <button
                type="button"
                className="btn secondary"
                onClick={() => navigate("/settings")}
              >
                Open Settings
              </button>
            </div>
            <label className="small">Max rounds: {maxRounds}</label>
            <input
              type="range"
              min="1"
              max="10"
              value={maxRounds}
              onChange={(event) => setMaxRounds(Number(event.target.value))}
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

      <MaintainerSelector patchContent={patchInput} onSelectionChange={setTargets} />

      {targets.lists?.length || targets.maintainers?.length ? (
        <p className="small">
          Targeting {targets.lists?.length || 0} list(s) and {targets.maintainers?.length || 0} maintainer(s).
        </p>
      ) : null}

      <button type="button" className="btn" onClick={onStart} disabled={missingContext.length > 0}>
        Start Review Session
      </button>
    </div>
  );
}
