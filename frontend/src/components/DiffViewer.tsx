import React from "react";

import DiffViewerImpl from "./patch/DiffViewer";

interface DiffViewerProps {
  original: string;
  modified: string;
  language?: string;
  height?: string;
}

export const DiffViewer: React.FC<DiffViewerProps> = ({
  original,
  modified,
  language = "diff",
  height = "400px",
}) => {
  return (
    <DiffViewerImpl
      original={original}
      modified={modified}
      language={language}
      height={height}
    />
  );
};

export default DiffViewer;
