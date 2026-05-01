import React, { useState, useRef, useEffect } from 'react';

import useSessionStore from '../store/sessionStore';

const LLM_OPTIONS = [
  {
    group: 'QGenie (Qualcomm Internal - Recommended)',
    options: [
      { value: 'gpt-4o-qgenie', label: 'GPT-4o via QGenie', badge: 'Recommended', provider: 'qgenie' },
      { value: 'gpt-4-1-qgenie', label: 'GPT-4.1 via QGenie', badge: 'Latest', provider: 'qgenie' },
      { value: 'claude-sonnet-45-qgenie', label: 'Claude Sonnet 4.5 via QGenie', provider: 'qgenie' },
      { value: 'claude-opus-4-qgenie', label: 'Claude Opus 4 via QGenie', provider: 'qgenie' },
      { value: 'qgenie-pro', label: 'QGenie Pro (Qualcomm Fast)', provider: 'qgenie' },
    ],
  },
  {
    group: 'OpenAI (Direct - Fallback)',
    options: [
      { value: 'gpt-4o-openai', label: 'GPT-4o (OpenAI Direct)', provider: 'openai' },
      { value: 'gpt-4-1-openai', label: 'GPT-4.1 (OpenAI Direct)', provider: 'openai' },
    ],
  },
  {
    group: 'Anthropic (Direct - Fallback)',
    options: [
      { value: 'claude-sonnet-45-anthropic', label: 'Claude Sonnet 4.5 (Anthropic Direct)', provider: 'anthropic' },
      { value: 'claude-opus-4-anthropic', label: 'Claude Opus 4 (Anthropic Direct)', provider: 'anthropic' },
    ],
  },
];

export default function LLMSelector() {
  const llmModel = useSessionStore((state) => state.llmModel);
  const setLlmModel = useSessionStore((state) => state.setLlmModel);
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const selectedOption = LLM_OPTIONS
    .flatMap((g) => g.options)
    .find((o) => o.value === llmModel) || LLM_OPTIONS[0].options[0];

  const handleSelect = (option) => {
    setTimeout(() => {
      setLlmModel(option.value);
      setOpen(false);
    }, 0);
  };

  return (
    <div className="llm-selector" ref={ref}>
      <label className="selector-label small">AI Provider &amp; Model</label>
      <div
        className={`selector-trigger ${open ? 'open' : ''}`}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((prev) => !prev);
        }}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && setOpen((prev) => !prev)}
        style={{
          marginTop: 6,
          border: '1px solid var(--glass-border)',
          borderRadius: 8,
          padding: '10px 12px',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          cursor: 'pointer',
        }}
      >
        <span className="selected-badge badge" style={{ minWidth: 96 }}>{selectedOption.badge || ''}</span>
        <span className="selected-label" style={{ flex: 1 }}>{selectedOption.label}</span>
        <span className={`chevron ${open ? 'up' : 'down'}`}>▾</span>
      </div>

      {open && (
        <div
          className="selector-dropdown"
          onClick={(e) => e.stopPropagation()}
          style={{
            marginTop: 6,
            border: '1px solid var(--glass-border)',
            borderRadius: 8,
            background: 'var(--panel)',
            maxHeight: 320,
            overflowY: 'auto',
          }}
        >
          {LLM_OPTIONS.map((group) => (
            <div key={group.group} className="option-group" style={{ padding: '8px 10px' }}>
              <div className="group-label small" style={{ opacity: 0.8, marginBottom: 6 }}>{group.group}</div>
              {group.options.map((option) => (
                <div
                  key={option.value}
                  className={`option-item ${option.value === llmModel ? 'selected' : ''}`}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    handleSelect(option);
                  }}
                  role="option"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === 'Enter' && handleSelect(option)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '8px 10px',
                    borderRadius: 6,
                    cursor: 'pointer',
                    background: option.value === llmModel ? 'rgba(255,255,255,0.08)' : 'transparent',
                    marginBottom: 4,
                  }}
                >
                  {option.badge && <span className="option-badge badge">{option.badge}</span>}
                  <span className="option-label" style={{ flex: 1 }}>{option.label}</span>
                  {option.value === llmModel && <span className="option-check">✓</span>}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
