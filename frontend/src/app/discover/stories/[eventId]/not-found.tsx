import { PageState } from "@/components/system/page-state";

export default function NotFound() {
  return (
    <PageState
      state="empty"
      eyebrow="公开事件"
      title="事件不存在或不可公开阅读"
      description="事件不存在、已撤回或来源许可已经变化。可以探索其他资讯。"
    />
  );
}
