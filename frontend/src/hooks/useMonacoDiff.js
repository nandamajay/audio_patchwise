import { useEffect, useRef } from "react";
import * as monaco from "monaco-editor";

export function useMonacoDiff(containerRef, options) {
  const editorRef = useRef(null);
  const originalModelRef = useRef(null);
  const modifiedModelRef = useRef(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    if (!containerRef.current) return undefined;

    const originalModel = monaco.editor.createModel(
      options.originalContent || "",
      options.language || "text/plain",
    );
    const modifiedModel = monaco.editor.createModel(
      options.modifiedContent || "",
      options.language || "text/plain",
    );

    originalModelRef.current = originalModel;
    modifiedModelRef.current = modifiedModel;

    const editor = monaco.editor.createDiffEditor(containerRef.current, {
      theme: "vs-dark",
      readOnly: true,
      renderSideBySide: true,
      automaticLayout: true,
      minimap: { enabled: false },
      fontSize: 13,
      fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      lineNumbers: "on",
      diffCodeLens: true,
      ignoreTrimWhitespace: false,
      scrollBeyondLastLine: false,
    });

    if (isMountedRef.current) {
      editor.setModel({
        original: originalModel,
        modified: modifiedModel,
      });
    }
    editorRef.current = editor;

    return () => {
      isMountedRef.current = false;
      if (editorRef.current) {
        try {
          // Critical order: detach models before disposing editor.
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

      if (originalModelRef.current) {
        try {
          if (!originalModelRef.current.isDisposed()) {
            originalModelRef.current.dispose();
          }
        } catch {
          // no-op
        }
        originalModelRef.current = null;
      }

      if (modifiedModelRef.current) {
        try {
          if (!modifiedModelRef.current.isDisposed()) {
            modifiedModelRef.current.dispose();
          }
        } catch {
          // no-op
        }
        modifiedModelRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!isMountedRef.current) return;
    if (originalModelRef.current && !originalModelRef.current.isDisposed()) {
      originalModelRef.current.setValue(options.originalContent || "");
    }
    if (modifiedModelRef.current && !modifiedModelRef.current.isDisposed()) {
      modifiedModelRef.current.setValue(options.modifiedContent || "");
    }
  }, [options.originalContent, options.modifiedContent]);

  return editorRef;
}
