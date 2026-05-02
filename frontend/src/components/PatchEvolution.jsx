import React from "react";
import PatchEvolutionTimeline from "./PatchEvolutionTimeline";

export const EvolutionDiff = ({ sessionId, rounds }) => (
  <PatchEvolutionTimeline sessionId={sessionId} rounds={rounds} />
);

export const PatchEvolution = ({ sessionId, rounds }) => {
  return <EvolutionDiff sessionId={sessionId} rounds={rounds} />;
};

export default PatchEvolution;
