import { useState } from "react";
import {
  AlertCircle,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  Clock,
  ExternalLink,
  Zap,
} from "lucide-react";

const stepConfig = {
  checkpatch_analysis: { icon: "🔍", color: "#00b4d8", label: "checkpatch.pl Analysis" },
  lsp_context: { icon: "🧩", color: "#7b2fff", label: "LSP Context Extraction" },
  lkml_search: { icon: "🌐", color: "#00d68f", label: "LKML Semantic Search" },
  compliance_check: { icon: "📋", color: "#ffaa00", label: "Upstream Compliance Check" },
  logic_analysis: { icon: "🧠", color: "#ff6b6b", label: "Logic & Memory Analysis" },
  fix_strategy: { icon: "💡", color: "#ffd166", label: "Fix Strategy Planning" },
  code_generation: { icon: "⚙️", color: "#06d6a0", label: "Code Generation" },
  justification: { icon: "📝", color: "#a8dadc", label: "Change Justification" },
  feedback_context: { icon: "👍", color: "#f4a261", label: "User Feedback Integration" },
};

function ConfidenceMeter({ value }) {
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? "#00d68f" : pct >= 60 ? "#ffaa00" : "#ff3d71";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
      <div
        style={{
          width: "80px",
          height: "6px",
          background: "rgba(255,255,255,0.1)",
          borderRadius: "3px",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: color,
            borderRadius: "3px",
            transition: "width 0.5s ease",
          }}
        />
      </div>
      <span style={{ color, fontSize: "11px", fontWeight: 700 }}>{pct}%</span>
    </div>
  );
}

function ReasoningNodeView({ node, depth = 0 }) {
  const [expanded, setExpanded] = useState(depth === 0);
  const cfg = stepConfig[node.step] || { icon: "🔵", color: "#8f9bb3", label: node.label };
  const hasChildren = node.children && node.children.length > 0;

  const statusIcon = {
    complete: <CheckCircle size={12} color="#00d68f" />,
    running: <Clock size={12} color="#ffaa00" className="spin" />,
    error: <AlertCircle size={12} color="#ff3d71" />,
    pending: <Clock size={12} color="#8f9bb3" />,
  }[node.status] || <Clock size={12} color="#8f9bb3" />;

  return (
    <div style={{ marginLeft: depth > 0 ? "20px" : "0", marginBottom: "6px" }}>
      <div
        onClick={() => hasChildren && setExpanded((prev) => !prev)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          padding: "8px 12px",
          borderRadius: "8px",
          background: `${cfg.color}11`,
          border: `1px solid ${cfg.color}33`,
          cursor: hasChildren ? "pointer" : "default",
          transition: "all 0.2s",
        }}
      >
        {hasChildren ? (
          expanded ? <ChevronDown size={12} color="#8f9bb3" /> : <ChevronRight size={12} color="#8f9bb3" />
        ) : (
          <span style={{ width: "12px" }} />
        )}
        <span style={{ fontSize: "14px" }}>{cfg.icon}</span>
        <span style={{ color: cfg.color, fontSize: "12px", fontWeight: 600 }}>{cfg.label}</span>

        <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "8px" }}>
          {node.confidence > 0 ? <ConfidenceMeter value={node.confidence} /> : null}
          {node.duration_ms > 0 ? <span style={{ color: "#8f9bb3", fontSize: "10px" }}>{node.duration_ms}ms</span> : null}
          {statusIcon}
        </span>
      </div>

      {expanded ? (
        <>
          {node.result ? (
            <div
              style={{
                marginLeft: "32px",
                marginTop: "4px",
                padding: "8px 12px",
                background: "rgba(0,0,0,0.2)",
                borderRadius: "6px",
                borderLeft: `2px solid ${cfg.color}55`,
              }}
            >
              <p style={{ color: "#cdd", fontSize: "11px", margin: 0, lineHeight: "1.5" }}>{node.result}</p>

              {(node.lkml_refs || []).map((ref, index) => (
                <a
                  key={`${ref.url || ref.title || index}`}
                  href={ref.url}
                  target="_blank"
                  rel="noreferrer"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "4px",
                    marginTop: "6px",
                    marginRight: "8px",
                    padding: "3px 8px",
                    borderRadius: "6px",
                    background: "rgba(0,212,143,0.1)",
                    border: "1px solid rgba(0,212,143,0.2)",
                    color: "#00d68f",
                    textDecoration: "none",
                    fontSize: "10px",
                  }}
                >
                  <ExternalLink size={9} />
                  {ref.title || ref.url}
                </a>
              ))}
            </div>
          ) : null}

          {(node.children || []).map((child, index) => (
            <ReasoningNodeView key={`${child.step}-${index}`} node={child} depth={depth + 1} />
          ))}
        </>
      ) : null}
    </div>
  );
}

export default function ThoughtChainTree({ thoughtChain, agentName, agentColor }) {
  const [viewMode, setViewMode] = useState("simple");

  if (!thoughtChain) return null;

  return (
    <div
      style={{
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: "12px",
        padding: "16px",
        marginTop: "10px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "14px" }}>
        <Zap size={14} color={agentColor} />
        <span style={{ color: agentColor, fontSize: "13px", fontWeight: 700 }}>{agentName} - Reasoning Chain</span>
        <span style={{ color: "#8f9bb3", fontSize: "11px" }}>
          Round {thoughtChain.round_num} - {thoughtChain.total_time}ms total
        </span>

        <div
          style={{
            marginLeft: "auto",
            display: "flex",
            background: "rgba(255,255,255,0.05)",
            borderRadius: "8px",
            padding: "2px",
          }}
        >
          {["simple", "deep"].map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setViewMode(mode)}
              style={{
                padding: "4px 12px",
                borderRadius: "6px",
                border: "none",
                background: viewMode === mode ? agentColor : "transparent",
                color: viewMode === mode ? "#fff" : "#8f9bb3",
                cursor: "pointer",
                fontSize: "11px",
                fontWeight: 600,
              }}
            >
              {mode === "simple" ? "Simple" : "Deep"}
            </button>
          ))}
        </div>
      </div>

      {viewMode === "simple" ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
          {(thoughtChain.nodes || []).map((node, index) => {
            const cfg = stepConfig[node.step] || { icon: "🔵", color: "#8f9bb3", label: node.step };
            return (
              <div
                key={`${node.step}-${index}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "4px",
                  padding: "4px 10px",
                  borderRadius: "12px",
                  background: `${cfg.color}15`,
                  border: `1px solid ${cfg.color}33`,
                }}
              >
                <span style={{ fontSize: "12px" }}>{cfg.icon}</span>
                <span style={{ color: cfg.color, fontSize: "11px", fontWeight: 600 }}>{cfg.label}</span>
                {node.status === "complete" ? <CheckCircle size={10} color={cfg.color} /> : null}
              </div>
            );
          })}
        </div>
      ) : (
        <div>
          {(thoughtChain.nodes || []).map((node, index) => (
            <ReasoningNodeView key={`${node.step}-${index}`} node={node} depth={0} />
          ))}
        </div>
      )}
    </div>
  );
}
