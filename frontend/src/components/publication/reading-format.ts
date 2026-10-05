export const categories = [
  ["ai-models", "模型"],
  ["ai-products", "产品"],
  ["industry", "行业"],
  ["paper", "论文"],
  ["tip", "技巧"],
  ["opinion", "观点"],
] as const;

export function publicationTime(value: string | null) {
  if (!value || Number.isNaN(new Date(value).getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
