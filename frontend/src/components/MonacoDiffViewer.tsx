import React, { useEffect, useRef, useCallback } from 'react';
import * as monaco from 'monaco-editor';

interface Props {
  original: string;
  modified: string;
  language?: string;
  height?: string;
}

export const MonacoDiffViewer: React.FC<Props> = ({
  original, modified, language = 'diff', height = '400px'
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<monaco.editor.IStandaloneDiffEditor | null>(null);
  const origModelRef = useRef<monaco.editor.ITextModel | null>(null);
  const modModelRef = useRef<monaco.editor.ITextModel | null>(null);

  const disposeEditor = useCallback(() => {
    // CRITICAL ORDER: setModel(null) BEFORE dispose()
    if (editorRef.current) {
      try { editorRef.current.setModel(null); } catch {}
      try { editorRef.current.dispose(); } catch {}
      editorRef.current = null;
    }
    [origModelRef, modModelRef].forEach(ref => {
      if (ref.current) {
        try { if (!ref.current.isDisposed()) ref.current.dispose(); } catch {}
        ref.current = null;
      }
    });
  }, []);

  useEffect(() => {
    if (!containerRef.current) return;
    const ts = Date.now();
    origModelRef.current = monaco.editor.createModel(
      original, language, monaco.Uri.parse(`inmemory://orig-${ts}`));
    modModelRef.current = monaco.editor.createModel(
      modified, language, monaco.Uri.parse(`inmemory://mod-${ts}`));
    editorRef.current = monaco.editor.createDiffEditor(containerRef.current, {
      theme: 'vs-dark', readOnly: true, renderSideBySide: true,
      automaticLayout: true, minimap: { enabled: false },
      scrollBeyondLastLine: false, fontSize: 13,
      fontFamily: "'JetBrains Mono', 'Fira Code', monospace"
    });
    editorRef.current.setModel({
      original: origModelRef.current, modified: modModelRef.current
    });
    return () => { disposeEditor(); };
  }, []); // Run ONCE on mount only

  useEffect(() => {
    if (origModelRef.current && !origModelRef.current.isDisposed())
      origModelRef.current.setValue(original);
    if (modModelRef.current && !modModelRef.current.isDisposed())
      modModelRef.current.setValue(modified);
  }, [original, modified]);

  return <div ref={containerRef} style={{
    height, border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: '8px', overflow: 'hidden'
  }} />;
};
