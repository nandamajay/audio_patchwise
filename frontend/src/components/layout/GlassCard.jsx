export default function GlassCard({ children, className = "", style }) {
  return (
    <div className={`glass card ${className}`.trim()} style={style}>
      {children}
    </div>
  );
}
