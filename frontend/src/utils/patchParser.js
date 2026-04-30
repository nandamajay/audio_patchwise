export function parsePatchMetadata(text = "") {
  const lines = text.split("\n");
  const subject = lines.find((line) => line.startsWith("Subject:")) || "";
  return {
    subject: subject.replace("Subject:", "").trim(),
    hasSignedOff: text.includes("Signed-off-by:"),
    lineCount: lines.length,
  };
}
