export default function AryabhataAvatar({ size = 54 }) {
  return (
    <div style={{ display: "grid", placeItems: "center", gap: 6 }}>
      <svg width={size} height={size} viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M35 28L42 15L50 28L58 14L66 28L74 13L83 28" stroke="var(--aryabhata-color)" strokeWidth="3" />
        <rect x="30" y="30" width="60" height="62" rx="30" stroke="var(--aryabhata-color)" strokeWidth="4" />
        <rect x="40" y="52" width="16" height="12" stroke="var(--aryabhata-color)" strokeWidth="3" />
        <rect x="64" y="52" width="16" height="12" stroke="var(--aryabhata-color)" strokeWidth="3" />
        <line x1="56" y1="58" x2="64" y2="58" stroke="var(--aryabhata-color)" strokeWidth="3" />
        <path d="M45 81H75" stroke="var(--aryabhata-color)" strokeWidth="3" />
        <path d="M86 82L95 73L104 82L95 91Z" stroke="var(--aryabhata-color)" strokeWidth="3" />
      </svg>
      <span className="small">ARYABHATA (Developer)</span>
    </div>
  );
}
