// The API schema bounds the support index to 0–100. Keep its fixed scale
// when filtering; the leading visible model does not become 100%.
export function supportScoreValue(score: number) {
  return Number.isFinite(score) ? Math.min(100, Math.max(0, score)) : 0;
}

export function confidenceLabel(entry: HotKeyAPI.RankingEntryView) {
  if (entry.stability?.sensitive) return "对证据变化敏感";
  if (entry.confidence === "HIGH") return "证据覆盖较高";
  if (entry.confidence === "MEDIUM") return "证据覆盖有限";
  return "证据有限";
}
