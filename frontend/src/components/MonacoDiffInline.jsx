import React, { useEffect, useRef, useState } from "react";
import * as monaco from "monaco-editor";

export const MonacoDiffInline = ({ original, modified, lineNumber }) => {
  const containerRef = useRef(null);
  const editorRef = useRef(null);
  const originalModelRef = useRef(null);
  const modifiedModelRef = useRef(null);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    if (!containerRef.current) return undefined;

    const timestamp = Date.now();
    const randomId = Math.random().toString(36).slice(2, 11);

    originalModelRef.current = monaco.editor.createModel(
      original || "",
      "c",
      monaco.Uri.parse(`inmemory://original-${timestamp}-${randomId}`),
    );

    modifiedModelRef.current = monaco.editor.createModel(
      modified || "",
      "c",
      monaco.Uri.parse(`inmemory://modified-${timestamp}-${randomId}`),
    );

    editorRef.current = monaco.editor.createDiffEditor(containerRef.current, {
      theme: "vs-dark",
      readOnly: true,
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      renderSideBySide: false,
      lineNumbers: (n) => `${(lineNumber || 1) + n - 1}`,
      fontSize: 12,
      lineHeight: 20,
      padding: { top: 8, bottom: 8 },
      scrollbar: { vertical: "hidden", horizontal: "hidden" },
      automaticLayout: true,
      renderValidationDecorations: "off",
    });

    editorRef.current.setModel({
      original: originalModelRef.current,
      modified: modifiedModelRef.current,
    });

    setIsReady(true);

    return () => {
      setIsReady(false);
      if (editorRef.current) {
        try {
          editorRef.current.setModel(null);
        } catch {
          // no-op
        }
        try {
          editorRef.current.dispose();
        } catch {
          // no-op
        }
        editorRef.current = null;
      }

      if (originalModelRef.current && !originalModelRef.current.isDisposed()) {
        originalModelRef.current.dispose();
      }
      originalModelRef.current = null;

      if (modifiedModelRef.current && !modifiedModelRef.current.isDisposed()) {
        modifiedModelRef.current.dispose();
      }
      modifiedModelRef.current = null;
    };
  }, [original, modified, lineNumber]);

  return (
    <div
      style={{
        border: "1px solid rgba(255,255,255,0.1)",
        borderRadius: "4px",
        overflow: "hidden",
        height: "80px",
      }}
    >
      {!isReady ? (
        <div
          style={{
            height: "80px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#6b7280",
            fontSize: "12px",
          }}
        >
          Loading diff...
        </div>
      ) : null}
      <div
        ref={containerRef}
        style={{ height: "80px", display: isReady ? "block" : "none" }}
      />
    </div>
  );
};

export const MonacoDiffFull = ({ original, modified }) => {
  const containerRef = useRef(null);
  const editorRef = useRef(null);
  const originalModelRef = useRef(null);
  const modifiedModelRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return undefined;

    const timestamp = Date.now();
    const randomId = Math.random().toString(36).slice(2, 11);

    originalModelRef.current = monaco.editor.createModel(
      original || "",
      "diff",
      monaco.Uri.parse(`inmemory://full-orig-${timestamp}-${randomId}`),
    );
    modifiedModelRef.current = monaco.editor.createModel(
      modified || "",
      "diff",
      monaco.Uri.parse(`inmemory://full-mod-${timestamp}-${randomId}`),
    );

    editorRef.current = monaco.editor.createDiffEditor(containerRef.current, {
      theme: "vs-dark",
      readOnly: true,
      minimap: { enabled: false },
      renderSideBySide: true,
      fontSize: 13,
      lineHeight: 22,
      scrollBeyondLastLine: false,
      automaticLayout: true,
      renderValidationDecorations: "off",
    });

    editorRef.current.setModel({
      original: originalModelRef.current,
      modified: modifiedModelRef.current,
    });

    return () => {
      if (editorRef.current) {
        try {
          editorRef.current.setModel(null);
        } catch {
          // no-op
        }
        try {
          editorRef.current.dispose();
        } catch {
          // no-op
        }
        editorRef.current = null;
      }

      if (originalModelRef.current && !originalModelRef.current.isDisposed()) {
        originalModelRef.current.dispose();
      }
      if (modifiedModelRef.current && !modifiedModelRef.current.isDisposed()) {
        modifiedModelRef.current.dispose();
      }
      originalModelRef.current = null;
      modifiedModelRef.current = null;
    };
  }, [original, modified]);

  return (
    <div
      ref={containerRef}
      style={{
        height: "500px",
        width: "100%",
        borderRadius: "8px",
        overflow: "hidden",
      }}
    />
  );
};
