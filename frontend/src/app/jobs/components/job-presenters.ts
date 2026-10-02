export const STATUS_LABELS: Record<HotKeyAPI.JobControlStatus, string> = {
  queued: "排队中",
  running: "执行中",
  cancelling: "取消中",
  succeeded: "已完成",
  partially_succeeded: "部分完成",
  failed: "失败",
  cancelled: "已取消",
};

export function capabilityLabel(
  capability: HotKeyAPI.SourceCapability,
): string {
  switch (capability) {
    case "search":
      return "检索";
    case "author_posts":
      return "作者作品";
    case "comments":
      return "评论";
    case "replies":
      return "回复";
    case "page_content":
      return "页面正文";
    case "hotlist":
      return "热榜";
  }
}

export function formatTime(value: string | null): string {
  if (value === null) {
    return "—";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value));
}
