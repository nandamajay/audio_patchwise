export default function SimilarPatchCard({ refData }) {
  if (!refData) return null;

  return (
    <a
      className="glass"
      style={{ display: "block", marginTop: 8, padding: 10, borderRadius: 10 }}
      href={refData.url}
      target="_blank"
      rel="noreferrer"
    >
      <div>🔗 Similar: {refData.title}</div>
      <div className="small">{refData.url}</div>
    </a>
  );
}
