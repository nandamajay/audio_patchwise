import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import useSessionStore from "../../store/sessionStore";

const api = axios.create({ baseURL: "/api" });

export default function SubmissionPanel() {
  const { sessionId } = useSessionStore();
  const [checklist, setChecklist] = useState([]);
  const [manualChecks, setManualChecks] = useState({ diff_reviewed: false, target_selected: false });
  const [target, setTarget] = useState("download");
  const [targetRepo, setTargetRepo] = useState("");
  const [gerritUrl, setGerritUrl] = useState("");
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    api.get(`/submit/checklist/${sessionId}`).then((res) => {
      setChecklist(res.data.items || []);
    }).catch(() => setChecklist([]));
  }, [sessionId]);

  const allChecksReady = useMemo(() => {
    const auto = checklist.filter((item) => item.id !== "diff_reviewed" && item.id !== "target_selected");
    const autoReady = auto.every((item) => Boolean(item.checked));
    return autoReady && manualChecks.diff_reviewed && manualChecks.target_selected;
  }, [checklist, manualChecks]);

  const submit = async () => {
    if (!sessionId || !allChecksReady) return;
    setSubmitting(true);
    try {
      const response = await api.post("/submit/", {
        session_id: sessionId,
        target,
        target_repo: target === "github" ? targetRepo : null,
        gerrit_url: target === "gerrit" ? gerritUrl : null,
        checklist_confirmed: true,
      });
      setResult(response.data);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="glass card">
      <h3 style={{ marginBottom: 10 }}>📋 Submission Checklist</h3>
      <div style={{ display: "grid", gap: 6 }}>
        {checklist.map((item) => (
          <label key={item.id} style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={item.id in manualChecks ? manualChecks[item.id] : Boolean(item.checked)}
              disabled={!(item.id in manualChecks)}
              onChange={(event) =>
                setManualChecks((prev) => ({ ...prev, [item.id]: event.target.checked }))
              }
            />
            {item.label}
          </label>
        ))}
      </div>

      <h4 style={{ marginTop: 14, marginBottom: 8 }}>🎯 Select Target</h4>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {["github", "gerrit", "upstream", "download"].map((item) => (
          <button
            key={item}
            type="button"
            className={`btn ${target === item ? "" : "secondary"}`}
            onClick={() => {
              setTarget(item);
              setManualChecks((prev) => ({ ...prev, target_selected: true }));
            }}
          >
            {item.toUpperCase()}
          </button>
        ))}
      </div>

      {target === "github" ? (
        <input
          className="input"
          style={{ marginTop: 8 }}
          value={targetRepo}
          onChange={(event) => setTargetRepo(event.target.value)}
          placeholder="owner/repo"
        />
      ) : null}
      {target === "gerrit" ? (
        <input
          className="input"
          style={{ marginTop: 8 }}
          value={gerritUrl}
          onChange={(event) => setGerritUrl(event.target.value)}
          placeholder="https://your-gerrit-instance"
        />
      ) : null}

      <button
        type="button"
        className="btn"
        style={{ width: "100%", marginTop: 12, boxShadow: allChecksReady ? "0 0 18px rgba(79,255,176,0.35)" : "none", opacity: allChecksReady ? 1 : 0.6 }}
        disabled={!allChecksReady || submitting}
        onClick={submit}
      >
        {submitting ? "Submitting..." : "✅ Approve & Submit"}
      </button>

      {result ? (
        <div className="glass" style={{ marginTop: 10, padding: 10, borderRadius: 10 }}>
          <div>Submission status: {String(result.status)}</div>
          {result.url ? (
            <a href={result.url} target="_blank" rel="noreferrer">Open submission URL</a>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
