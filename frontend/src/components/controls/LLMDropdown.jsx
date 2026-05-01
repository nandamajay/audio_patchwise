export default function LLMDropdown({ value, onChange }) {
  return (
    <select className="select" value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="openai:gpt-4o">OpenAI GPT-4o (Highest Accuracy)</option>
      <option value="anthropic:claude-3-5-sonnet-latest">Anthropic Claude 3.5 Sonnet</option>
      <option value="mock:local">Local Mock (No API Key)</option>
      <option value="qualcomm:qualcomm-internal">Qualcomm Internal (If wired)</option>
    </select>
  );
}
