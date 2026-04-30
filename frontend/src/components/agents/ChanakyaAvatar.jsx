export default function ChanakyaAvatar({ size = 54 }) {
  return (
    <div style={{ display: "grid", placeItems: "center", gap: 6 }}>
      <svg width={size} height={size} viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="60" cy="60" r="42" stroke="var(--chanakya-color)" strokeWidth="4" />
        <ellipse cx="45" cy="56" rx="14" ry="10" stroke="var(--chanakya-color)" strokeWidth="3" />
        <ellipse cx="75" cy="56" rx="14" ry="10" stroke="var(--chanakya-color)" strokeWidth="3" />
        <line x1="59" y1="56" x2="61" y2="56" stroke="var(--chanakya-color)" strokeWidth="3" />
        <path d="M27 35L40 24" stroke="var(--chanakya-color)" strokeWidth="3" />
        <circle cx="92" cy="80" r="11" stroke="var(--chanakya-color)" strokeWidth="3" />
        <line x1="100" y1="88" x2="110" y2="99" stroke="var(--chanakya-color)" strokeWidth="3" />
      </svg>
      <span className="small">CHANAKYA (Reviewer)</span>
    </div>
  );
}
