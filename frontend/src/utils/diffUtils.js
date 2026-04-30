export function buildInlineDiffPreview(original = "", updated = "") {
  const left = original.split("\n");
  const right = updated.split("\n");
  const previews = [];

  const limit = Math.max(left.length, right.length);
  for (let index = 0; index < limit; index += 1) {
    const a = left[index] || "";
    const b = right[index] || "";
    if (a !== b) {
      previews.push({ before: a, after: b, line: index + 1 });
    }
    if (previews.length >= 5) break;
  }

  return previews;
}
