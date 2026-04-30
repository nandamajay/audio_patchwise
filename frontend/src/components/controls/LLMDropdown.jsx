export default function LLMDropdown({ value, onChange }) {
  return (
    <select className="select" value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="gpt-4o">OpenAI GPT-4o</option>
      <option value="claude-3-5">Claude 3.5</option>
      <option value="qualcomm-internal">Qualcomm Internal</option>
      <option value="custom">Custom</option>
    </select>
  );
}
