import React, { useRef, useEffect, useCallback } from 'react';
import * as monaco from 'monaco-editor';

export default function DiffViewer({ original, modified, language = 'diff' }) {
  const containerRef = useRef(null);
  const editorRef = useRef(null);
  const originalModelRef = useRef(null);
  const modifiedModelRef = useRef(null);
  const mountedRef = useRef(true);

  const safeDisposeEditor = useCallback(() => {
    try {
      if (editorRef.current) {
        editorRef.current.setModel(null);
      }
    } catch (e) {
      // ignore
    }

    try {
      if (originalModelRef.current && !originalModelRef.current.isDisposed()) {
        originalModelRef.current.dispose();
      }
    } catch (e) {
      // ignore
    }
    originalModelRef.current = null;

    try {
      if (modifiedModelRef.current && !modifiedModelRef.current.isDisposed()) {
        modifiedModelRef.current.dispose();
      }
    } catch (e) {
      // ignore
    }
    modifiedModelRef.current = null;

    try {
      if (editorRef.current) {
        editorRef.current.dispose();
      }
    } catch (e) {
      // ignore
    }
    editorRef.current = null;
  }, []);

  useEffect(() => {
    mountedRef.current = true;

    if (!containerRef.current) return undefined;
    if (!original && !modified) return undefined;

    safeDisposeEditor();

    if (!mountedRef.current) return undefined;

    editorRef.current = monaco.editor.createDiffEditor(containerRef.current, {
      readOnly: true,
      theme: 'vs-dark',
      fontSize: 12,
      lineNumbers: 'on',
      renderSideBySide: true,
      ignoreTrimWhitespace: false,
      renderIndicators: true,
      automaticLayout: true,
      scrollBeyondLastLine: false,
      minimap: { enabled: false },
    });

    originalModelRef.current = monaco.editor.createModel(original || '', language);
    modifiedModelRef.current = monaco.editor.createModel(modified || '', language);

    if (editorRef.current && !editorRef.current.isDisposed()) {
      editorRef.current.setModel({
        original: originalModelRef.current,
        modified: modifiedModelRef.current,
      });
    }

    return () => {
      mountedRef.current = false;
      safeDisposeEditor();
    };
  }, [original, modified, language, safeDisposeEditor]);

  useEffect(() => {
    const observer = new ResizeObserver(() => {
      if (editorRef.current && !editorRef.current.isDisposed()) {
        editorRef.current.layout();
      }
    });
    if (containerRef.current) {
      observer.observe(containerRef.current);
    }
    return () => observer.disconnect();
  }, []);

  if (!original && !modified) {
    return (
      <div className="diff-placeholder">
        <span>No diff available yet</span>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      style={{ height: '300px', width: '100%', border: '1px solid #333' }}
    />
  );
}
